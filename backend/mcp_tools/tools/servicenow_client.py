"""
ServiceNow Client for AutoScrum MCP Integration

Provides async ServiceNow API client with OAuth 2.0 and Basic Auth support.
Adapted for use with AutoScrum orchestrator.
"""

import sys
import os
import asyncio
import time
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# ============================================================================
# Third-party imports
# ============================================================================
try:
    import httpx
except ImportError:
    httpx = None
    print("[WARN] httpx not installed. ServiceNow features will not work.", file=sys.stderr)

# ============================================================================
# ServiceNow Client and Utilities
# ============================================================================

class ServiceNowClient:
    """
    ServiceNow API client for AutoScrum.
    
    Supports both OAuth 2.0 and Basic Auth.
    Automatically initializes from environment variables.
    """
    
    def __init__(self, instance_url: Optional[str] = None, username: Optional[str] = None, 
                 password: Optional[str] = None, 
                 client_id: Optional[str] = None,
                 client_secret: Optional[str] = None,
                 timeout_seconds: int = 30):
        """
        Initialize ServiceNow client.
        
        If no parameters provided, reads from environment variables:
        - SERVICENOW_INSTANCE or SN_INSTANCE_URL
        - SERVICENOW_USERNAME or SN_USERNAME
        - SERVICENOW_PASSWORD or SN_PASSWORD
        - SN_CLIENT_CREDENTIALS (for OAuth)
        - SN_CLIENT_SECRET (for OAuth)
        """
        if httpx is None:
            raise RuntimeError("httpx not installed. Install with: pip install httpx")
        
        # Support both old and new env var names
        self.instance_url = (instance_url or 
                            os.getenv("SERVICENOW_INSTANCE") or 
                            os.getenv("SN_INSTANCE_URL", "")).rstrip("/")
        self.username = username or os.getenv("SERVICENOW_USERNAME") or os.getenv("SN_USERNAME")
        self.password = password or os.getenv("SERVICENOW_PASSWORD") or os.getenv("SN_PASSWORD")
        self.client_id = client_id or os.getenv("SN_CLIENT_CREDENTIALS")
        self.client_secret = client_secret or os.getenv("SN_CLIENT_SECRET")
        self.timeout_seconds = timeout_seconds
        
        # Check if configured
        self.configured = bool(self.instance_url and (
            (self.username and self.password) or 
            (self.client_id and self.client_secret)
        ))
        
        if not self.configured:
            print("Warning: ServiceNow credentials not configured")
            self._client = None
            self._auth = None
            self._access_token = None
            self._token_expires_at = None
            self._use_oauth = False
            return
        
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))
        self._auth: Optional[httpx.Auth] = None
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[float] = None
        
        self._use_oauth = bool(self.client_id and self.client_secret)
        if not self._use_oauth and self.username and self.password:
            self._auth = httpx.BasicAuth(self.username, self.password)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()

    async def _get_oauth_token(self) -> str:
        """Get OAuth 2.0 access token using CLIENT CREDENTIALS grant type."""
        if not self._use_oauth:
            raise RuntimeError("OAuth not configured (missing client_id or client_secret)")
        
        token_url = f"{self.instance_url}/oauth_token.do"
        
        payload = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        try:
            resp = await self._client.post(token_url, data=payload, headers=headers)
            
            if resp.status_code == 200:
                token_data = resp.json()
                access_token = token_data.get('access_token')
                expires_in = token_data.get('expires_in', 3600)
                
                if access_token:
                    self._access_token = access_token
                    self._token_expires_at = time.time() + expires_in - 60
                    return access_token
                else:
                    raise RuntimeError("OAuth token response missing 'access_token'")
            else:
                error_text = resp.text
                try:
                    error_data = resp.json()
                    error_desc = error_data.get('error_description', error_text)
                except:
                    error_desc = error_text
                raise RuntimeError(f"OAuth token request failed ({resp.status_code}): {error_desc}")
        except httpx.HTTPError as e:
            raise RuntimeError(f"OAuth token request network error: {str(e)}")

    async def _ensure_valid_token(self) -> None:
        """Ensure we have a valid OAuth token, fetching a new one if needed."""
        if not self._use_oauth or not self.configured:
            return
        
        if not self._access_token or (self._token_expires_at and time.time() >= self._token_expires_at):
            await self._get_oauth_token()

    @staticmethod
    def _needs_retry(status: int) -> bool:
        return status in {429, 500, 502, 503, 504}

    @staticmethod
    def _map_error_code(status: int, error_body: Optional[Dict[str, Any]] = None) -> str:
        """Map HTTP status code to error code, with special handling for 403."""
        if status in {400}:
            return "BAD_REQUEST"
        if status == 401:
            return "AUTH_ERROR"
        if status == 403:
            if error_body:
                error_msg = str(error_body).lower()
                if any(keyword in error_msg for keyword in ["data policy", "mandatory", "required field", "validation"]):
                    return "VALIDATION_ERROR"
            return "AUTH_ERROR"
        if status == 404:
            return "NOT_FOUND"
        if status == 409:
            return "CONFLICT"
        if status == 429:
            return "RATE_LIMIT"
        if 500 <= status <= 599:
            return "SERVER_ERROR"
        return "BAD_REQUEST"

    async def request(self, method: str, path: str,
                      params: Optional[Dict[str, Any]] = None,
                      json_body: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, Any]]:
        """Make HTTP request to ServiceNow API with retry logic."""
        if not self.configured or not self._client:
            raise RuntimeError("ServiceNow client not configured")
        
        url = f"{self.instance_url}{path}"
        headers = {"Accept": "application/json", "Content-Type": "application/json"}

        if self._use_oauth:
            await self._ensure_valid_token()
            if self._access_token:
                headers["Authorization"] = f"Bearer {self._access_token}"

        max_attempts = 5
        backoff = 0.5
        last_exc: Optional[Exception] = None
        
        for attempt in range(1, max_attempts + 1):
            try:
                auth = self._auth if not self._use_oauth else None
                resp = await self._client.request(method, url, params=params, json=json_body, 
                                                 headers=headers, auth=auth)
                
                if self._use_oauth and resp.status_code == 401 and attempt == 1:
                    await self._get_oauth_token()
                    headers["Authorization"] = f"Bearer {self._access_token}"
                    continue
                
                if self._needs_retry(resp.status_code):
                    delay = backoff + (0.1 * backoff * (0.5 - 0.5))
                    await asyncio.sleep(min(delay, 10.0))
                    backoff = min(backoff * 2, 8.0)
                    continue

                status = resp.status_code
                try:
                    body = resp.json()
                except Exception:
                    body = {"raw": resp.text}
                normalized_body = self.normalize_response(body)
                return status, normalized_body
            except (httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError) as e:
                last_exc = e
                await asyncio.sleep(min(backoff, 5.0))
                backoff = min(backoff * 2, 8.0)

        if last_exc:
            raise last_exc
        raise RuntimeError("Unknown request failure")

    @staticmethod
    def normalize_response(body: Dict[str, Any]) -> Dict[str, Any]:
        """ServiceNow wraps responses in 'result' key."""
        if isinstance(body, dict) and "result" in body:
            return body["result"]
        return body
    
    async def create_incident(
        self,
        short_description: str,
        description: str,
        priority: str = "3",
        category: Optional[str] = None,
        assigned_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create ServiceNow incident.
        
        Args:
            short_description: Brief incident description
            description: Detailed description
            priority: Priority (1=Critical, 2=High, 3=Medium, 4=Low)
            category: Incident category
            assigned_to: Assignee user ID
            
        Returns:
            Created incident data or error dict
        """
        if not self.configured:
            return {
                "error": "ServiceNow not configured",
                "error_message": "ServiceNow credentials are not configured. Please set SERVICENOW_INSTANCE, SERVICENOW_USERNAME, and SERVICENOW_PASSWORD in your .env file.",
                "success": False,
                "mock": False
            }
        
        try:
            # Build incident payload
            payload = {
                "short_description": short_description,
                "description": description,
                "priority": priority,
                "state": "1"  # New
            }
            
            if category:
                payload["category"] = category
            if assigned_to:
                payload["assigned_to"] = assigned_to
            
            # Make actual HTTP request to ServiceNow
            status, result = await self.request(
                "POST",
                "/api/now/table/incident",
                params=None,
                json_body=payload
            )
            
            if status not in {200, 201}:
                error_code = self._map_error_code(status, result if isinstance(result, dict) else None)
                return {
                    "error": f"ServiceNow API error: {status}",
                    "error_message": f"Failed to create incident in ServiceNow. HTTP {status}: {str(result)}",
                    "error_code": error_code,
                    "success": False,
                    "mock": False
                }
            
            # Extract incident data from response
            # ServiceNow API returns: {"result": {...}} which is normalized to {...} by normalize_response
            # Handle both dict and list responses
            if isinstance(result, dict):
                incident_data = result
            elif isinstance(result, list) and result:
                incident_data = result[0]
            else:
                return {
                    "error": "Invalid ServiceNow response",
                    "error_message": "ServiceNow returned an unexpected response format",
                    "success": False,
                    "mock": False
                }
            
            # Validate that we have required fields
            if not incident_data.get("number"):
                return {
                    "error": "Invalid ServiceNow response",
                    "error_message": "ServiceNow response missing incident number",
                    "success": False,
                    "mock": False
                }
            
            return {
                "number": incident_data.get("number"),
                "sys_id": incident_data.get("sys_id"),
                "short_description": incident_data.get("short_description"),
                "description": incident_data.get("description"),
                "priority": incident_data.get("priority"),
                "state": incident_data.get("state"),
                "created_at": incident_data.get("sys_created_on") or datetime.now().isoformat(),
                "mock": False
            }
        
        except httpx.ConnectError as e:
            # Connection error - ServiceNow instance not reachable
            return {
                "error": "ServiceNow connection failed",
                "error_message": f"Cannot connect to ServiceNow instance. Please check your SERVICENOW_INSTANCE URL and network connectivity. Error: {str(e)}",
                "success": False,
                "mock": False
            }
        except Exception as e:
            # Other errors - return error instead of fake data
            return {
                "error": "ServiceNow request failed",
                "error_message": f"Failed to create ServiceNow incident: {str(e)}",
                "success": False,
                "mock": False
            }


# ServiceNow utility functions
def make_request_id() -> str:
    return str(uuid.uuid4())


def envelope_success(data: Dict[str, Any], paging: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
        "meta": {"request_id": make_request_id(), "paging": paging or None},
    }


def envelope_error(message: str, code: Optional[str] = None, 
                   details: Optional[Dict[str, Any]] = None,
                   paging: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": {"message": message, "code": code, "details": details or None},
        "meta": {"request_id": make_request_id(), "paging": paging or None},
    }


def sanitize_fields(params: Dict[str, Any]) -> Dict[str, Any]:
    """Remove None values to keep queries clean."""
    return {k: v for k, v in params.items() if v is not None}


def paging_meta(limit: Optional[int], offset: Optional[int], count: Optional[int]) -> Dict[str, Any]:
    limit = int(limit or 0)
    offset = int(offset or 0)
    next_offset = offset + limit if limit else None
    next_token = f"offset={next_offset}" if next_offset is not None else None
    return {"limit": limit or 0, "offset": offset or 0, "next": next_token, "total": count}


def ensure_env() -> Optional[Dict[str, Any]]:
    """Check required ServiceNow env vars. Supports OAuth or Basic Auth."""
    missing = []
    if not os.getenv("SN_INSTANCE_URL"):
        missing.append("SN_INSTANCE_URL")
    
    has_oauth = bool(os.getenv("SN_CLIENT_CREDENTIALS") and os.getenv("SN_CLIENT_SECRET"))
    has_basic_auth = bool(os.getenv("SN_USERNAME") and os.getenv("SN_PASSWORD"))
    
    if not has_oauth and not has_basic_auth:
        if not os.getenv("SN_CLIENT_CREDENTIALS"):
            missing.append("SN_CLIENT_CREDENTIALS")
        if not os.getenv("SN_CLIENT_SECRET"):
            missing.append("SN_CLIENT_SECRET")
        if not os.getenv("SN_USERNAME"):
            missing.append("SN_USERNAME (or use OAuth)")
        if not os.getenv("SN_PASSWORD"):
            missing.append("SN_PASSWORD (or use OAuth)")
    
    if missing:
        return envelope_error(
            message=f"Missing required environment variables: {', '.join(missing)}. Provide either OAuth credentials (SN_CLIENT_CREDENTIALS + SN_CLIENT_SECRET) or Basic Auth (SN_USERNAME + SN_PASSWORD).",
            code="CONFIG_ERROR",
        )
    return None


async def get_client() -> ServiceNowClient:
    """Create ServiceNow client from env vars. Supports OAuth (preferred) or Basic Auth."""
    return ServiceNowClient(
        instance_url=os.getenv("SN_INSTANCE_URL", "").rstrip("/"),
        username=os.getenv("SN_USERNAME"),
        password=os.getenv("SN_PASSWORD"),
        client_id=os.getenv("SN_CLIENT_CREDENTIALS"),
        client_secret=os.getenv("SN_CLIENT_SECRET"),
        timeout_seconds=int(os.getenv("SN_TIMEOUT_SECONDS", "30")),
    )


async def test_servicenow_connection() -> bool:
    """Test ServiceNow connectivity at startup. Raises exception if fails."""
    cfg_err = ensure_env()
    if cfg_err:
        raise RuntimeError(f"ServiceNow config error: {cfg_err['error']['message']}")
    
    client = await get_client()
    try:
        status, body = await client.request("GET", "/api/now/table/sys_user", 
                                           params={"sysparm_limit": 1}, json_body=None)
        if status != 200:
            raise RuntimeError(f"ServiceNow health check failed with status {status}")
        return True
    finally:
        await client.close()


def register_servicenow_tools(mcp) -> None:
    """Register ServiceNow tools with the MCP server (legacy)."""
    # Optional MCP integration - only if FastMCP is available
    try:
        from mcp.server.fastmcp import FastMCP
        if not isinstance(mcp, FastMCP):
            return
    except ImportError:
        # FastMCP not available - skip MCP tool registration
        return
    
    @mcp.tool()
    async def servicenow_list_incidents(
        sysparm_query: str = "active=true",
        sysparm_fields: str = "",
        sysparm_limit: int = 50,
        sysparm_offset: int = 0
    ) -> str:
        """Query ServiceNow incidents."""
        cfg_err = ensure_env()
        if cfg_err:
            return str(cfg_err)
        
        params = sanitize_fields({
            "sysparm_query": sysparm_query,
            "sysparm_fields": sysparm_fields or None,
            "sysparm_limit": sysparm_limit,
            "sysparm_offset": sysparm_offset,
        })
        
        client = await get_client()
        try:
            status, body = await client.request("GET", "/api/now/table/incident", 
                                               params=params, json_body=None)
            if status != 200:
                error_code = ServiceNowClient._map_error_code(status, body if isinstance(body, dict) else None)
                return str(envelope_error(str(body), error_code, {"status": status},
                                         paging=paging_meta(params.get("sysparm_limit"), params.get("sysparm_offset"), None)))
            
            records = body if isinstance(body, list) else [body]
            return str(envelope_success({"records": records, "count": len(records)},
                                      paging=paging_meta(params.get("sysparm_limit"), params.get("sysparm_offset"), None)))
        finally:
            await client.close()
    
    @mcp.tool()
    async def servicenow_get_incident_by_number(number: str, sysparm_fields: str = "") -> str:
        """Retrieve a specific ServiceNow incident by its number."""
        cfg_err = ensure_env()
        if cfg_err:
            return str(cfg_err)
        
        if not number:
            return str(envelope_error("'number' is required", code="BAD_REQUEST"))
        
        params = sanitize_fields({
            "sysparm_query": f"number={number}",
            "sysparm_fields": sysparm_fields or None,
            "sysparm_limit": 1,
            "sysparm_offset": 0,
        })
        
        client = await get_client()
        try:
            status, body = await client.request("GET", "/api/now/table/incident", params=params, json_body=None)
            if status != 200:
                error_code = ServiceNowClient._map_error_code(status, body if isinstance(body, dict) else None)
                return str(envelope_error(str(body), error_code, {"status": status}))
            
            records = body if isinstance(body, list) else [body]
            if not records:
                return str(envelope_error("Incident not found", code="NOT_FOUND", details={"status": 404}))
            
            return str(envelope_success({"record": records[0]}))
        finally:
            await client.close()
    
    @mcp.tool()
    async def servicenow_create_incident(
        short_description: str,
        description: str = "",
        assignment_group: str = "",
        priority: str = "",
        caller_id: str = "",
        contact_type: str = "self-service"
    ) -> str:
        """Create a new ServiceNow incident/ticket."""
        cfg_err = ensure_env()
        if cfg_err:
            return str(cfg_err)
        
        payload = sanitize_fields({
            "short_description": short_description,
            "description": description or None,
            "assignment_group": assignment_group or None,
            "priority": priority or None,
            "caller_id": caller_id or None,
            "contact_type": contact_type or "self-service",
        })
        
        client = await get_client()
        try:
            status, body = await client.request("POST", "/api/now/table/incident", params=None, json_body=payload)
            if status not in {200, 201}:
                error_code = ServiceNowClient._map_error_code(status, body if isinstance(body, dict) else None)
                return str(envelope_error(str(body), error_code, {"status": status}))
            
            return str(envelope_success({"record": body}))
        finally:
            await client.close()
    
    @mcp.tool()
    async def servicenow_update_incident(
        sys_id: str,
        state: str = "",
        assigned_to: str = "",
        work_notes: str = "",
        close_code: str = "",
        close_notes: str = ""
    ) -> str:
        """Update an existing ServiceNow incident."""
        cfg_err = ensure_env()
        if cfg_err:
            return str(cfg_err)
        
        if not sys_id:
            return str(envelope_error("'sys_id' is required", code="BAD_REQUEST"))
        
        fields = sanitize_fields({
            "state": state or None,
            "assigned_to": assigned_to or None,
            "work_notes": work_notes or None,
            "close_code": close_code or None,
            "close_notes": close_notes or None,
        })
        
        client = await get_client()
        try:
            status, body = await client.request("PATCH", f"/api/now/table/incident/{sys_id}", params=None, json_body=fields)
            if status not in {200}:
                error_code = ServiceNowClient._map_error_code(status, body if isinstance(body, dict) else None)
                return str(envelope_error(str(body), error_code, {"status": status}))
            
            return str(envelope_success({"record": body}))
        finally:
            await client.close()
    
    @mcp.tool()
    async def servicenow_list_kb_articles(
        sysparm_query: str = "active=true",
        sysparm_fields: str = "",
        sysparm_limit: int = 20,
        sysparm_offset: int = 0,
        ci_sys_id: str = ""
    ) -> str:
        """Search ServiceNow Knowledge Base articles."""
        cfg_err = ensure_env()
        if cfg_err:
            return str(cfg_err)
        
        client = await get_client()
        try:
            params = None
            result = None
            
            if ci_sys_id:
                m2m_params = sanitize_fields({
                    "sysparm_query": f"cmdb_ci={ci_sys_id}",
                    "sysparm_fields": "kb_knowledge",
                    "sysparm_limit": 1000,
                })
                
                m2m_status, m2m_body = await client.request("GET", "/api/now/table/m2m_kb_ci", 
                                                           params=m2m_params, json_body=None)
                
                if m2m_status != 200:
                    if m2m_status in {401, 403}:
                        ci_params = sanitize_fields({
                            "sysparm_query": f"sys_id={ci_sys_id}",
                            "sysparm_fields": "name,model_id,class",
                            "sysparm_limit": 1,
                        })
                        ci_status, ci_body = await client.request("GET", "/api/now/table/cmdb_ci", params=ci_params)
                        
                        if ci_status == 200:
                            ci_record = ci_body[0] if isinstance(ci_body, list) and ci_body else (ci_body if isinstance(ci_body, dict) else {})
                            ci_name = ci_record.get("name", "")
                            ci_model = ci_record.get("model_id", {}).get("display_value", "") if isinstance(ci_record.get("model_id"), dict) else str(ci_record.get("model_id", ""))
                            ci_class = ci_record.get("class", {}).get("display_value", "") if isinstance(ci_record.get("class"), dict) else str(ci_record.get("class", ""))
                            
                            fallback_terms = []
                            if ci_name:
                                fallback_terms.append(f"short_descriptionCONTAINS{ci_name}")
                                fallback_terms.append(f"textCONTAINS{ci_name}")
                            if ci_model:
                                fallback_terms.append(f"short_descriptionCONTAINS{ci_model}")
                                fallback_terms.append(f"textCONTAINS{ci_model}")
                            if ci_class:
                                fallback_terms.append(f"short_descriptionCONTAINS{ci_class}")
                                fallback_terms.append(f"textCONTAINS{ci_class}")
                            
                            if fallback_terms:
                                fallback_query = "^OR".join(fallback_terms) + "^active=true"
                                if sysparm_query and sysparm_query != "active=true":
                                    base_query = sysparm_query.replace("^active=true", "").replace("active=true^", "").replace("active=true", "")
                                    if base_query:
                                        fallback_query = f"{base_query}^{fallback_query}"
                                
                                params = sanitize_fields({
                                    "sysparm_query": fallback_query,
                                    "sysparm_fields": sysparm_fields or None,
                                    "sysparm_limit": sysparm_limit,
                                    "sysparm_offset": sysparm_offset,
                                })
                            else:
                                return str(envelope_error("Could not retrieve CI details for fallback search.", code="NOT_FOUND"))
                        else:
                            return str(envelope_error("Could not retrieve CI details for fallback search.", code="NOT_FOUND"))
                    else:
                        error_code = ServiceNowClient._map_error_code(m2m_status, m2m_body if isinstance(m2m_body, dict) else None)
                        return str(envelope_error(f"Failed to query m2m_kb_ci: {str(m2m_body)}", error_code, {"status": m2m_status}))
                else:
                    m2m_records = m2m_body if isinstance(m2m_body, list) else [m2m_body]
                    
                    if not m2m_records:
                        return str(envelope_success({"records": [], "count": 0}, paging=paging_meta(sysparm_limit, sysparm_offset, 0)))
                    
                    kb_sys_ids = [record.get("kb_knowledge", {}).get("value") if isinstance(record.get("kb_knowledge"), dict) 
                                 else record.get("kb_knowledge") 
                                 for record in m2m_records if record.get("kb_knowledge")]
                    kb_sys_ids = list(set(filter(None, kb_sys_ids)))
                    
                    if not kb_sys_ids:
                        return str(envelope_success({"records": [], "count": 0}, paging=paging_meta(sysparm_limit, sysparm_offset, 0)))
                    
                    sys_id_query = "^OR".join([f"sys_id={kb_id}" for kb_id in kb_sys_ids])
                    
                    if sysparm_query and sysparm_query != "active=true":
                        base_query = sysparm_query.replace("^active=true", "").replace("active=true^", "").replace("active=true", "")
                        if base_query:
                            combined_query = f"{base_query}^{sys_id_query}^active=true"
                        else:
                            combined_query = f"{sys_id_query}^active=true"
                    else:
                        combined_query = f"{sys_id_query}^active=true"
                    
                    params = sanitize_fields({
                        "sysparm_query": combined_query,
                        "sysparm_fields": sysparm_fields or None,
                        "sysparm_limit": sysparm_limit,
                        "sysparm_offset": sysparm_offset,
                    })
            
            if params is None:
                query = sysparm_query if sysparm_query else "active=true"
                if "active=true" not in query and query != "":
                    query = f"{query}^active=true" if query else "active=true"
                
                params = sanitize_fields({
                    "sysparm_query": query,
                    "sysparm_fields": sysparm_fields or None,
                    "sysparm_limit": sysparm_limit,
                    "sysparm_offset": sysparm_offset,
                })
            
            status, body = await client.request("GET", "/api/now/table/kb_knowledge", params=params, json_body=None)
            if status != 200:
                error_code = ServiceNowClient._map_error_code(status, body if isinstance(body, dict) else None)
                return str(envelope_error(str(body), error_code, {"status": status},
                                         paging=paging_meta(params.get("sysparm_limit"), params.get("sysparm_offset"), None)))
            
            records = body if isinstance(body, list) else [body]
            return str(envelope_success({"records": records, "count": len(records)},
                                      paging=paging_meta(params.get("sysparm_limit"), params.get("sysparm_offset"), None)))
        finally:
            await client.close()
    
    @mcp.tool()
    async def servicenow_query_table(
        table_name: str,
        sysparm_query: str = "",
        sysparm_fields: str = "",
        sysparm_limit: int = 50,
        sysparm_offset: int = 0
    ) -> str:
        """Query any ServiceNow table."""
        cfg_err = ensure_env()
        if cfg_err:
            return str(cfg_err)
        
        if not table_name:
            return str(envelope_error("'table_name' is required", code="BAD_REQUEST"))
        
        params = sanitize_fields({
            "sysparm_query": sysparm_query or None,
            "sysparm_fields": sysparm_fields or None,
            "sysparm_limit": sysparm_limit,
            "sysparm_offset": sysparm_offset,
        })
        
        client = await get_client()
        try:
            status, body = await client.request("GET", f"/api/now/table/{table_name}", params=params, json_body=None)
            if status != 200:
                error_code = ServiceNowClient._map_error_code(status, body if isinstance(body, dict) else None)
                return str(envelope_error(str(body), error_code, {"status": status},
                                         paging=paging_meta(params.get("sysparm_limit"), params.get("sysparm_offset"), None)))
            
            records = body if isinstance(body, list) else [body]
            return str(envelope_success({"records": records, "count": len(records)},
                                      paging=paging_meta(params.get("sysparm_limit"), params.get("sysparm_offset"), None)))
        finally:
            await client.close()

# ============================================================================
# ServiceNow Tool Implementations (without @mcp.tool decorators)
# ============================================================================

async def servicenow_list_incidents_impl(
    sysparm_query: str = "active=true",
    sysparm_fields: str = "",
    sysparm_limit: int = 50,
    sysparm_offset: int = 0
) -> dict:
    """Implementation function for servicenow_list_incidents tool."""
    cfg_err = ensure_env()
    if cfg_err:
        return cfg_err
    
    params = sanitize_fields({
        "sysparm_query": sysparm_query,
        "sysparm_fields": sysparm_fields or None,
        "sysparm_limit": sysparm_limit,
        "sysparm_offset": sysparm_offset,
    })
    
    client = await get_client()
    try:
        status, body = await client.request("GET", "/api/now/table/incident", params=params, json_body=None)
        if status != 200:
            error_code = ServiceNowClient._map_error_code(status, body if isinstance(body, dict) else None)
            return envelope_error(str(body), error_code, {"status": status},
                                 paging=paging_meta(params.get("sysparm_limit"), params.get("sysparm_offset"), None))
        else:
            records = body if isinstance(body, list) else [body]
            return envelope_success({"records": records, "count": len(records)},
                                  paging=paging_meta(params.get("sysparm_limit"), params.get("sysparm_offset"), None))
    finally:
        await client.close()


async def servicenow_create_incident_impl(
    short_description: str,
    description: str = "",
    assignment_group: str = "",
    priority: str = "",
    caller_id: str = "",
    contact_type: str = "self-service"
) -> dict:
    """Implementation function for servicenow_create_incident tool."""
    cfg_err = ensure_env()
    if cfg_err:
        return cfg_err
    
    payload = sanitize_fields({
        "short_description": short_description,
        "description": description or None,
        "assignment_group": assignment_group or None,
        "priority": priority or None,
        "caller_id": caller_id or None,
        "contact_type": contact_type or "self-service",
    })
    
    client = await get_client()
    try:
        status, body = await client.request("POST", "/api/now/table/incident", params=None, json_body=payload)
        if status not in {200, 201}:
            error_code = ServiceNowClient._map_error_code(status, body if isinstance(body, dict) else None)
            return envelope_error(str(body), error_code, {"status": status})
        else:
            return envelope_success({"record": body})
    finally:
        await client.close()


async def servicenow_get_incident_by_number_impl(
    number: str,
    sysparm_fields: str = ""
) -> dict:
    """Implementation function for servicenow_get_incident_by_number tool."""
    cfg_err = ensure_env()
    if cfg_err:
        return cfg_err
    
    if not number:
        return envelope_error("'number' is required", code="BAD_REQUEST")
    
    params = sanitize_fields({
        "sysparm_query": f"number={number}",
        "sysparm_fields": sysparm_fields or None,
        "sysparm_limit": 1,
        "sysparm_offset": 0,
    })
    
    client = await get_client()
    try:
        status, body = await client.request("GET", "/api/now/table/incident", params=params, json_body=None)
        if status != 200:
            error_code = ServiceNowClient._map_error_code(status, body if isinstance(body, dict) else None)
            return envelope_error(str(body), error_code, {"status": status})
        else:
            records = body if isinstance(body, list) else [body]
            if not records:
                return envelope_error("Incident not found", code="NOT_FOUND", details={"status": 404})
            else:
                return envelope_success({"record": records[0]})
    finally:
        await client.close()


async def servicenow_get_problem_by_number_impl(
    number: str,
    sysparm_fields: str = ""
) -> dict:
    """Implementation function for servicenow_get_problem_by_number tool."""
    cfg_err = ensure_env()
    if cfg_err:
        return cfg_err
    
    if not number:
        return envelope_error("'number' is required", code="BAD_REQUEST")
    
    params = sanitize_fields({
        "sysparm_query": f"number={number}",
        "sysparm_fields": sysparm_fields or None,
        "sysparm_limit": 1,
        "sysparm_offset": 0,
    })
    
    client = await get_client()
    try:
        status, body = await client.request("GET", "/api/now/table/problem", params=params, json_body=None)
        if status != 200:
            error_code = ServiceNowClient._map_error_code(status, body if isinstance(body, dict) else None)
            return envelope_error(str(body), error_code, {"status": status})
        else:
            records = body if isinstance(body, list) else [body]
            if not records:
                return envelope_error("Problem not found", code="NOT_FOUND", details={"status": 404})
            else:
                return envelope_success({"record": records[0]})
    finally:
        await client.close()


async def servicenow_update_incident_impl(
    sys_id: str,
    state: str = "",
    assigned_to: str = "",
    work_notes: str = "",
    close_code: str = "",
    close_notes: str = ""
) -> dict:
    """Implementation function for servicenow_update_incident tool."""
    cfg_err = ensure_env()
    if cfg_err:
        return cfg_err
    
    if not sys_id:
        return envelope_error("'sys_id' is required", code="BAD_REQUEST")
    
    fields = sanitize_fields({
        "state": state or None,
        "assigned_to": assigned_to or None,
        "work_notes": work_notes or None,
        "close_code": close_code or None,
        "close_notes": close_notes or None,
    })
    
    client = await get_client()
    try:
        status, body = await client.request("PATCH", f"/api/now/table/incident/{sys_id}", params=None, json_body=fields)
        if status not in {200}:
            error_code = ServiceNowClient._map_error_code(status, body if isinstance(body, dict) else None)
            return envelope_error(str(body), error_code, {"status": status})
        else:
            return envelope_success({"record": body})
    finally:
        await client.close()


async def servicenow_list_kb_articles_impl(
    keywords: str = "",
    ci_sys_id: str = "",
    sysparm_limit: int = 20
) -> dict:
    """Implementation function for servicenow_list_kb_articles tool."""
    cfg_err = ensure_env()
    if cfg_err:
        return cfg_err
    
    client = await get_client()
    try:
        params = None
        result = None
        
        # If CI sys_id is provided, query m2m_kb_ci first
        if ci_sys_id:
            m2m_params = sanitize_fields({
                "sysparm_query": f"cmdb_ci={ci_sys_id}",
                "sysparm_fields": "kb_knowledge",
                "sysparm_limit": 1000,
            })
            
            m2m_status, m2m_body = await client.request("GET", "/api/now/table/m2m_kb_ci", 
                                                       params=m2m_params, json_body=None)
            
            if m2m_status != 200:
                if m2m_status in {401, 403}:
                    # Fallback: Get CI details and search by name
                    ci_params = sanitize_fields({
                        "sysparm_query": f"sys_id={ci_sys_id}",
                        "sysparm_fields": "name,model_id.name,sys_class_name",
                        "sysparm_limit": 1,
                    })
                    ci_status, ci_body = await client.request("GET", "/api/now/table/cmdb_ci", params=ci_params)
                    
                    if ci_status == 200 and ci_body:
                        ci_records = ci_body if isinstance(ci_body, list) else [ci_body]
                        if ci_records:
                            ci_record = ci_records[0]
                            ci_name = ci_record.get("name")
                            ci_model = ci_record.get("model_id", {}).get("display_value", "") if isinstance(ci_record.get("model_id"), dict) else str(ci_record.get("model_id", ""))
                            ci_class = ci_record.get("sys_class_name")
                            
                            search_terms = []
                            if ci_name: search_terms.append(ci_name)
                            if ci_model: search_terms.append(ci_model)
                            if ci_class: search_terms.append(ci_class)
                            
                            if search_terms:
                                keyword_query_parts = []
                                for term in search_terms:
                                    keyword_query_parts.append(f"short_descriptionCONTAINS{term}")
                                    keyword_query_parts.append(f"textCONTAINS{term}")
                                
                                fallback_query = f"({'^OR'.join(keyword_query_parts)})^active=true"
                                
                                params = sanitize_fields({
                                    "sysparm_query": fallback_query,
                                    "sysparm_limit": sysparm_limit,
                                    "sysparm_offset": 0,
                                })
                            else:
                                result = envelope_error("Could not retrieve CI details for fallback search.", code="NOT_FOUND")
                        else:
                            result = envelope_error("Could not retrieve CI details for fallback search.", code="NOT_FOUND")
                    else:
                        result = envelope_error("Could not retrieve CI details for fallback search.", code="NOT_FOUND")
                else:
                    error_code = ServiceNowClient._map_error_code(m2m_status, m2m_body if isinstance(m2m_body, dict) else None)
                    result = envelope_error(str(m2m_body), error_code, {"status": m2m_status})
            else:
                # m2m_kb_ci query succeeded
                m2m_records = m2m_body if isinstance(m2m_body, list) else [m2m_body]
                
                if not m2m_records:
                    result = envelope_success({"records": [], "count": 0}, 
                                            paging=paging_meta(sysparm_limit, 0, 0))
                else:
                    kb_sys_ids = [item.get("kb_knowledge", {}).get("value") if isinstance(item.get("kb_knowledge"), dict) 
                                 else item.get("kb_knowledge") 
                                 for item in m2m_records if item.get("kb_knowledge")]
                    kb_sys_ids = list(set(filter(None, kb_sys_ids)))
                    
                    if not kb_sys_ids:
                        result = envelope_success({"records": [], "count": 0}, 
                                                paging=paging_meta(sysparm_limit, 0, 0))
                    else:
                        kb_query = f"sys_idIN{','.join(kb_sys_ids)}^active=true"
                        params = sanitize_fields({
                            "sysparm_query": kb_query,
                            "sysparm_limit": sysparm_limit,
                            "sysparm_offset": 0,
                        })
        else:
            # Regular keyword search
            if keywords:
                keyword_query_parts = []
                for keyword in keywords.split():
                    keyword_query_parts.append(f"short_descriptionCONTAINS{keyword}")
                    keyword_query_parts.append(f"textCONTAINS{keyword}")
                query = f"({'^OR'.join(keyword_query_parts)})^active=true"
            else:
                query = "active=true"
            
            params = sanitize_fields({
                "sysparm_query": query,
                "sysparm_limit": sysparm_limit,
                "sysparm_offset": 0,
            })
        
        # Query kb_knowledge if params is set and result is not already set
        if result is None and params is not None:
            kb_status, kb_body = await client.request("GET", "/api/now/table/kb_knowledge", params=params, json_body=None)
            if kb_status == 200 and kb_body:
                kb_records = kb_body if isinstance(kb_body, list) else [kb_body]
                result = envelope_success({"records": kb_records, "count": len(kb_records)},
                                        paging=paging_meta(params.get("sysparm_limit"), params.get("sysparm_offset"), None))
            else:
                error_code = ServiceNowClient._map_error_code(kb_status, kb_body if isinstance(kb_body, dict) else None)
                result = envelope_error("No KB articles found.", code="NOT_FOUND",
                                       paging=paging_meta(params.get("sysparm_limit"), params.get("sysparm_offset"), None))
        
        if result is None:
            result = envelope_error("No search parameters provided.", code="BAD_REQUEST")
        
        return result
    finally:
        await client.close()


async def servicenow_query_table_impl(
    table_name: str,
    sysparm_query: str = "",
    sysparm_fields: str = "",
    sysparm_limit: int = 50,
    sysparm_offset: int = 0
) -> dict:
    """Implementation function for servicenow_query_table tool."""
    cfg_err = ensure_env()
    if cfg_err:
        return cfg_err
    
    if not table_name:
        return envelope_error("'table_name' is required", code="BAD_REQUEST")
    
    params = sanitize_fields({
        "sysparm_query": sysparm_query or None,
        "sysparm_fields": sysparm_fields or None,
        "sysparm_limit": sysparm_limit,
        "sysparm_offset": sysparm_offset,
    })
    
    client = await get_client()
    try:
        status, body = await client.request("GET", f"/api/now/table/{table_name}", params=params, json_body=None)
        if status != 200:
            error_code = ServiceNowClient._map_error_code(status, body if isinstance(body, dict) else None)
            return envelope_error(str(body), error_code, {"status": status},
                                 paging=paging_meta(params.get("sysparm_limit"), params.get("sysparm_offset"), None))
        else:
            records = body if isinstance(body, list) else [body]
            return envelope_success({"records": records, "count": len(records)},
                                  paging=paging_meta(params.get("sysparm_limit"), params.get("sysparm_offset"), None))
    finally:
        await client.close()


# Legacy MCP tool registration (for backward compatibility)
def _register_servicenow_connector(mcp) -> None:
    """Register ServiceNow tools with the MCP server (legacy)."""
    try:
        register_servicenow_tools(mcp)
    except Exception as e:
        print(f"[WARN] Failed to register ServiceNow tools: {e}", file=sys.stderr)


def _get_servicenow_tool_schemas() -> List[Dict[str, Any]]:
    """Return tool schemas for ServiceNow connector."""
    return [
        {
            "type": "function",
            "function": {
                "name": "servicenow_list_incidents",
                "description": "Query ServiceNow incidents/tickets. PRIMARY tool for questions about incidents, tickets, IT issues, problems, outages, device-related tickets, or IT support. Use for questions with words like 'incident', 'ticket', 'device', 'problem', 'issue', 'outage', 'created for', etc. Search by description using CONTAINS: device number 0501→short_descriptionCONTAINS0501^ORdescriptionCONTAINS0501^active=true. Build queries: open→active=true, P1→priority=1, my tickets→assigned_to=current_user. Combine with '^' (AND) or '^OR' (OR). Examples: 'incidents for device 0501'→short_descriptionCONTAINS0501^ORdescriptionCONTAINS0501^active=true, 'open P1 incidents'→active=true^priority=1.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sysparm_query": {
                            "type": "string", 
                            "description": "ServiceNow query filter. Build from natural language: open→active=true, closed→active=false, P1→priority=1, my tickets→assigned_to=current_user, network team→assignment_group.name=Network Team. SEARCH BY DESCRIPTION/DEVICE: Use CONTAINS for text search - device number 0501→short_descriptionCONTAINS0501^ORdescriptionCONTAINS0501, VPN→short_descriptionCONTAINSVPN^ORdescriptionCONTAINSVPN, database→short_descriptionCONTAINSdatabase^ORdescriptionCONTAINSdatabase. Combine with '^' (AND) or '^OR' (OR). Default: 'active=true'."
                        },
                        "sysparm_fields": {"type": "string", "description": "Comma-separated list of fields to return (e.g., 'number,short_description,state,priority'). Leave empty for all fields."},
                        "sysparm_limit": {"type": "integer", "description": "Max records to return. Extract from user request: 'show many'→50, 'show all'→100, 'just a few'→10. Default: 50."},
                        "sysparm_offset": {"type": "integer", "description": "Starting record offset for pagination. Use when user asks for 'next page' or 'more results'. Default: 0."}
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "servicenow_create_incident",
                "description": "Create a new ServiceNow incident/ticket. Use this when user asks to create a ticket, report an issue, or log a problem. IMPORTANT: Extract ALL available information from indirect user statements - urgency/criticality→priority (urgent/critical→'1', high→'2', low→'4'), team mentions→assignment_group (network team→'Network Team'), reporter→caller_id, details→description, contact method→contact_type (calling→'phone', emailing→'email'). Examples: 'Create ticket for database outage' → short_description='database outage', 'Report critical VPN issue for network team' → short_description='VPN issue', priority='1', assignment_group='Network Team', 'I need a high priority ticket for email server, call me' → short_description='email server', priority='2', contact_type='phone'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "short_description": {
                            "type": "string", 
                            "description": "Brief summary of the incident. Extract from user's main statement about what the issue is. Required field."
                        },
                        "description": {
                            "type": "string", 
                            "description": "Detailed description of the incident. Extract any additional details, context, or explanation the user provides beyond the short summary. If user provides detailed explanation, use it here."
                        },
                        "assignment_group": {
                            "type": "string", 
                            "description": "Group to assign the incident to. Extract from team/department mentions: 'network team'→'Network Team', 'IT support'→'IT Support', 'helpdesk'→'IT Helpdesk', 'security team'→'Security Team'. If user mentions a specific team, extract it."
                        },
                        "priority": {
                            "type": "string", 
                            "description": "Priority level: '1'=Critical/Urgent, '2'=High, '3'=Medium, '4'=Low. Extract from urgency mentions: 'urgent'/'critical'/'P1'→'1', 'high priority'/'important'→'2', 'low priority'/'not urgent'→'4'. If user mentions urgency, extract it."
                        },
                        "caller_id": {
                            "type": "string", 
                            "description": "User who reported the incident (username, email, or sys_id). Extract if user mentions who reported it, their name, email, or username."
                        },
                        "contact_type": {
                            "type": "string", 
                            "description": "How the incident was reported. Extract from contact method mentions: 'calling'/'call me'/'phone'→'phone', 'emailing'/'email'→'email', 'walk-in'→'walk-in', 'chat'→'chat'. Default: 'self-service'. If user mentions how they're reporting, extract it."
                        }
                    },
                    "required": ["short_description"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "servicenow_get_incident_by_number",
                "description": "Retrieve a specific ServiceNow incident by its number. Use this when user mentions a specific incident number. IMPORTANT: Extract incident number from various formats - full format 'INC0010002', without prefix '10002' (add INC prefix), with spaces/hyphens 'INC-001-0002' (normalize), from phrases 'ticket INC0010002' or 'incident number 10002'. Examples: 'Show me INC0010002', 'Get details for ticket 10002', 'What's the status of incident INC-001-0002?'",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "number": {
                            "type": "string",
                            "description": "Incident number. Extract and normalize from user input: 'INC0010002'→'INC0010002', '10002'→'INC0010002' (add INC prefix), 'INC-001-0002'→'INC0010002' (remove hyphens), 'ticket INC0010002'→'INC0010002'. Always normalize to format INC + digits."
                        },
                        "sysparm_fields": {
                            "type": "string",
                            "description": "Comma-separated list of specific fields to return (e.g., 'number,short_description,state,priority'). Leave empty for all fields. Extract if user asks for specific information like 'just the status' or 'only priority and description'."
                        }
                    },
                    "required": ["number"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "servicenow_update_incident",
                "description": "Update an existing ServiceNow incident. Use this to change incident status, reassign tickets, add notes, or close incidents. IMPORTANT: Extract ALL update information from indirect user statements - sys_id from incident number, state from status mentions (close/closed→'6', resolve/resolved→'6', in progress→'2'), assigned_to from reassignment (assign to John→'john.doe'), work_notes from note mentions, close_code from closure reason (resolved→'Solved (Work Around)', duplicate→'Duplicate'), close_notes from resolution details. Examples: 'Close incident INC001' → sys_id='<from INC001>', state='6', 'Assign ticket to John' → sys_id='<from context>', assigned_to='john.doe', 'Mark INC002 as resolved, duplicate of INC001' → sys_id='<from INC002>', state='6', close_code='Duplicate', close_notes='duplicate of INC001'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sys_id": {
                            "type": "string",
                            "description": "System ID of the incident to update. REQUIRED. Extract from incident number if provided (e.g., 'INC001' → get sys_id). If user provides incident number, you may need to look it up first or use the number format if sys_id is not available."
                        },
                        "state": {
                            "type": "string",
                            "description": "New state of the incident. Extract from status mentions: 'close'/'closed'→'6', 'resolve'/'resolved'→'6', 'in progress'/'working on it'→'2', 'new'→'1', 'on hold'→'3'. If user mentions status change, extract it."
                        },
                        "assigned_to": {
                            "type": "string",
                            "description": "User to assign the incident to (username or sys_id). Extract from reassignment mentions: 'assign to John'→'john.doe', 'give to IT team'→extract team member username, 'reassign to Sarah'→'sarah.smith'. If user mentions reassignment, extract it."
                        },
                        "work_notes": {
                            "type": "string",
                            "description": "Work notes to add to the incident. Extract from note mentions: 'add note that...'→work_notes='...', 'update with...'→work_notes='...', 'document that...'→work_notes='...'. If user mentions adding notes or updates, extract them."
                        },
                        "close_code": {
                            "type": "string",
                            "description": "Code indicating why the incident was closed. Extract from closure reason: 'resolved'/'fixed'→'Solved (Work Around)', 'duplicate'→'Duplicate', 'not an issue'→'Not an Issue', 'cancelled'→'Cancelled'. If user mentions closure reason, extract it."
                        },
                        "close_notes": {
                            "type": "string",
                            "description": "Notes explaining the resolution or closure. Extract from resolution details: 'resolved by...'→close_notes='...', 'fixed by restarting...'→close_notes='...', 'duplicate of...'→close_notes='...'. If user mentions resolution details, extract them."
                        }
                    },
                    "required": ["sys_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "servicenow_list_kb_articles",
                "description": "Search ServiceNow Knowledge Base articles. Use for questions about how-to guides, documentation, procedures, troubleshooting steps, OR KB articles related to Configuration Items (CIs). TWO MODES: 1) Regular search: keywords→search kb_knowledge. 2) CI-related: Extract CI sys_id→query m2m_kb_ci to find linked KB articles. Examples: 'How do I reset password?'→keywords, 'KB articles for CI 7779da38dbed9b84f82ee1c2ca961914'→ci_sys_id, 'Find KB articles about VPN'→keywords.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keywords": {
                            "type": "string",
                            "description": "Keywords to search for in KB articles. Extract from user's question: 'password reset'→keywords='password reset', 'VPN setup'→keywords='VPN setup', 'how to configure email'→keywords='email configuration'. Use this for regular KB article searches."
                        },
                        "ci_sys_id": {
                            "type": "string",
                            "description": "Configuration Item sys_id to find related KB articles. Extract from CI mentions: 'KB for CI 7779da38dbed9b84f82ee1c2ca961914'→ci_sys_id='7779da38dbed9b84f82ee1c2ca961914', 'knowledge base for this server'→extract server CI sys_id. Use this for CI-related KB article searches."
                        },
                        "sysparm_limit": {
                            "type": "integer",
                            "description": "Maximum number of articles to return. Extract from user request: 'show many'→50, 'show all'→100, 'just a few'→10. Default: 50."
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "servicenow_query_table",
                "description": "Query any ServiceNow table (CMDB CI, assets, users, etc.). Use this for questions about Configuration Items (CMDB CI), cmdb_ci, assets, devices, servers, users, or any ServiceNow table. Extract table name from query: 'cmdb_ci'→'cmdb_ci', 'CI'→'cmdb_ci', 'asset'→'alm_asset'. Extract sys_id: 'details 7779da38dbed9b84f82ee1c2ca961914'→sysparm_query='sys_id=7779da38dbed9b84f82ee1c2ca961914'. Examples: 'details of cmdb_ci 7779da38dbed9b84f82ee1c2ca961914'→table_name='cmdb_ci', sysparm_query='sys_id=7779da38dbed9b84f82ee1c2ca961914'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "Name of the ServiceNow table to query. Extract from user query: 'cmdb_ci'→'cmdb_ci', 'CI'→'cmdb_ci', 'asset'→'alm_asset', 'user'→'sys_user', 'device'→'cmdb_ci' (if device-related). Common tables: 'cmdb_ci', 'alm_asset', 'sys_user', 'cmdb_model', 'cmdb_location'."
                        },
                        "sysparm_query": {
                            "type": "string",
                            "description": "ServiceNow query filter. Extract from user query: 'sys_id=...'→sysparm_query='sys_id=...', 'name=...'→sysparm_query='name=...', 'active=true'→sysparm_query='active=true'. Combine with '^' (AND) or '^OR' (OR). Examples: 'sys_id=7779da38dbed9b84f82ee1c2ca961914', 'name=LAPTOP-001^active=true'."
                        },
                        "sysparm_fields": {
                            "type": "string",
                            "description": "Comma-separated list of fields to return. Leave empty for all fields. Extract if user asks for specific fields."
                        },
                        "sysparm_limit": {
                            "type": "integer",
                            "description": "Maximum number of records to return. Default: 50."
                        }
                    },
                    "required": ["table_name"]
                }
            }
        }
    ]


async def _initialize_servicenow_connector() -> bool:
    """Initialize ServiceNow connector (test connection)."""
    try:
        result = await test_servicenow_connection()
        if result:
            print("[OK] ServiceNow connector initialized", file=sys.stderr)
            return True
        else:
            print("[WARN] ServiceNow connection test failed", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[WARN] ServiceNow connector initialization failed: {e}", file=sys.stderr)
        print("[WARN] ServiceNow tools will not work - check SN_* env vars", file=sys.stderr)
        return False


async def _test_servicenow_connection() -> bool:
    """Test ServiceNow connection."""
    try:
        return await test_servicenow_connection()
    except Exception:
        return False

