"""
MCP Server for AutoScrum Tools

Registers all tools (ServiceNow, Jira, Zoom) with FastMCP for standardized tool access.
Provides tool schemas and execution functions for the orchestrator.
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List, Callable
import json

try:
    from mcp.server.fastmcp import FastMCP
    FASTMCP_AVAILABLE = True
except ImportError:
    FASTMCP_AVAILABLE = False
    FastMCP = None

from .tools.servicenow_client import (
    ServiceNowClient,
    servicenow_create_incident_impl,
    servicenow_list_incidents_impl,
    servicenow_get_incident_by_number_impl,
    servicenow_update_incident_impl,
    servicenow_list_kb_articles_impl,
    servicenow_query_table_impl,
    _get_servicenow_tool_schemas
)
from .tools.jira_client import (
    jira_verify_credentials_impl,
    jira_get_issue_impl,
    jira_search_issues_impl,
    jira_list_tasks_impl,
    jira_create_issue_impl,
    jira_assign_issue_impl,
    jira_set_story_points_impl,
    jira_set_priority_impl,
    jira_transition_issue_impl,
    jira_story_points_summary_impl,
    jira_create_story_impl,
    jira_get_sprint_data_impl,
    jira_get_team_capacity_impl,
    jira_assign_task_impl,
    jira_get_user_workload_impl,
    _get_jira_tool_schemas
)

logger = logging.getLogger(__name__)

# Create FastMCP server instance if available
mcp = FastMCP("AutoScrum Tools") if FASTMCP_AVAILABLE else None

# Tool registry for execution
_tool_executors: Dict[str, Callable] = {}


def get_mcp_server() -> Optional[FastMCP]:
    """Get the MCP server instance."""
    return mcp


def register_all_tools():
    """Register all tools with the MCP server."""
    if not FASTMCP_AVAILABLE:
        logger.warning("FastMCP not available - tools will be registered in registry only")
    
    logger.info("🔧 Registering tools with FastMCP...")
    
    # Register ServiceNow tools
    register_servicenow_tools()
    
    # Register Jira tools
    register_jira_tools()
    
    logger.info("✅ All tools registered with FastMCP")


def register_servicenow_tools():
    """Register ServiceNow tools with FastMCP."""
    logger.info("📝 Registering ServiceNow tools...")
    
    async def servicenow_create_incident_executor(
        short_description: str,
        description: str = "",
        assignment_group: str = "",
        priority: str = "",
        caller_id: str = "",
        contact_type: str = "self-service"
    ) -> dict:
        """Create a new ServiceNow incident/ticket."""
        result = await servicenow_create_incident_impl(
            short_description=short_description,
            description=description,
            assignment_group=assignment_group,
            priority=priority,
            caller_id=caller_id,
            contact_type=contact_type
        )
        return result
    
    # Register executor
    _tool_executors["servicenow_create_incident"] = servicenow_create_incident_executor
    
    # Register with FastMCP if available
    if mcp:
        @mcp.tool()
        async def servicenow_create_incident(
            short_description: str,
            description: str = "",
            assignment_group: str = "",
            priority: str = "",
            caller_id: str = "",
            contact_type: str = "self-service"
        ) -> dict:
            return await servicenow_create_incident_executor(
                short_description=short_description,
                description=description,
                assignment_group=assignment_group,
                priority=priority,
                caller_id=caller_id,
                contact_type=contact_type
            )
    
    async def servicenow_list_incidents_executor(
        sysparm_query: str = "active=true",
        sysparm_fields: str = "",
        sysparm_limit: int = 50,
        sysparm_offset: int = 0
    ) -> dict:
        """Query ServiceNow incidents/tickets."""
        return await servicenow_list_incidents_impl(
            sysparm_query=sysparm_query,
            sysparm_fields=sysparm_fields,
            sysparm_limit=sysparm_limit,
            sysparm_offset=sysparm_offset
        )
    
    async def servicenow_get_incident_by_number_executor(
        number: str,
        sysparm_fields: str = ""
    ) -> dict:
        """Retrieve a specific ServiceNow incident by its number."""
        return await servicenow_get_incident_by_number_impl(
            number=number,
            sysparm_fields=sysparm_fields
        )
    
    async def servicenow_update_incident_executor(
        sys_id: str,
        state: str = "",
        assigned_to: str = "",
        work_notes: str = "",
        close_code: str = "",
        close_notes: str = ""
    ) -> dict:
        """Update an existing ServiceNow incident."""
        return await servicenow_update_incident_impl(
            sys_id=sys_id,
            state=state,
            assigned_to=assigned_to,
            work_notes=work_notes,
            close_code=close_code,
            close_notes=close_notes
        )
    
    async def servicenow_list_kb_articles_executor(
        keywords: str = "",
        ci_sys_id: str = "",
        sysparm_limit: int = 20
    ) -> dict:
        """Search ServiceNow Knowledge Base articles."""
        return await servicenow_list_kb_articles_impl(
            keywords=keywords,
            ci_sys_id=ci_sys_id,
            sysparm_limit=sysparm_limit
        )
    
    async def servicenow_query_table_executor(
        table_name: str,
        sysparm_query: str = "",
        sysparm_fields: str = "",
        sysparm_limit: int = 50,
        sysparm_offset: int = 0
    ) -> dict:
        """Query any ServiceNow table."""
        return await servicenow_query_table_impl(
            table_name=table_name,
            sysparm_query=sysparm_query,
            sysparm_fields=sysparm_fields,
            sysparm_limit=sysparm_limit,
            sysparm_offset=sysparm_offset
        )
    
    # Register executors
    _tool_executors["servicenow_list_incidents"] = servicenow_list_incidents_executor
    _tool_executors["servicenow_get_incident_by_number"] = servicenow_get_incident_by_number_executor
    _tool_executors["servicenow_update_incident"] = servicenow_update_incident_executor
    _tool_executors["servicenow_list_kb_articles"] = servicenow_list_kb_articles_executor
    _tool_executors["servicenow_query_table"] = servicenow_query_table_executor
    
    # Register with FastMCP if available
    if mcp:
        @mcp.tool()
        async def servicenow_list_incidents(
            sysparm_query: str = "active=true",
            sysparm_fields: str = "",
            sysparm_limit: int = 50,
            sysparm_offset: int = 0
        ) -> dict:
            return await servicenow_list_incidents_executor(
                sysparm_query=sysparm_query,
                sysparm_fields=sysparm_fields,
                sysparm_limit=sysparm_limit,
                sysparm_offset=sysparm_offset
            )
        
        @mcp.tool()
        async def servicenow_get_incident_by_number(
            number: str,
            sysparm_fields: str = ""
        ) -> dict:
            return await servicenow_get_incident_by_number_executor(
                number=number,
                sysparm_fields=sysparm_fields
            )
        
        @mcp.tool()
        async def servicenow_update_incident(
            sys_id: str,
            state: str = "",
            assigned_to: str = "",
            work_notes: str = "",
            close_code: str = "",
            close_notes: str = ""
        ) -> dict:
            return await servicenow_update_incident_executor(
                sys_id=sys_id,
                state=state,
                assigned_to=assigned_to,
                work_notes=work_notes,
                close_code=close_code,
                close_notes=close_notes
            )
        
        @mcp.tool()
        async def servicenow_list_kb_articles(
            keywords: str = "",
            ci_sys_id: str = "",
            sysparm_limit: int = 20
        ) -> dict:
            return await servicenow_list_kb_articles_executor(
                keywords=keywords,
                ci_sys_id=ci_sys_id,
                sysparm_limit=sysparm_limit
            )
        
        @mcp.tool()
        async def servicenow_query_table(
            table_name: str,
            sysparm_query: str = "",
            sysparm_fields: str = "",
            sysparm_limit: int = 50,
            sysparm_offset: int = 0
        ) -> dict:
            return await servicenow_query_table_executor(
                table_name=table_name,
                sysparm_query=sysparm_query,
                sysparm_fields=sysparm_fields,
                sysparm_limit=sysparm_limit,
                sysparm_offset=sysparm_offset
            )
    
    logger.info("✅ ServiceNow tools registered")


def register_jira_tools():
    """Register Jira tools with FastMCP."""
    logger.info("📝 Registering Jira tools...")
    
    # Register all implementation functions directly as executors
    _tool_executors["jira_verify_credentials"] = jira_verify_credentials_impl
    _tool_executors["jira_get_issue"] = jira_get_issue_impl
    _tool_executors["jira_search_issues"] = jira_search_issues_impl
    _tool_executors["jira_list_tasks"] = jira_list_tasks_impl
    _tool_executors["jira_create_issue"] = jira_create_issue_impl
    _tool_executors["jira_assign_issue"] = jira_assign_issue_impl
    _tool_executors["jira_set_story_points"] = jira_set_story_points_impl
    _tool_executors["jira_set_priority"] = jira_set_priority_impl
    _tool_executors["jira_transition_issue"] = jira_transition_issue_impl
    _tool_executors["jira_story_points_summary"] = jira_story_points_summary_impl
    _tool_executors["jira_create_story"] = jira_create_story_impl
    _tool_executors["jira_get_sprint_data"] = jira_get_sprint_data_impl
    _tool_executors["jira_get_team_capacity"] = jira_get_team_capacity_impl
    _tool_executors["jira_assign_task"] = jira_assign_task_impl
    _tool_executors["jira_get_user_workload"] = jira_get_user_workload_impl
    
    # Apply FastMCP decorators with explicit parameter definitions for better schema extraction
    if mcp:
        @mcp.tool()
        async def jira_get_issue(issue_key: str) -> dict:
            """
            Fetch a Jira issue by its exact issue key.
            
            REQUIRES the full issue key (e.g., SCRUM-1, PROJ-123).
            If you only have a story name or title, use jira_search_issues instead.
            """
            return await jira_get_issue_impl(issue_key=issue_key)
        
        @mcp.tool()
        async def jira_search_issues(
            jql: str,
            max_results: int = 50,
            start_at: int = 0,
            fields: Optional[str] = None
        ) -> dict:
            """
            Search for Jira issues using a JQL query.
            
            Use this when you have a story name, title, or other details but not the exact issue key.
            Example JQL: 'summary ~ \"Task 3\"' to find issues with 'Task 3' in the summary.
            """
            return await jira_search_issues_impl(
                jql=jql,
                max_results=max_results,
                start_at=start_at,
                fields=fields
            )
        
        # Decorate other implementation functions
        mcp.tool()(jira_verify_credentials_impl)
        mcp.tool()(jira_list_tasks_impl)
        mcp.tool()(jira_create_issue_impl)
        mcp.tool()(jira_assign_issue_impl)
        mcp.tool()(jira_set_story_points_impl)
        mcp.tool()(jira_set_priority_impl)
        mcp.tool()(jira_transition_issue_impl)
        mcp.tool()(jira_story_points_summary_impl)
        mcp.tool()(jira_create_story_impl)
        mcp.tool()(jira_get_sprint_data_impl)
        mcp.tool()(jira_get_team_capacity_impl)
        mcp.tool()(jira_assign_task_impl)
        mcp.tool()(jira_get_user_workload_impl)
    
    logger.info("✅ Jira tools registered")




def get_tool_schemas() -> list:
    """Get all tool schemas for function calling."""
    schemas = []
    
    # Get ServiceNow schemas
    servicenow_schemas = _get_servicenow_tool_schemas()
    schemas.extend(servicenow_schemas)
    
    # Get Jira schemas
    jira_schemas = _get_jira_tool_schemas()
    # Wrap in function format for OpenAI
    for schema in jira_schemas:
        schemas.append({
            "type": "function",
            "function": schema
        })
    
    return schemas


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool by name with given arguments.
    
    Args:
        tool_name: Name of the tool to execute
        arguments: Dictionary of arguments for the tool
        
    Returns:
        Tool execution result
    """
    if tool_name not in _tool_executors:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}",
            "error_type": "unknown_tool"
        }
    
    import asyncio
    executor = _tool_executors[tool_name]
    
    # Run async executor
    try:
        if asyncio.iscoroutinefunction(executor):
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, we need to use a different approach
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor_pool:
                    future = executor_pool.submit(asyncio.run, executor(**arguments))
                    result = future.result()
            else:
                result = loop.run_until_complete(executor(**arguments))
        else:
            result = executor(**arguments)
        
        return result
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "error_type": "execution_error"
        }


async def execute_tool_async(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool asynchronously by name with given arguments.
    
    Args:
        tool_name: Name of the tool to execute
        arguments: Dictionary of arguments for the tool
        
    Returns:
        Tool execution result
    """
    if tool_name not in _tool_executors:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}",
            "error_type": "unknown_tool"
        }
    
    executor = _tool_executors[tool_name]
    
    # Validate required arguments for specific tools
    if tool_name == "jira_get_issue":
        if not arguments.get("issue_key"):
            return {
                "success": False,
                "data": None,
                "error": {
                    "message": "issue_key is required. If you only have a story name, use jira_search_issues with a JQL query like 'summary ~ \"story name\"' to find the issue first.",
                    "code": "MISSING_PARAMETER",
                    "details": "Use jira_search_issues to search for issues by name, then use jira_get_issue with the found issue key."
                },
                "meta": {"request_id": None}
            }
    
    if tool_name == "jira_search_issues":
        if not arguments.get("jql"):
            return {
                "success": False,
                "data": None,
                "error": {
                    "message": "jql parameter is required. Example: To find a story named 'Task 3', use JQL: 'summary ~ \"Task 3\"' or 'text ~ \"Task 3\"'.",
                    "code": "MISSING_PARAMETER",
                    "details": "The jql parameter is required. Use JQL syntax like 'summary ~ \"story name\"' to search by story name."
                },
                "meta": {"request_id": None}
            }
    
    try:
        if asyncio.iscoroutinefunction(executor):
            result = await executor(**arguments)
        else:
            result = executor(**arguments)
        
        return result
    except TypeError as e:
        # Handle missing required arguments
        error_msg = str(e)
        if "missing" in error_msg and "required" in error_msg:
            logger.error(f"Missing required argument for {tool_name}: {error_msg}")
            return {
                "success": False,
                "data": None,
                "error": {
                    "message": f"Missing required argument: {error_msg}. Please provide all required parameters.",
                    "code": "MISSING_PARAMETER",
                    "details": f"For {tool_name}, check the tool schema for required parameters."
                },
                "meta": {"request_id": None}
            }
        raise
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "error_type": "execution_error"
        }


# Initialize tools on module import
register_all_tools()

