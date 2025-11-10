"""Jira client for MCP integration - Refactored for FastMCP compatibility.

This module provides:
- Tool schema definitions for Jira operations
- Implementation functions for each tool
- Jira API client wrapper with proper error handling

Integrated comprehensive Jira functionality from jira-latest-tools including:
- Issue management (create, read, update, assign, transition)
- Story points and priority management
- JQL search capabilities
- Sprint-based aggregations
- Team capacity analysis
"""

import os
import json
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from dotenv import load_dotenv
import httpx
import requests
import logging

load_dotenv()
logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

class JiraConfigError(RuntimeError):
    """Raised when required Jira configuration values are missing."""


@dataclass
class JiraConfig:
    """Jira configuration with comprehensive settings."""
    base_url: str
    email: str
    api_token: str
    default_project: Optional[str] = None
    story_points_field_id: Optional[str] = None


def load_config() -> JiraConfig:
    """Load Jira configuration from environment variables (with .env support)."""
    load_dotenv()

    base_url = os.getenv("JIRA_BASE_URL", "").strip()
    email = os.getenv("JIRA_EMAIL", "").strip()
    api_token = os.getenv("JIRA_API_TOKEN", "").strip()
    default_project = os.getenv("JIRA_DEFAULT_PROJECT", "").strip() or None
    story_points_field_id = os.getenv("JIRA_STORY_POINTS_FIELD_ID", "").strip() or None

    missing = {
        "JIRA_BASE_URL": base_url,
        "JIRA_EMAIL": email,
        "JIRA_API_TOKEN": api_token,
    }
    missing_keys = [key for key, value in missing.items() if not value]
    if missing_keys:
        raise JiraConfigError(
            "Missing required environment variables: "
            + ", ".join(missing_keys)
            + ". Please provide them via environment variables or a .env file."
        )

    return JiraConfig(
        base_url=base_url.rstrip("/"),
        email=email,
        api_token=api_token,
        default_project=default_project,
        story_points_field_id=story_points_field_id,
    )


# ============================================================================
# Tool Schemas - Defining available Jira operations
# ============================================================================

def _get_jira_tool_schemas() -> List[Dict[str, Any]]:
    """Return comprehensive Jira tool schemas for MCP registration."""
    return [
        {
            "name": "jira_verify_credentials",
            "description": "Verify Jira credentials by calling the /myself endpoint",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "jira_get_issue",
            "description": "Fetch a Jira issue by its exact issue key. REQUIRES the full issue key (e.g., SCRUM-1, PROJ-123). If you only have a story name or title, use jira_search_issues instead to find the issue first.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "The exact Jira issue key (e.g., SCRUM-1, PROJ-123). This parameter is REQUIRED. If you only know the story name, use jira_search_issues to search for it first."
                    }
                },
                "required": ["issue_key"]
            }
        },
        {
            "name": "jira_search_issues",
            "description": "Search for Jira issues using a JQL (Jira Query Language) query. Use this when you have a story name, title, or other details but not the exact issue key. Example: To find a story named 'Task 3', use JQL: 'summary ~ \"Task 3\"' or 'text ~ \"Task 3\"'.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "jql": {
                        "type": "string",
                        "description": "JQL query string. REQUIRED. Examples: 'summary ~ \"Task 3\"' to search by summary, 'text ~ \"Task 3\"' to search all text fields, 'project = SCRUM AND summary ~ \"Task 3\"' to search in a specific project. To find a story by name, use: 'summary ~ \"story name\"' or 'text ~ \"story name\"'."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (optional, default: 50)",
                        "default": 50
                    },
                    "start_at": {
                        "type": "integer",
                        "description": "Starting index for pagination (optional, default: 0)",
                        "default": 0
                    },
                    "fields": {
                        "type": "string",
                        "description": "Comma-separated list of fields to return (optional)",
                        "default": None
                    }
                },
                "required": ["jql"]
            }
        },
        {
            "name": "jira_list_tasks",
            "description": "List recent tasks in a project (defaults to configured project)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_key": {
                        "type": "string",
                        "description": "Project key to list tasks from",
                        "default": None
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by status name",
                        "default": None
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tasks to list",
                        "default": 20
                    },
                    "start_at": {
                        "type": "integer",
                        "description": "Starting index for pagination",
                        "default": 0
                    }
                },
                "required": []
            }
        },
        {
            "name": "jira_create_issue",
            "description": "Create a Jira issue in the specified project",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_key": {
                        "type": "string",
                        "description": "Project key to create issue in",
                        "default": None
                    },
                    "summary": {
                        "type": "string",
                        "description": "Issue summary/title"
                    },
                    "issue_type": {
                        "type": "string",
                        "description": "Issue type (e.g., Task, Bug, Story)",
                        "default": "Task"
                    },
                    "description": {
                        "type": "string",
                        "description": "Issue description",
                        "default": None
                    },
                    "assignee_email": {
                        "type": "string",
                        "description": "Email of user to assign issue to",
                        "default": None
                    },
                    "story_points": {
                        "type": "number",
                        "description": "Story points for the issue",
                        "default": None
                    },
                    "priority": {
                        "type": "string",
                        "description": "Priority name (e.g., High, Medium, Low)",
                        "default": None
                    }
                },
                "required": ["summary"]
            }
        },
        {
            "name": "jira_assign_issue",
            "description": "Assign a Jira issue to a user",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Issue key to assign (e.g., SCRUM-1)"
                    },
                    "email": {
                        "type": "string",
                        "description": "Email address of the assignee"
                    }
                },
                "required": ["issue_key", "email"]
            }
        },
        {
            "name": "jira_set_story_points",
            "description": "Update an issue's story points",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Issue key (e.g., SCRUM-1)"
                    },
                    "story_points": {
                        "type": "number",
                        "description": "New story points value"
                    }
                },
                "required": ["issue_key", "story_points"]
            }
        },
        {
            "name": "jira_set_priority",
            "description": "Update an issue's priority by name",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Issue key (e.g., SCRUM-1)"
                    },
                    "priority": {
                        "type": "string",
                        "description": "Priority name (e.g., High, Medium, Low)"
                    }
                },
                "required": ["issue_key", "priority"]
            }
        },
        {
            "name": "jira_transition_issue",
            "description": "Move an issue through the workflow to the target status",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Issue key (e.g., SCRUM-1)"
                    },
                    "target_status": {
                        "type": "string",
                        "description": "Target status name (e.g., 'In Progress', 'Done')"
                    }
                },
                "required": ["issue_key", "target_status"]
            }
        },
        {
            "name": "jira_story_points_summary",
            "description": "Aggregate story points per assignee for a sprint or custom JQL",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "sprint": {
                        "type": "string",
                        "description": "Sprint identifier or clause",
                        "default": None
                    },
                    "project_key": {
                        "type": "string",
                        "description": "Project key to scope the query",
                        "default": None
                    },
                    "jql": {
                        "type": "string",
                        "description": "Custom JQL to aggregate story points",
                        "default": None
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum issues to inspect",
                        "default": 500
                    }
                },
                "required": []
            }
        },
        # Legacy tool schemas for backward compatibility
        {
            "name": "jira_create_story",
            "description": "Create a new story in Jira (legacy - use jira_create_issue)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_key": {
                        "type": "string",
                        "description": "Jira project key (e.g., 'PROJ')"
                    },
                    "summary": {
                        "type": "string",
                        "description": "Story summary/title"
                    },
                    "description": {
                        "type": "string",
                        "description": "Story description"
                    },
                    "story_points": {
                        "type": "integer",
                        "description": "Story points estimate",
                        "default": None
                    },
                    "assignee": {
                        "type": "string",
                        "description": "Assignee email or account ID",
                        "default": None
                    }
                },
                "required": ["project_key", "summary", "description"]
            }
        },
        {
            "name": "jira_get_sprint_data",
            "description": "Get sprint details and issues (legacy)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "sprint_id": {
                        "type": "integer",
                        "description": "Sprint ID (default: 1)",
                        "default": 1
                    }
                },
                "required": []
            }
        },
        {
            "name": "jira_get_team_capacity",
            "description": "Get team capacity and workload information (legacy)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "board_id": {
                        "type": "integer",
                        "description": "Jira board ID (default: 1)",
                        "default": 1
                    }
                },
                "required": []
            }
        },
        {
            "name": "jira_assign_task",
            "description": "Assign a task to a team member (legacy - use jira_assign_issue)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_key": {
                        "type": "string",
                        "description": "Task key (e.g., 'PROJ-123')"
                    },
                    "assignee_email": {
                        "type": "string",
                        "description": "Assignee email or account ID"
                    }
                },
                "required": ["task_key", "assignee_email"]
            }
        },
        {
            "name": "jira_get_user_workload",
            "description": "Get a user's assigned tasks and workload (legacy)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_email": {
                        "type": "string",
                        "description": "User email address"
                    }
                },
                "required": ["user_email"]
            }
        }
    ]


# ============================================================================
# Jira Client Class
# ============================================================================

class JiraClient:
    """Thin wrapper around Jira REST API v3 with comprehensive functionality."""

    def __init__(self, config: Optional[JiraConfig] = None) -> None:
        self.config = config or load_config()
        self._story_points_field_checked = False

        # Load job title mappings from environment variable for backward compatibility
        # Format: JIRA_USER_DESIGNATIONS='{"user@example.com": "Senior Developer", ...}'
        self.user_designations = self._load_user_designations()
    
    def _load_user_designations(self) -> Dict[str, str]:
        """
        Load user designation mappings from environment variable.

        Returns:
            Dictionary mapping email/accountId to job title
        """
        try:
            designations_json = os.getenv("JIRA_USER_DESIGNATIONS", "{}")
            return json.loads(designations_json)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JIRA_USER_DESIGNATIONS, using empty mapping")
            return {}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        url = f"{self.config.base_url}{path}"
        response = requests.request(
            method=method.upper(),
            url=url,
            auth=(self.config.email, self.config.api_token),
            params=params,
            json=json_body,
            timeout=15,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Jira API request failed ({response.status_code}): {response.text}"
            )
        return response

    def get_myself(self) -> Dict[str, Any]:
        return self._request("GET", "/rest/api/3/myself").json()

    def get_issue(self, issue_key: str) -> Dict[str, Any]:
        return self._request(
            "GET",
            f"/rest/api/3/issue/{issue_key}",
            params={"expand": "renderedFields"},
        ).json()

    def search(
        self,
        jql: str,
        *,
        max_results: int = 50,
        start_at: int = 0,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at,
        }
        if fields:
            params["fields"] = fields
        return self._request(
            "GET",
            "/rest/api/3/search/jql",
            params=params,
        ).json()

    def list_tasks(
        self,
        project_key: str,
        *,
        status: Optional[str] = None,
        limit: int = 20,
        start_at: int = 0,
    ) -> Dict[str, Any]:
        jql_parts = [f'project = "{project_key}"']
        if status:
            jql_parts.append(f'status = "{status}"')
        jql = " AND ".join(jql_parts) + " ORDER BY created DESC"

        return self.search(
            jql,
            max_results=limit,
            start_at=start_at,
            fields="summary,status,assignee,duedate",
        )

    @staticmethod
    def _make_adf_paragraph(text: str) -> Dict[str, Any]:
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                        }
                    ],
                }
            ],
        }

    def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str = "Task",
        description: Optional[str] = None,
        assignee_email: Optional[str] = None,
        story_points: Optional[float] = None,
        priority: Optional[str] = None,
    ) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        
        # Validate inputs
        if not summary or not summary.strip():
            raise ValueError("summary is required and cannot be empty")
        
        logger.info(f"Creating Jira issue: project={project_key}, summary='{summary[:50]}...', issue_type={issue_type}, has_description={bool(description)}, assignee_email={assignee_email}")
        
        payload: Dict[str, Any] = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary.strip(),  # Ensure summary is set correctly
                "issuetype": {"name": issue_type},
            }
        }
        
        # Set description if provided
        if description:
            description_text = description.strip() if isinstance(description, str) else str(description)
            if description_text:
                payload["fields"]["description"] = self._make_adf_paragraph(description_text)
                logger.info(f"Description set (length: {len(description_text)})")

        # Set assignee if provided
        if assignee_email:
            assignee_email = assignee_email.strip()
            logger.info(f"Looking up assignee: '{assignee_email}'")
            account_id = self._find_account_id_by_query(assignee_email)
            if not account_id:
                logger.warning(f"Could not find Jira user matching '{assignee_email}'. Issue will be created without assignee.")
                # Don't raise error - create issue without assignee and log warning
            else:
                payload["fields"]["assignee"] = {"accountId": account_id}
                logger.info(f"Assignee set: accountId={account_id} for email={assignee_email}")

        if story_points is not None:
            field_id = self._ensure_story_points_field_id()
            payload["fields"][field_id] = story_points

        if priority:
            payload["fields"]["priority"] = {"name": priority}

        logger.info(f"Creating Jira issue with payload fields: {list(payload['fields'].keys())}")
        logger.info(f"Payload summary (title): '{payload['fields'].get('summary', 'MISSING')[:100]}'")
        logger.info(f"Payload has description: {bool(payload['fields'].get('description'))}")
        logger.info(f"Payload has assignee: {bool(payload['fields'].get('assignee'))}")

        # Create the issue
        response_data = self._request(
            "POST",
            "/rest/api/3/issue",
            json_body=payload,
        ).json()
        
        issue_key = response_data.get("key")
        
        # If assignee was not set during creation but was provided, try to assign after creation
        if issue_key and assignee_email and not payload["fields"].get("assignee"):
            logger.info(f"Assignee was not set during creation. Attempting to assign {issue_key} to {assignee_email} after creation...")
            try:
                self.assign_issue(issue_key, email=assignee_email)
                logger.info(f"Successfully assigned {issue_key} to {assignee_email} after creation")
            except Exception as assign_error:
                logger.warning(f"Failed to assign {issue_key} to {assignee_email} after creation: {assign_error}")
        
        return response_data
    
    def assign_issue(
        self,
        issue_key: str,
        *,
        email: str,
    ) -> None:
        """
        Assign an issue to a user.

        Args:
            issue_key: Jira issue key (e.g., SCRUM-1).
            email: Convenience parameter; if provided, the first matching user's accountId
                is used. Requires permissions to search users.
        """
        if not email:
            raise ValueError("An email must be provided to assign an issue.")

        target_account_id = self._find_account_id_by_query(email)
        if not target_account_id:
            raise RuntimeError(
                f"Could not find a Jira user matching '{email}'."
            )

        self._request(
            "PUT",
            f"/rest/api/3/issue/{issue_key}/assignee",
            json_body={"accountId": target_account_id},
        )

    def set_story_points(self, issue_key: str, story_points: float) -> None:
        field_id = self._ensure_story_points_field_id()
        self._update_issue_fields(issue_key, {field_id: story_points})

    def set_priority(self, issue_key: str, priority: str) -> None:
        if not priority:
            raise ValueError("priority is required.")
        self._update_issue_fields(
            issue_key,
            {"priority": {"name": priority}},
        )

    def transition_issue(
        self,
        issue_key: str,
        target_status: str,
    ) -> Dict[str, Any]:
        """
        Move an issue to the desired workflow status.
        """
        if not issue_key or not issue_key.strip():
            raise ValueError("issue_key is required.")
        if not target_status or not target_status.strip():
            raise ValueError("target_status is required.")

        transitions_response = self._request(
            "GET",
            f"/rest/api/3/issue/{issue_key}/transitions",
        )
        transitions = transitions_response.json().get("transitions", [])

        chosen = None
        target_status_lower = target_status.strip().lower()
        for transition in transitions:
            status = transition.get("to") or {}
            name = status.get("name", "")
            if name.lower() == target_status_lower:
                chosen = transition
                break

        if not chosen:
            available = ", ".join(
                (t.get("to") or {}).get("name", "Unknown") for t in transitions
            )
            raise RuntimeError(
                f"Cannot transition {issue_key} to '{target_status}'. "
                f"Available: {available or 'none'}."
            )

        transition_id = chosen.get("id")
        response = self._request(
            "POST",
            f"/rest/api/3/issue/{issue_key}/transitions",
            json_body={"transition": {"id": transition_id}},
        )
        return response.json() if response.text else {"status": "ok"}

    def _find_account_id_by_query(self, query: str) -> Optional[str]:
        """Return the first accountId that matches the given user search query."""
        import logging
        logger = logging.getLogger(__name__)
        
        if not query or not query.strip():
            logger.warning("Empty query provided to _find_account_id_by_query")
            return None
        
        query = query.strip()
        logger.info(f"Searching for Jira user with query: '{query}'")
        
        try:
            response = self._request(
                "GET",
                "/rest/api/3/user/search",
                params={
                    "query": query,
                    "maxResults": 10,  # Increased to find more matches
                },
            )
            users: List[Dict[str, Any]] = response.json()
            
            if not users:
                logger.warning(f"No users found matching query: '{query}'")
                return None
            
            # Try exact email match first
            for user in users:
                email_address = user.get("emailAddress", "").lower()
                display_name = user.get("displayName", "").lower()
                query_lower = query.lower()
                
                if email_address == query_lower or display_name == query_lower:
                    account_id = user.get("accountId")
                    logger.info(f"Found exact match: email={email_address}, displayName={display_name}, accountId={account_id}")
                    return account_id
            
            # Fallback to first result
            account_id = users[0].get("accountId")
            email_address = users[0].get("emailAddress", "N/A")
            display_name = users[0].get("displayName", "N/A")
            logger.info(f"Using first match: email={email_address}, displayName={display_name}, accountId={account_id}")
            return account_id
            
        except Exception as e:
            logger.error(f"Error searching for user '{query}': {e}", exc_info=True)
            return None

    def _ensure_story_points_field_id(self) -> str:
        if self.config.story_points_field_id:
            return self.config.story_points_field_id

        if not self._story_points_field_checked:
            self._discover_story_points_field()
            self._story_points_field_checked = True

        if not self.config.story_points_field_id:
            raise RuntimeError(
                "Unable to determine Story Points field id. Set JIRA_STORY_POINTS_FIELD_ID."
            )
        return self.config.story_points_field_id

    def _discover_story_points_field(self) -> None:
        response = self._request("GET", "/rest/api/3/field")
        fields = response.json()
        candidates = [
            field
            for field in fields
            if isinstance(field, dict)
            and field.get("name")
            and "story point" in field["name"].lower()
        ]
        if candidates:
            field_id = candidates[0].get("id")
            if field_id:
                self.config.story_points_field_id = field_id

    def _update_issue_fields(self, issue_key: str, fields: Dict[str, Any]) -> None:
        self._request(
            "PUT",
            f"/rest/api/3/issue/{issue_key}",
            json_body={"fields": fields},
        )
    
    async def _make_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> tuple[int, Dict[str, Any]]:
        """
        Async HTTP request wrapper for Jira API.
        
        Returns:
            Tuple of (status_code, response_json)
        """
        url = f"{self.config.base_url}/{path}"
        
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                auth=(self.config.email, self.config.api_token),
                params=params,
                json=json,
                timeout=15.0,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            
            try:
                response_json = response.json() if response.text else {}
            except Exception:
                response_json = {}
            
            return response.status_code, response_json
    
    async def _fetch_user_profile(self, account_id: str) -> Dict[str, Any]:
        """Fetch full user profile from Jira."""
        try:
            status, data = await self._make_request(
                "GET",
                f"rest/api/3/user",
                params={"accountId": account_id}
            )
            if status >= 400:
                return {}
            return data
        except Exception as e:
            logger.warning(f"Failed to fetch user profile for {account_id}: {str(e)}")
            return {}
    
    def _map_designation_to_experience(self, job_title: str) -> str:
        """Map job title to experience level."""
        if not job_title:
            return "mid"
        
        job_title_lower = job_title.lower()
        
        # Senior indicators
        if any(indicator in job_title_lower for indicator in ["senior", "sr.", "lead", "principal", "architect", "staff"]):
            return "senior"
        
        # Junior indicators
        if any(indicator in job_title_lower for indicator in ["junior", "jr.", "intern", "trainee", "associate"]):
            return "junior"
        
        # Default to mid
        return "mid"

    def story_points_by_jql(
        self,
        jql: str,
        *,
        max_results: int = 1000,
    ) -> Dict[str, Any]:
        """
        Aggregate story points per assignee for issues matching the given JQL.
        """
        if not jql or not jql.strip():
            raise ValueError("JQL must be provided.")

        story_points_field = self._ensure_story_points_field_id()
        fields_param = f"summary,assignee,{story_points_field}"
        members: Dict[str, Dict[str, Any]] = {}
        unassigned: Dict[str, Any] = {
            "storyPoints": 0.0,
            "issueCount": 0,
            "unestimatedCount": 0,
            "issues": [],
        }
        total_issues = 0

        start_at = 0
        remaining = max_results
        while remaining > 0:
            batch_size = min(remaining, 100)
            response = self._request(
                "GET",
                "/rest/api/3/search/jql",
                params={
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": batch_size,
                    "fields": fields_param,
                },
            )
            data = response.json()
            issues = data.get("issues", [])
            total_issues += len(issues)

            for issue in issues:
                fields = issue.get("fields") or {}
                assignee = fields.get("assignee")
                story_points = fields.get(story_points_field)
                has_estimate = isinstance(story_points, (int, float))
                story_points_value = float(story_points) if has_estimate else 0.0

                issue_entry = {
                    "key": issue.get("key"),
                    "summary": fields.get("summary"),
                    "storyPoints": story_points if has_estimate else None,
                }

                if assignee and assignee.get("accountId"):
                    account_id = assignee["accountId"]
                    member_entry = members.setdefault(
                        account_id,
                        {
                            "accountId": account_id,
                            "displayName": assignee.get("displayName"),
                            "emailAddress": assignee.get("emailAddress"),
                            "storyPoints": 0.0,
                            "issueCount": 0,
                            "unestimatedCount": 0,
                            "issues": [],
                        },
                    )
                    member_entry["issueCount"] += 1
                    if has_estimate:
                        member_entry["storyPoints"] += story_points_value
                    else:
                        member_entry["unestimatedCount"] += 1
                    member_entry["issues"].append(issue_entry)
                else:
                    unassigned["issueCount"] += 1
                    if has_estimate:
                        unassigned["storyPoints"] += story_points_value
                    else:
                        unassigned["unestimatedCount"] += 1
                    unassigned["issues"].append(issue_entry)

            if len(issues) < batch_size:
                break

            start_at += len(issues)
            remaining -= len(issues)

        members_list = list(members.values())
        members_list.sort(key=lambda m: m["storyPoints"], reverse=True)

        result: Dict[str, Any] = {
            "jql": jql,
            "totalIssues": total_issues,
            "members": members_list,
        }

        if unassigned["issueCount"] or unassigned["storyPoints"]:
            result["unassigned"] = unassigned

        return result

    def story_points_by_sprint(
        self,
        sprint: str,
        *,
        project_key: Optional[str] = None,
        max_results: int = 1000,
    ) -> Dict[str, Any]:
        """
        Aggregate story points per assignee for a specific sprint.

        Args:
            sprint: Sprint identifier. Accepts a sprint ID (numeric), a full JQL clause
                such as "sprint in openSprints()", or a sprint name.
            project_key: Optional project key to scope the query.
        """
        if not sprint or not sprint.strip():
            raise ValueError("Sprint identifier must be provided.")

        sprint = sprint.strip()
        sprint_lower = sprint.lower()

        if sprint_lower.startswith("sprint =") or sprint_lower.startswith("sprint in"):
            sprint_clause = sprint
        elif sprint.isdigit():
            sprint_clause = f"sprint = {sprint}"
        else:
            sanitized = sprint.replace('"', '\\"')
            sprint_clause = f'sprint = "{sanitized}"'

        if project_key:
            jql = f'{sprint_clause} AND project = "{project_key}"'
        else:
            jql = sprint_clause

        result = self.story_points_by_jql(jql, max_results=max_results)
        result["sprint"] = sprint
        if project_key:
            result["project"] = project_key
        return result

    # Backward compatibility methods - these maintain the old async interface
    # but internally use the new sync methods
    async def create_story(
        self,
        project_key: str,
        summary: str,
        description: str,
        story_points: Optional[int] = None,
        assignee: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a Jira story."""
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}]
                        }
                    ]
                },
                "issuetype": {"name": "Story"}
            }
        }
        
        if story_points:
            payload["fields"]["customfield_10016"] = story_points
        
        assignee_set = False
        if assignee:
            assignee = assignee.strip()
            logger.info(f"Looking up assignee: '{assignee}'")
            
            # Search with more results to find exact match
            status_user, users = await self._make_request(
                "GET",
                "rest/api/3/user/search",
                params={"query": assignee, "maxResults": 10}  # Increased to find more matches
            )
            
            if status_user < 400 and users:
                assignee_lower = assignee.lower()
                # Try exact email match first
                for user in users:
                    email_address = user.get("emailAddress", "").lower()
                    display_name = user.get("displayName", "").lower()
                    
                    # Check for exact email match
                    if "@" in assignee and email_address == assignee_lower:
                        account_id = user.get("accountId")
                        if account_id:
                            payload["fields"]["assignee"] = {"accountId": account_id}
                            assignee_set = True
                            logger.info(f"Found exact email match: {email_address}, accountId={account_id}")
                            break
                    # Check for display name match (case-insensitive, partial)
                    elif not "@" in assignee and assignee_lower in display_name:
                        account_id = user.get("accountId")
                        if account_id:
                            payload["fields"]["assignee"] = {"accountId": account_id}
                            assignee_set = True
                            logger.info(f"Found display name match: {display_name}, accountId={account_id}")
                            break
                
                # Fallback: use first result if no exact match
                if not assignee_set and users:
                    account_id = users[0].get("accountId")
                    if account_id:
                        payload["fields"]["assignee"] = {"accountId": account_id}
                        assignee_set = True
                        email_address = users[0].get("emailAddress", "N/A")
                        display_name = users[0].get("displayName", "N/A")
                        logger.info(f"Using first match: email={email_address}, displayName={display_name}, accountId={account_id}")
            
            if not assignee_set:
                logger.warning(f"Could not find Jira user for assignee: '{assignee}'. Will attempt post-creation assignment.")
        
        try:
            logger.info(f"Creating Jira issue: project={project_key}, summary='{summary[:50]}...', has_assignee={assignee_set}")
            status, body = await self._make_request("POST", "rest/api/3/issue", json=payload)
            
            if status >= 400:
                error_msg = body.get("errorMessages", []) if isinstance(body, dict) else []
                errors = body.get("errors", {}) if isinstance(body, dict) else {}
                logger.error(f"Jira API error {status}: messages={error_msg}, errors={errors}")
                return {
                    "success": False,
                    "error": f"Jira API error {status}: {error_msg or errors}",
                    "details": body
                }
            
            issue_key = body.get("key")
            
            # If assignee was not set during creation but was provided, try to assign after creation
            if issue_key and assignee and not assignee_set:
                logger.info(f"Assignee was not set during creation. Attempting to assign {issue_key} to {assignee} after creation...")
                try:
                    # Use the synchronous assign_issue method via executor
                    import asyncio
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: self.assign_issue(issue_key, email=assignee)
                    )
                    logger.info(f"Successfully assigned {issue_key} to {assignee} after creation")
                    assignee_set = True  # Mark as set for return value
                except Exception as assign_error:
                    logger.warning(f"Failed to assign {issue_key} to {assignee} after creation: {assign_error}")
            
            # Fetch full issue details
            status2, issue_data = await self._make_request("GET", f"rest/api/3/issue/{issue_key}")
            
            if status2 >= 400:
                return {
                    "success": True,
                    "key": issue_key,
                    "summary": summary,
                    "partial": True
                }
            
            fields = issue_data.get("fields", {})
            assignee_info = fields.get("assignee")
            assignee_display = None
            if assignee_info:
                assignee_display = assignee_info.get("displayName") or assignee_info.get("emailAddress")
            
            logger.info(f"Created issue {issue_key}, assignee set: {bool(assignee_info)}, assignee_display: {assignee_display}")
            
            return {
                "success": True,
                "key": issue_data.get("key"),
                "id": issue_data.get("id"),
                "summary": fields.get("summary"),
                "status": fields.get("status", {}).get("name", "To Do"),
                "story_points": fields.get("customfield_10016"),
                "assignee": assignee_display
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "execution_error"
            }

    async def get_sprint_data(self, sprint_id: int = 1) -> Dict[str, Any]:
        """Get sprint details and issues."""
        try:
            # Get sprint details
            status, sprint_data = await self._make_request("GET", f"rest/agile/1.0/sprint/{sprint_id}")
            
            if status >= 400:
                return {
                    "success": False,
                    "error": f"Sprint {sprint_id} not found",
                    "status_code": status
                }
            
            # Get sprint issues
            status2, issues_data = await self._make_request("GET", f"rest/agile/1.0/sprint/{sprint_id}/issue")
            
            if status2 >= 400:
                return {
                    "success": True,
                    "sprint": sprint_data,
                    "issues": []
                }
            
            issues = issues_data.get("issues", [])
            
            # Calculate metrics
            total_sp = sum(i.get("fields", {}).get("customfield_10016", 0) or 0 for i in issues)
            completed_sp = sum(
                i.get("fields", {}).get("customfield_10016", 0) or 0
                for i in issues
                if i.get("fields", {}).get("status", {}).get("name") == "Done"
            )
            
            return {
                "success": True,
                "id": sprint_data.get("id"),
                "name": sprint_data.get("name"),
                "state": sprint_data.get("state"),
                "start_date": sprint_data.get("startDate"),
                "end_date": sprint_data.get("endDate"),
                "total_issues": len(issues),
                "total_story_points": total_sp,
                "completed_story_points": completed_sp,
                "issues": [
                    {
                        "key": i.get("key"),
                        "summary": i.get("fields", {}).get("summary"),
                        "status": i.get("fields", {}).get("status", {}).get("name"),
                        "story_points": i.get("fields", {}).get("customfield_10016")
                    }
                    for i in issues
                ]
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "execution_error"
            }

    async def get_team_capacity(self, board_id: int = 1) -> Dict[str, Any]:
        """Get team capacity information."""
        try:
            # Get active sprint
            status, sprints_data = await self._make_request(
                "GET",
                f"rest/agile/1.0/board/{board_id}/sprint",
                params={"state": "active"}
            )
            
            if status >= 400:
                return {"success": False, "error": "Board not found", "team": []}
            
            sprints = sprints_data.get("values", [])
            if not sprints:
                return {"success": True, "team": [], "message": "No active sprint"}
            
            sprint_id = sprints[0].get("id")
            
            # Get sprint issues
            status2, issues_data = await self._make_request(
                "GET",
                f"rest/agile/1.0/sprint/{sprint_id}/issue"
            )
            
            if status2 >= 400:
                return {"success": False, "error": "Failed to fetch issues", "team": []}
            
            issues = issues_data.get("issues", [])
            
            # Calculate capacity per assignee
            capacity_map = {}
            for issue in issues:
                assignee = issue.get("fields", {}).get("assignee")
                if assignee:
                    account_id = assignee.get("accountId")
                    if account_id not in capacity_map:
                        capacity_map[account_id] = {
                            "id": account_id,
                            "name": assignee.get("displayName"),
                            "email": assignee.get("emailAddress"),
                            "assigned_issues": 0,
                            "total_story_points": 0
                        }
                    
                    capacity_map[account_id]["assigned_issues"] += 1
                    sp = issue.get("fields", {}).get("customfield_10016", 0) or 0
                    capacity_map[account_id]["total_story_points"] += sp
            
            # Fetch user profiles to get job titles and designations
            team = []
            for member_data in capacity_map.values():
                account_id = member_data["id"]
                email = member_data.get("email", "")
                
                # Try to get job title from multiple sources:
                # 1. Manual mapping by email or account_id (from env variable)
                # 2. Jira user profile API (if available)
                # 3. Default to empty string
                
                job_title = ""
                
                # Check manual mappings first (most reliable)
                if email and email in self.user_designations:
                    job_title = self.user_designations[email]
                elif account_id in self.user_designations:
                    job_title = self.user_designations[account_id]
                else:
                    # Fetch full user profile as fallback
                    user_profile = await self._fetch_user_profile(account_id)
                    # Extract job title (can be in different fields depending on Jira setup)
                    job_title = user_profile.get("jobTitle") or user_profile.get("title") or ""
                
                # Map job title to experience level
                experience_level = self._map_designation_to_experience(job_title)
                
                # Log if job title is found
                if job_title:
                    logger.info(f"User {member_data.get('name')}: job_title='{job_title}', experience_level='{experience_level}'")
                else:
                    logger.warning(f"No job title found for {member_data.get('name')} ({email}), defaulting to 'mid' experience level")
                
                max_capacity = 40  # 40 hours/week
                current_load = member_data["total_story_points"]
                
                team.append({
                    **member_data,
                    "job_title": job_title,
                    "experience_level": experience_level,
                    "max_capacity": max_capacity,
                    "current_load": current_load,
                    "available_capacity": max(0, max_capacity - current_load)
                })
            
            return {
                "success": True,
                "sprint_id": sprint_id,
                "team": sorted(team, key=lambda x: x["total_story_points"], reverse=True)
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "execution_error",
                "team": []
            }

    async def assign_task(self, task_key: str, assignee_email: str) -> Dict[str, Any]:
        """Assign task to user."""
        try:
            # Resolve email to account ID if needed
            account_id = assignee_email
            if "@" in assignee_email:
                status, users = await self._make_request(
                    "GET",
                    "rest/api/3/user/search",
                    params={"query": assignee_email}
                )
                
                if status >= 400 or not users:
                    return {
                        "success": False,
                        "error": f"User {assignee_email} not found"
                    }
                
                account_id = users[0].get("accountId")
            
            # Assign the task
            status, _ = await self._make_request(
                "PUT",
                f"rest/api/3/issue/{task_key}/assignee",
                json={"accountId": account_id}
            )
            
            if status >= 400:
                return {
                    "success": False,
                    "error": f"Failed to assign task {task_key}"
                }
            
            return {
                "success": True,
                "key": task_key,
                "assignee": assignee_email,
                "assigned": True
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "execution_error"
            }

    async def get_user_workload(self, user_email: str) -> Dict[str, Any]:
        """Get user's workload."""
        try:
            # Search for user
            status, users = await self._make_request(
                "GET",
                "rest/api/3/user/search",
                params={"query": user_email}
            )
            
            if status >= 400 or not users:
                return {
                    "success": False,
                    "error": f"User {user_email} not found"
                }
            
            account_id = users[0].get("accountId")
            
            # Get assigned issues
            jql = f"assignee = {account_id} AND status != Done"
            status2, issues_data = await self._make_request(
                "GET",
                "rest/api/3/search",
                params={"jql": jql, "fields": "summary,status,customfield_10016"}
            )
            
            if status2 >= 400:
                return {
                    "success": False,
                    "error": "Failed to fetch workload"
                }
            
            issues = issues_data.get("issues", [])
            total_sp = sum(i.get("fields", {}).get("customfield_10016", 0) or 0 for i in issues)
            
            return {
                "success": True,
                "user": user_email,
                "account_id": account_id,
                "assigned_issues": len(issues),
                "total_story_points": total_sp,
                "issues": [
                    {
                        "key": i.get("key"),
                        "summary": i.get("fields", {}).get("summary"),
                        "status": i.get("fields", {}).get("status", {}).get("name"),
                        "story_points": i.get("fields", {}).get("customfield_10016")
                    }
                    for i in issues
                ]
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "execution_error"
            }


# ============================================================================
# Tool Implementation Functions - Called by MCP Server
# ============================================================================

async def jira_verify_credentials_impl() -> Dict[str, Any]:
    """Implementation for verifying Jira credentials."""
    try:
        client = JiraClient()
        data = client.get_myself()
        return {
            "success": True,
            "data": data,
            "meta": {"request_id": None}
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": {
                "message": str(e),
                "code": "JIRA_ERROR",
                "details": None
            },
            "meta": {"request_id": None}
        }


async def jira_get_issue_impl(issue_key: str) -> Dict[str, Any]:
    """Implementation for getting a Jira issue."""
    try:
        client = JiraClient()
        data = client.get_issue(issue_key)
        return {
            "success": True,
            "data": data,
            "meta": {"request_id": None}
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": {
                "message": str(e),
                "code": "JIRA_ERROR",
                "details": None
            },
            "meta": {"request_id": None}
        }


async def jira_search_issues_impl(
    jql: str,
    max_results: int = 50,
    start_at: int = 0,
    fields: Optional[str] = None,
) -> Dict[str, Any]:
    """Implementation for searching Jira issues."""
    try:
        client = JiraClient()
        data = client.search(jql, max_results=max_results, start_at=start_at, fields=fields)
        return {
            "success": True,
            "data": data,
            "meta": {"request_id": None}
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": {
                "message": str(e),
                "code": "JIRA_ERROR",
                "details": None
            },
            "meta": {"request_id": None}
        }


async def jira_list_tasks_impl(
    project_key: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
    start_at: int = 0,
) -> Dict[str, Any]:
    """Implementation for listing tasks in a project."""
    try:
        client = JiraClient()
        data = client.list_tasks(
            project_key=project_key or client.config.default_project,
            status=status,
            limit=limit,
            start_at=start_at,
        )
        return {
            "success": True,
            "data": data,
            "meta": {"request_id": None}
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": {
                "message": str(e),
                "code": "JIRA_ERROR",
                "details": None
            },
            "meta": {"request_id": None}
        }


async def jira_create_issue_impl(
    project_key: Optional[str],
    summary: str,
    issue_type: str = "Task",
    description: Optional[str] = None,
    assignee_email: Optional[str] = None,
    story_points: Optional[float] = None,
    priority: Optional[str] = None,
) -> Dict[str, Any]:
    """Implementation for creating a Jira issue."""
    try:
        client = JiraClient()
        # Ensure we have a valid project_key
        final_project_key = project_key or client.config.default_project
        if not final_project_key or not final_project_key.strip():
            return {
                "success": False,
                "data": None,
                "error": {
                    "message": "Jira API request failed (400): {\"errorMessages\":[],\"errors\":{\"project\":\"valid project is required\"}}",
                    "code": "JIRA_ERROR",
                    "details": "Project key is required but was not provided. Please provide project_key parameter or set JIRA_DEFAULT_PROJECT environment variable."
                },
                "meta": {"request_id": None}
            }
        
        data = client.create_issue(
            project_key=final_project_key,
            summary=summary,
            issue_type=issue_type,
            description=description,
            assignee_email=assignee_email,
            story_points=story_points,
            priority=priority,
        )
        return {
            "success": True,
            "data": data,
            "meta": {"request_id": None}
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": {
                "message": str(e),
                "code": "JIRA_ERROR",
                "details": None
            },
            "meta": {"request_id": None}
        }


async def jira_assign_issue_impl(issue_key: str, email: str) -> Dict[str, Any]:
    """Implementation for assigning a Jira issue."""
    try:
        client = JiraClient()
        client.assign_issue(issue_key, email=email)
        return {
            "success": True,
            "data": {"status": "ok", "issue": issue_key, "assigned_to": email},
            "meta": {"request_id": None}
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": {
                "message": str(e),
                "code": "JIRA_ERROR",
                "details": None
            },
            "meta": {"request_id": None}
        }


async def jira_set_story_points_impl(issue_key: str, story_points: float) -> Dict[str, Any]:
    """Implementation for setting story points."""
    try:
        client = JiraClient()
        client.set_story_points(issue_key, story_points)
        return {
            "success": True,
            "data": {"status": "ok", "issue": issue_key, "story_points": story_points},
            "meta": {"request_id": None}
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": {
                "message": str(e),
                "code": "JIRA_ERROR",
                "details": None
            },
            "meta": {"request_id": None}
        }


async def jira_set_priority_impl(issue_key: str, priority: str) -> Dict[str, Any]:
    """Implementation for setting priority."""
    try:
        client = JiraClient()
        client.set_priority(issue_key, priority)
        return {
            "success": True,
            "data": {"status": "ok", "issue": issue_key, "priority": priority},
            "meta": {"request_id": None}
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": {
                "message": str(e),
                "code": "JIRA_ERROR",
                "details": None
            },
            "meta": {"request_id": None}
        }


async def jira_transition_issue_impl(issue_key: str, target_status: str) -> Dict[str, Any]:
    """Implementation for transitioning an issue."""
    try:
        client = JiraClient()
        data = client.transition_issue(issue_key, target_status)
        return {
            "success": True,
            "data": data,
            "meta": {"request_id": None}
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": {
                "message": str(e),
                "code": "JIRA_ERROR",
                "details": None
            },
            "meta": {"request_id": None}
        }


async def jira_story_points_summary_impl(
    sprint: Optional[str] = None,
    project_key: Optional[str] = None,
    jql: Optional[str] = None,
    max_results: int = 500,
) -> Dict[str, Any]:
    """Implementation for story points summary."""
    try:
        client = JiraClient()
        if jql:
            data = client.story_points_by_jql(jql, max_results=max_results)
        elif sprint:
            data = client.story_points_by_sprint(
                sprint, project_key=project_key, max_results=max_results
            )
        else:
            raise RuntimeError("Provide either sprint or jql parameter.")
        return {
            "success": True,
            "data": data,
            "meta": {"request_id": None}
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": {
                "message": str(e),
                "code": "JIRA_ERROR",
                "details": None
            },
            "meta": {"request_id": None}
        }


# Legacy implementation functions for backward compatibility
async def jira_create_story_impl(
    project_key: str,
    summary: str,
    description: str,
    story_points: Optional[int] = None,
    assignee: Optional[str] = None
) -> Dict[str, Any]:
    """Legacy implementation for creating a Jira story - delegates to create_issue."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Validate and log inputs to ensure correct mapping
    if not summary or not summary.strip():
        raise ValueError("summary parameter is required and cannot be empty")
    
    summary_text = summary.strip()
    description_text = description.strip() if description else ""
    
    logger.info(f"jira_create_story_impl called:")
    logger.info(f"  project_key: '{project_key}'")
    logger.info(f"  summary (will go to title field): '{summary_text[:80]}...'")
    logger.info(f"  description (will go to description field): length={len(description_text)}")
    logger.info(f"  story_points: {story_points}")
    logger.info(f"  assignee: '{assignee}'")
    
    return await jira_create_issue_impl(
        project_key=project_key,
        summary=summary_text,  # Explicitly pass as summary (title)
        issue_type="Story",
        description=description_text if description_text else None,  # Explicitly pass as description
        assignee_email=assignee.strip() if assignee else None,
        story_points=float(story_points) if story_points else None,
    )


async def jira_get_sprint_data_impl(sprint_id: int = 1) -> Dict[str, Any]:
    """Legacy implementation for getting sprint data."""
    return await jira_story_points_summary_impl(sprint=str(sprint_id))


async def jira_get_team_capacity_impl(board_id: int = 1) -> Dict[str, Any]:
    """Legacy implementation for getting team capacity."""
    try:
        client = JiraClient()
        # Get active sprint for the board
        status, sprints_data = await client._make_request("GET", f"rest/agile/1.0/board/{board_id}/sprint", params={"state": "active"})
        if status >= 400 or not sprints_data.get("values"):
            return {
                "success": False,
                "error": "No active sprint found",
                "team": []
            }

        sprint_id = sprints_data["values"][0]["id"]
        data = client.story_points_by_sprint(str(sprint_id))

        # Transform to legacy format
        team = []
        for member in data.get("members", []):
            # Map experience level
            job_title = member.get("displayName", "")
            if "senior" in job_title.lower() or "sr" in job_title.lower():
                experience_level = "senior"
            elif "junior" in job_title.lower() or "jr" in job_title.lower():
                experience_level = "junior"
            else:
                experience_level = "mid"

            team.append({
                "id": member.get("accountId"),
                "name": member.get("displayName"),
                "email": member.get("emailAddress"),
                "job_title": job_title,
                "experience_level": experience_level,
                "max_capacity": 40,  # Default
                "current_load": member.get("storyPoints", 0),
                "available_capacity": 40 - member.get("storyPoints", 0),
                "assigned_issues": member.get("issueCount", 0),
                "total_story_points": member.get("storyPoints", 0)
            })

        return {
            "success": True,
            "data": {
                "sprint_id": sprint_id,
                "team": sorted(team, key=lambda x: x["total_story_points"], reverse=True)
            },
            "meta": {"request_id": None}
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": {
                "message": str(e),
                "code": "JIRA_ERROR",
                "details": None
            },
            "meta": {"request_id": None}
        }


async def jira_assign_task_impl(task_key: str, assignee_email: str) -> Dict[str, Any]:
    """Legacy implementation for assigning a task."""
    return await jira_assign_issue_impl(task_key, assignee_email)


async def jira_get_user_workload_impl(user_email: str) -> Dict[str, Any]:
    """Legacy implementation for getting user workload."""
    try:
        client = JiraClient()
        # Find user account ID
        status, users = await client._make_request("GET", "rest/api/3/user/search", params={"query": user_email})
        if status >= 400 or not users:
            return {
                "success": False,
                "error": f"User {user_email} not found"
            }

        account_id = users[0].get("accountId")
        jql = f"assignee = {account_id} AND status != Done"
        data = client.search(jql, fields="summary,status,customfield_10016")

        total_sp = sum(i.get("fields", {}).get("customfield_10016", 0) or 0 for i in data.get("issues", []))

        return {
            "success": True,
            "data": {
                "user": user_email,
                "account_id": account_id,
                "assigned_issues": len(data.get("issues", [])),
                "total_story_points": total_sp,
                "issues": [
                    {
                        "key": i.get("key"),
                        "summary": i.get("fields", {}).get("summary"),
                        "status": i.get("fields", {}).get("status", {}).get("name"),
                        "story_points": i.get("fields", {}).get("customfield_10016")
                    }
                    for i in data.get("issues", [])
                ]
            },
            "meta": {"request_id": None}
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": {
                "message": str(e),
                "code": "JIRA_ERROR",
                "details": None
            },
            "meta": {"request_id": None}
        }

