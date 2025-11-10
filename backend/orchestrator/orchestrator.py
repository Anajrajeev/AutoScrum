"""
LangGraph Orchestrator - Central coordination for AutoScrum agents.

Uses LangGraph StateGraph for proper workflow orchestration.
Optimized memory usage - only stores essential state, not full workflow history.
"""

from typing import Dict, Any, Optional, List, TypedDict, Annotated
from enum import Enum
import asyncio
from datetime import datetime
import json
import operator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agents import (
    DynamicContextAgent,
    StoryCreatorAgent,
    PrioritizationAgent
)
from memory.redis_client import get_redis_client
from db.database import get_db
from db.models import AgentLog
from mcp_tools import JiraClient, ServiceNowClient
from mcp_tools.mcp_server import get_tool_schemas, execute_tool_async


class AgentState(str, Enum):
    """Agent execution states."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING = "waiting"


class WorkflowType(str, Enum):
    """Types of orchestration workflows."""
    FEATURE_CLARIFICATION = "feature_clarification"
    STORY_GENERATION = "story_generation"
    TASK_PRIORITIZATION = "task_prioritization"
    FULL_PIPELINE = "full_pipeline"


# ============================================================================
# LangGraph State Definitions
# ============================================================================

class FeatureWorkflowState(TypedDict):
    """State for feature clarification workflow."""
    feature_id: int
    feature_name: str
    feature_description: str
    user_response: Optional[str]
    conversation_history: Annotated[List[Dict[str, str]], operator.add]
    current_question: Optional[str]
    is_complete: bool
    context_summary: Optional[Dict[str, Any]]
    workflow_id: str


class StoryGenerationState(TypedDict):
    """State for story generation workflow."""
    feature_id: int
    context: Dict[str, Any]
    stories: Annotated[List[Dict[str, Any]], operator.add]
    epic: Optional[Dict[str, Any]]
    workflow_id: str
    status: str


class Orchestrator:
    """
    LangGraph-based orchestrator for multi-agent coordination.
    
    Uses LangGraph StateGraph for proper workflow management.
    Optimized memory - only stores essential state in Redis.
    """

    def __init__(self):
        """Initialize orchestrator with agents and clients."""
        # Initialize agents
        self.dynamic_agent = DynamicContextAgent()
        self.story_agent = StoryCreatorAgent()
        self.prioritization_agent = PrioritizationAgent()
        
        # Initialize MCP clients
        self.jira_client = JiraClient()
        self.servicenow_client = ServiceNowClient()
        
        # Initialize memory (lightweight usage)
        self.redis_client = get_redis_client()
        
        # Build LangGraph workflows
        self._build_feature_workflow_graph()
        self._build_story_generation_graph()
        
        # Minimal state tracking (only active workflow IDs)
        self.active_workflows: Dict[str, str] = {}  # workflow_id -> workflow_type

    # ========================================================================
    # LangGraph Workflow: Feature Clarification
    # ========================================================================

    def _build_feature_workflow_graph(self):
        """Build LangGraph for feature clarification workflow.

        STRICT LIMIT: DynamicContextAgent enforces maximum 5 questions per feature.
        After 5 questions, clarification is forced to complete regardless of LLM determination.
        """
        workflow = StateGraph(FeatureWorkflowState)
        
        # Add nodes
        workflow.add_node("clarify", self._clarify_node)
        workflow.add_node("check_complete", self._check_complete_node)
        
        # Set entry point
        workflow.set_entry_point("clarify")
        
        # Add edges
        workflow.add_conditional_edges(
            "clarify",
            self._should_continue_clarification,
            {
                "continue": END,  # Stop after asking question, wait for user response
                "complete": "check_complete",
                "end": END
            }
        )
        workflow.add_edge("check_complete", END)
        
        # Compile with memory
        memory = MemorySaver()
        self.feature_graph = workflow.compile(checkpointer=memory)

    async def _clarify_node(self, state: FeatureWorkflowState) -> FeatureWorkflowState:
        """Node: Run clarification agent."""
        try:
            # Get conversation history from state
            conversation_history = state.get("conversation_history", [])
            
            result = await self.dynamic_agent.execute({
                "feature_id": state["feature_id"],
                "feature_name": state.get("feature_name"),
                "feature_description": state.get("feature_description"),
                "user_response": state.get("user_response"),
                "conversation_history": conversation_history
            })
            
            # Update state (minimal - only essential data)
            state["current_question"] = result.get("question")
            state["is_complete"] = result.get("is_complete", False)
            state["context_summary"] = result.get("context_summary")
            
            # Update conversation history from agent result (agent manages it)
            if result.get("conversation_history"):
                state["conversation_history"] = result["conversation_history"]
            
            # Only save to Redis if not complete (when complete, _check_complete_node handles it)
            if not state["is_complete"]:
                # Store workflow state for continuation
                context_to_store = {
                    "feature_name": state.get("feature_name"),
                    "feature_description": state.get("feature_description"),
                    "is_complete": False,
                    "last_question": state["current_question"],
                    "workflow_id": state.get("workflow_id")
                }
                
                self.redis_client.set_feature_context(
                    state["feature_id"],
                    context_to_store,
                    ttl=3600  # 1 hour
                )
            
        except Exception as e:
            state["is_complete"] = True  # Fail gracefully
            state["current_question"] = f"Error: {str(e)}"
        
        return state

    async def _check_complete_node(self, state: FeatureWorkflowState) -> FeatureWorkflowState:
        """Node: Finalize clarification."""
        import logging
        logger = logging.getLogger(__name__)
        
        context_summary = state.get("context_summary")
        
        # Validate that context_summary has all required fields
        required_fields = ["goals", "user_personas", "key_features", "acceptance_criteria", "technical_constraints", "success_metrics"]
        
        if context_summary and isinstance(context_summary, dict):
            has_all_fields = all(field in context_summary for field in required_fields)
            
            if has_all_fields:
                logger.info(f"✅ [CHECK COMPLETE] Context summary has all required fields")
                # Merge context_summary with feature metadata
                final_context = {
                    "feature_name": state.get("feature_name"),
                    "feature_description": state.get("feature_description"),
                    "is_complete": True
                }
                # Add all fields from context_summary
                final_context.update(context_summary)
                
                # Store complete context with all required fields
                self.redis_client.set_feature_context(
                    state["feature_id"],
                    final_context,
                    ttl=86400  # 24 hours for completed features
                )
                logger.info(f"✅ [CHECK COMPLETE] Saved complete context to Redis with all fields")
            else:
                missing_fields = [f for f in required_fields if f not in context_summary]
                logger.warning(f"⚠️ [CHECK COMPLETE] Context summary missing fields: {missing_fields}")
                # Do NOT mark as complete - keep it incomplete
                state["is_complete"] = False
                state["current_question"] = "Could you provide more details about the missing aspects?"
        else:
            logger.error(f"❌ [CHECK COMPLETE] No context_summary or invalid format")
            # Do NOT mark as complete - keep it incomplete
            state["is_complete"] = False
            state["current_question"] = "I need to gather more information. Could you summarize the feature requirements?"
        
        return state

    def _should_continue_clarification(self, state: FeatureWorkflowState) -> str:
        """Conditional edge: Determine next step."""
        if state.get("is_complete"):
            return "complete"
        elif state.get("current_question"):
            return "continue"
        else:
            return "end"

    # ========================================================================
    # LangGraph Workflow: Story Generation
    # ========================================================================

    def _build_story_generation_graph(self):
        """Build LangGraph for story generation workflow."""
        workflow = StateGraph(StoryGenerationState)
        
        # Add nodes
        workflow.add_node("generate_stories", self._generate_stories_node)
        workflow.add_node("create_epic", self._create_epic_node)
        
        # Set entry point
        workflow.set_entry_point("generate_stories")
        
        # Add edges
        workflow.add_edge("generate_stories", "create_epic")
        workflow.add_edge("create_epic", END)
        
        # Compile
        memory = MemorySaver()
        self.story_graph = workflow.compile(checkpointer=memory)

    async def _generate_stories_node(self, state: StoryGenerationState) -> StoryGenerationState:
        """Node: Generate stories from context."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"🎨 [STORY GEN] Starting story generation for feature {state['feature_id']}")
            logger.info(f"📦 [STORY GEN] Context keys: {list(state.get('context', {}).keys())}")
            
            result = await self.story_agent.generate_from_feature_id(
                feature_id=state["feature_id"],
                generate_epic=True
            )
            
            state["stories"] = result.get("stories", [])
            state["epic"] = result.get("epic")
            state["status"] = "completed"
            logger.info(f"✅ [STORY GEN] Generated {len(state['stories'])} stories")
            
        except Exception as e:
            logger.error(f"❌ [STORY GEN] Failed: {str(e)}", exc_info=True)
            state["status"] = "failed"
            state["stories"] = []
            state["error"] = str(e)
        
        return state

    async def _create_epic_node(self, state: StoryGenerationState) -> StoryGenerationState:
        """Node: Create epic if needed."""
        # Epic creation logic (can push to Jira if needed)
        return state

    # ========================================================================
    # Public Workflow Methods
    # ========================================================================

    async def run_feature_workflow(
        self,
        feature_id: int,
        feature_name: str,
        feature_description: str,
        auto_generate_stories: bool = False
    ) -> Dict[str, Any]:
        """
        Run feature clarification workflow using LangGraph.
        
        Args:
            feature_id: Feature ID
            feature_name: Feature name
            feature_description: Feature description
            auto_generate_stories: Auto-generate stories after clarification
            
        Returns:
            Workflow result
        """
        workflow_id = f"feature_{feature_id}_{int(datetime.now().timestamp())}"
        self.active_workflows[workflow_id] = WorkflowType.FEATURE_CLARIFICATION
        
        # Initial state
        initial_state: FeatureWorkflowState = {
            "feature_id": feature_id,
            "feature_name": feature_name,
            "feature_description": feature_description,
            "user_response": None,
            "conversation_history": [],
            "current_question": None,
            "is_complete": False,
            "context_summary": None,
            "workflow_id": workflow_id
        }
        
        try:
            # Run LangGraph workflow
            config = {"configurable": {"thread_id": workflow_id}}
            final_state = await self.feature_graph.ainvoke(initial_state, config)
            
            return {
                "workflow_id": workflow_id,
                "status": "complete" if final_state["is_complete"] else "ongoing",
                "question": final_state.get("current_question"),
                "is_complete": final_state["is_complete"]
            }
        
        except Exception as e:
            return {
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(e)
            }

    async def continue_clarification(
        self,
        workflow_id: str,
        feature_id: int,
        user_response: str
    ) -> Dict[str, Any]:
        """
        Continue feature clarification conversation using LangGraph.
        
        Args:
            workflow_id: Workflow ID
            feature_id: Feature ID
            user_response: User's response to clarification question
            
        Returns:
            Next clarification or completion signal
        """
        try:
            # Get current state from graph memory
            config = {"configurable": {"thread_id": workflow_id}}
            current_state = await self.feature_graph.aget_state(config)
            
            if not current_state:
                raise ValueError(f"Workflow {workflow_id} not found")
            
            # Update state with user response
            state = current_state.values
            state["user_response"] = user_response
            
            # Only add to history if user_response is provided
            if user_response:
                state["conversation_history"].append({
                    "role": "user",
                    "content": user_response
                })
            
            # Continue workflow
            final_state = await self.feature_graph.ainvoke(state, config)
            
            return {
                "workflow_id": workflow_id,
                "status": "complete" if final_state["is_complete"] else "ongoing",
                "question": final_state.get("current_question"),
                "is_complete": final_state["is_complete"]
            }
        
        except Exception as e:
            return {
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(e)
            }

    async def generate_stories_from_context(
        self,
        feature_id: int,
        auto_push_to_jira: bool = False
    ) -> Dict[str, Any]:
        """
        Generate stories from clarified feature context using LangGraph.
        
        Args:
            feature_id: Feature ID
            auto_push_to_jira: Automatically push stories to Jira
            
        Returns:
            Generated stories
        """
        workflow_id = f"story_{feature_id}_{int(datetime.now().timestamp())}"
        self.active_workflows[workflow_id] = WorkflowType.STORY_GENERATION
        
        # Get context from Redis (lightweight)
        context = self.redis_client.get_feature_context(feature_id) or {}
        
        # Initial state
        initial_state: StoryGenerationState = {
            "feature_id": feature_id,
            "context": context,
            "stories": [],
            "epic": None,
            "workflow_id": workflow_id,
            "status": "running"
        }
        
        try:
            # Run LangGraph workflow
            config = {"configurable": {"thread_id": workflow_id}}
            final_state = await self.story_graph.ainvoke(initial_state, config)
            
            # Optionally push to Jira
            if auto_push_to_jira and final_state.get("stories"):
                jira_results = await self._push_stories_to_jira(
                    feature_id=feature_id,
                    stories=final_state["stories"],
                    epic=final_state.get("epic")
                )
                final_state["jira_push"] = jira_results
            
            return {
                "workflow_id": workflow_id,
                "status": final_state["status"],
                "stories": final_state["stories"],
                "epic": final_state.get("epic")
            }
        
        except Exception as e:
            return {
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(e)
            }

    # ========================================================================
    # Other Workflows (Simplified - not using LangGraph yet)
    # ========================================================================

    async def run_prioritization_workflow(
        self,
        stories: List[Dict[str, Any]],
        team_id: Optional[str] = None,
        auto_assign_to_jira: bool = False
    ) -> Dict[str, Any]:
        """Run task prioritization workflow."""
        import logging
        logger = logging.getLogger(__name__)
        
        workflow_id = f"prioritize_{int(datetime.now().timestamp())}"
        
        try:
            # ALWAYS use configured team from .env (JIRA_USER_DESIGNATIONS or TEAM_MEMBERS)
            # This ensures proper role-based assignment with the correct team structure
            logger.info(f"📋 [PRIORITIZATION] Loading team from environment configuration")
            team_members = self._get_default_team()
            
            logger.info(f"👥 [PRIORITIZATION] Proceeding with {len(team_members)} team members")
            
            # Log team for debugging
            for member in team_members:
                logger.info(f"  - {member.get('name')} ({member.get('job_title')})")
            
            # Run prioritization agent
            result = await self.prioritization_agent.execute({
                "stories": stories,
                "team_members": team_members
            })
            
            # Optionally assign in Jira
            if auto_assign_to_jira:
                jira_assignments = await self._assign_tasks_in_jira(
                    result["assignments"]
                )
                result["jira_assignments"] = jira_assignments
            
            return {
                "workflow_id": workflow_id,
                "status": "completed",
                "prioritization": result
            }
        
        except Exception as e:
            logger.error(f"❌ [PRIORITIZATION] Workflow failed: {str(e)}", exc_info=True)
            return {
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(e)
            }


    async def run_full_pipeline(
        self,
        feature_id: int,
        feature_name: str,
        feature_description: str,
        context: Dict[str, Any],
        team_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run full pipeline: story generation → prioritization."""
        workflow_id = f"pipeline_{feature_id}_{int(datetime.now().timestamp())}"
        
        try:
            # Store context (lightweight)
            self.redis_client.set_feature_context(feature_id, context, ttl=86400)
            
            # Step 1: Story Generation
            story_result = await self.generate_stories_from_context(feature_id)
            
            # Step 2: Prioritization
            prioritization_result = await self.run_prioritization_workflow(
                stories=story_result.get("stories", []),
                team_id=team_id
            )
            
            return {
                "workflow_id": workflow_id,
                "status": "completed",
                "stories": story_result,
                "prioritization": prioritization_result
            }
        
        except Exception as e:
            return {
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(e)
            }

    # ========================================================================
    # MCP Integration Helpers
    # ========================================================================

    async def _push_stories_to_jira(
        self,
        feature_id: int,
        stories: List[Dict[str, Any]],
        epic: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Push generated stories to Jira."""
        results = {
            "epic": None,
            "stories": [],
            "errors": []
        }
        
        if epic:
            try:
                epic_result = await self.jira_client.create_story(
                    project_key="PROJ",
                    summary=epic["title"],
                    description=epic["description"]
                )
                results["epic"] = epic_result
            except Exception as e:
                results["errors"].append({"epic": str(e)})
        
        for story in stories:
            try:
                story_result = await self.jira_client.create_story(
                    project_key="PROJ",
                    summary=story["title"],
                    description=story["description"],
                    story_points=story.get("story_points")
                )
                results["stories"].append(story_result)
            except Exception as e:
                results["errors"].append({"story": story["title"], "error": str(e)})
        
        return results

    async def _assign_tasks_in_jira(
        self,
        assignments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Assign tasks in Jira."""
        results = []
        for assignment in assignments:
            if assignment.get("assignee"):
                try:
                    result = await self.jira_client.assign_task(
                        task_key=assignment.get("story_id", "PROJ-000"),
                        assignee_email=assignment["assignee"]
                    )
                    results.append(result)
                except Exception as e:
                    results.append({"error": str(e)})
        return results

    # ========================================================================
    # Query Interface with Tool Calling
    # ========================================================================

    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """Get available tools from MCP server for function calling."""
        import logging
        logger = logging.getLogger(__name__)
        
        # Get all tool schemas from MCP server
        tools = get_tool_schemas()
        
        logger.info(f"🔧 Available tools from MCP: {[t['function']['name'] for t in tools]}")
        return tools

    def _format_tool_result(self, function_name: str, tool_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format tool execution result in a clean, human-readable format for frontend.
        
        Args:
            function_name: Name of the tool/function that was executed
            tool_result: Raw result from tool execution
            
        Returns:
            Formatted result dictionary with human-readable message and structured data
        """
        import logging
        logger = logging.getLogger(__name__)
        
        formatted = {
            "success": tool_result.get("success", False),
            "tool": function_name,
            "message": "",
            "data": {},
            "metadata": {}
        }
        
        try:
            # Handle both old and new tool names for backward compatibility
            if function_name in ["create_servicenow_incident", "servicenow_create_incident"]:
                # Check if the operation was successful
                if not tool_result.get("success", False):
                    # Error case - incident was NOT created
                    formatted["success"] = False
                    error_message = tool_result.get("error", "Unknown error occurred")
                    error_type = tool_result.get("error_type", "unknown_error")
                    
                    formatted["message"] = (
                        f"❌ **Failed to create ServiceNow incident**\n\n"
                        f"**Error:** {error_message}\n\n"
                        f"Please check:\n"
                        f"- ServiceNow credentials are configured in your .env file\n"
                        f"- ServiceNow instance URL is correct and accessible\n"
                        f"- Network connectivity to ServiceNow\n"
                        f"- ServiceNow API permissions"
                    )
                    formatted["data"] = {
                        "error": error_message,
                        "error_type": error_type,
                        "incident_created": False
                    }
                    formatted["metadata"]["error"] = True
                    formatted["metadata"]["error_type"] = error_type
                    return formatted
                
                # Success case - incident was created
                result = tool_result.get("result", {})
                incident_number = result.get("number")
                short_description = result.get("short_description", "")
                priority = result.get("priority", "3")
                state = result.get("state", "1")
                
                # Priority mapping
                priority_map = {
                    "1": "Critical",
                    "2": "High",
                    "3": "Medium",
                    "4": "Low"
                }
                priority_text = priority_map.get(priority, "Medium")
                
                # State mapping
                state_map = {
                    "1": "New",
                    "2": "In Progress",
                    "3": "On Hold",
                    "6": "Resolved",
                    "7": "Closed"
                }
                state_text = state_map.get(state, "New")
                
                formatted["message"] = (
                    f"✅ **Successfully created ServiceNow incident!**\n\n"
                    f"**Incident Number:** {incident_number}\n"
                    f"**Description:** {short_description}\n"
                    f"**Priority:** {priority_text}\n"
                    f"**Status:** {state_text}\n\n"
                    f"You can track this incident in ServiceNow using the incident number above."
                )
                formatted["metadata"]["is_mock"] = False
                formatted["metadata"]["incident_created"] = True
                
                # Structured data for frontend
                formatted["data"] = {
                    "incident_number": incident_number,
                    "short_description": short_description,
                    "description": result.get("description", ""),
                    "priority": priority_text,
                    "priority_code": priority,
                    "status": state_text,
                    "status_code": state,
                    "created_at": result.get("created_at", ""),
                    "sys_id": result.get("sys_id", ""),
                    "incident_created": True
                }
                
            elif function_name == "jira_get_issue":
                # Format Jira issue details
                if not tool_result.get("success", False):
                    error_info = tool_result.get("error", {})
                    if isinstance(error_info, dict):
                        error_msg = error_info.get("message", "Unknown error occurred")
                    else:
                        error_msg = str(error_info)
                    formatted["message"] = f"❌ **Failed to retrieve Jira issue**\n\n**Error:** {error_msg}"
                    formatted["data"] = {"error": error_msg}
                    return formatted
                
                issue_data = tool_result.get("data", {})
                if not issue_data:
                    formatted["message"] = "❌ No issue data returned"
                    return formatted
                
                # Extract issue fields
                fields = issue_data.get("fields", {})
                key = issue_data.get("key", "N/A")
                issue_type = fields.get("issuetype", {}).get("name", "N/A")
                summary = fields.get("summary", "No summary")
                status = fields.get("status", {}).get("name", "N/A")
                assignee = fields.get("assignee")
                assignee_name = assignee.get("displayName", "Not assigned") if assignee else "Not assigned"
                creator = fields.get("creator", {})
                creator_name = creator.get("displayName", "N/A") if creator else "N/A"
                created = fields.get("created", "")
                updated = fields.get("updated", "")
                description = fields.get("description")
                description_text = "No description provided"
                if description:
                    if isinstance(description, dict):
                        description_text = description.get("content", [{}])[0].get("content", [{}])[0].get("text", "No description provided")
                    else:
                        description_text = str(description)
                
                # Format dates
                from datetime import datetime, timezone
                try:
                    if created:
                        created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        created_formatted = created_dt.strftime("%B %d, %Y")
                    else:
                        created_formatted = "N/A"
                    
                    if updated:
                        updated_dt = datetime.fromisoformat(updated.replace('Z', '+00:00'))
                        updated_formatted = updated_dt.strftime("%B %d, %Y")
                        # Check if updated today
                        now = datetime.now(timezone.utc)
                        if (now - updated_dt).days == 0:
                            updated_formatted = "Today"
                    else:
                        updated_formatted = "N/A"
                except:
                    created_formatted = created[:10] if created else "N/A"
                    updated_formatted = updated[:10] if updated else "N/A"
                
                # Get parent epic if exists
                parent = fields.get("parent", {})
                parent_key = parent.get("key", "N/A") if parent else "N/A"
                parent_summary = parent.get("fields", {}).get("summary", "N/A") if parent else "N/A"
                epic_key = parent_key if parent_key != "N/A" else "N/A"
                epic_summary = parent_summary if parent_summary != "N/A" else "N/A"
                
                # Get project info
                project = fields.get("project", {})
                project_name = project.get("name", "N/A") if project else "N/A"
                project_key = project.get("key", "N/A") if project else "N/A"
                
                # Get sprints
                sprints = []
                sprint_field = fields.get("customfield_10020", [])  # Sprint field
                if sprint_field:
                    for sprint in sprint_field:
                        sprint_name = sprint.get("name", "N/A")
                        sprint_state = sprint.get("state", "N/A")
                        sprints.append(f"{sprint_name} ({sprint_state})")
                
                # Build formatted message
                message_parts = [
                    f"**📋 Issue Details**\n",
                    f"**Key:** {key}",
                    f"**Issue Type:** {issue_type}",
                    f"**Summary:** {summary}",
                    f"**Status:** {status}",
                    f"**Assignee:** {assignee_name}",
                    f"**Creator:** {creator_name}",
                    f"**Created Date:** {created_formatted}",
                    f"**Last Updated:** {updated_formatted}",
                    f"**Description:** {description_text}",
                    f"**Project:** {project_name} (Key: {project_key})"
                ]
                
                if epic_key != "N/A":
                    message_parts.append(f"**Parent Epic:** {epic_summary} (Key: {epic_key})")
                
                if sprints:
                    message_parts.append(f"**Sprints:** {', '.join(sprints)}")
                
                formatted["message"] = "\n".join(message_parts)
                formatted["data"] = {
                    "key": key,
                    "issue_type": issue_type,
                    "summary": summary,
                    "status": status,
                    "assignee": assignee_name,
                    "creator": creator_name,
                    "created": created_formatted,
                    "updated": updated_formatted,
                    "description": description_text,
                    "project": project_name,
                    "project_key": project_key,
                    "epic_key": epic_key,
                    "epic_summary": epic_summary,
                    "sprints": sprints
                }
                
            elif function_name == "jira_search_issues":
                # Format Jira search results
                if not tool_result.get("success", False):
                    error_info = tool_result.get("error", {})
                    if isinstance(error_info, dict):
                        error_msg = error_info.get("message", "Unknown error occurred")
                    else:
                        error_msg = str(error_info)
                    formatted["message"] = f"❌ **Failed to search Jira issues**\n\n**Error:** {error_msg}"
                    formatted["data"] = {"error": error_msg}
                    return formatted
                
                search_data = tool_result.get("data", {})
                issues = search_data.get("issues", [])
                total = search_data.get("total", 0)
                
                if total == 0:
                    formatted["message"] = "🔍 **No issues found**\n\nNo Jira issues matched your search criteria."
                    formatted["data"] = {"total": 0, "issues": []}
                    return formatted
                
                # Format first few issues
                message_parts = [f"🔍 **Found {total} issue(s)**\n"]
                
                for idx, issue in enumerate(issues[:5]):  # Show first 5
                    fields = issue.get("fields", {})
                    key = issue.get("key", "N/A")
                    summary = fields.get("summary", "No summary")
                    status = fields.get("status", {}).get("name", "N/A")
                    issue_type = fields.get("issuetype", {}).get("name", "N/A")
                    
                    message_parts.append(f"\n**{idx + 1}. {key}** - {summary}")
                    message_parts.append(f"   Type: {issue_type} | Status: {status}")
                
                if total > 5:
                    message_parts.append(f"\n*... and {total - 5} more issue(s)*")
                
                formatted["message"] = "\n".join(message_parts)
                formatted["data"] = {
                    "total": total,
                    "issues": issues[:10]  # Store first 10 for reference
                }
                
            else:
                # Generic formatting for other tools
                formatted["message"] = tool_result.get("message", "Action completed successfully.")
                formatted["data"] = tool_result.get("result", {})
                formatted["metadata"] = tool_result.get("metadata", {})
            
            # Add error information if present
            if not formatted["success"]:
                error_msg = tool_result.get("error", "Unknown error occurred")
                formatted["message"] = f"❌ Error: {error_msg}"
                formatted["data"]["error"] = error_msg
            
            # Log full message for debugging, but truncate for cleaner logs
            message_preview = formatted['message'][:200] + ("..." if len(formatted['message']) > 200 else "")
            logger.info(f"📝 Formatted result: {message_preview}")
            return formatted
            
        except Exception as e:
            logger.error(f"❌ Error formatting tool result: {str(e)}", exc_info=True)
            return {
                "success": False,
                "tool": function_name,
                "message": f"Error formatting result: {str(e)}",
                "data": {},
                "metadata": {}
            }

    async def _execute_tool_call(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool/function call using MCP server."""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"🔨 Executing tool via MCP: {function_name} with args: {arguments}")
        
        try:
            # Use MCP server to execute the tool
            result = await execute_tool_async(function_name, arguments)
            logger.info(f"✅ MCP tool execution result: {result.get('success', False)}")
            
            # Handle envelope format (ServiceNow uses envelope_success/envelope_error)
            if isinstance(result, dict) and "success" in result:
                # This is an envelope format
                if result.get("success"):
                    # Success envelope - extract data
                    data = result.get("data", {})
                    if isinstance(data, dict) and "record" in data:
                        # ServiceNow format: data.record contains the actual record
                        record = data.get("record", {})
                        return {
                            "success": True,
                            "result": record,
                            "message": f"Tool executed successfully"
                        }
                    else:
                        # Other envelope formats - return data directly
                        return {
                            "success": True,
                            "result": data,
                            "message": "Tool executed successfully"
                        }
                else:
                    # Error envelope
                    error_info = result.get("error", {})
                    if isinstance(error_info, dict):
                        error_message = error_info.get("message", "Unknown error")
                        error_code = error_info.get("code", "unknown_error")
                    else:
                        error_message = str(error_info)
                        error_code = "unknown_error"
                    
                    logger.warning(f"⚠️ Tool execution failed: {error_message}")
                    return {
                        "success": False,
                        "result": result,
                        "error": error_message,
                        "error_type": error_code
                    }
            
            # For direct result format (Jira tools return this)
            if isinstance(result, dict) and "success" in result:
                return result
            
            # Fallback: wrap result in standard format
            return {
                "success": True,
                "result": result,
                "message": "Tool executed successfully"
            }
        
        except Exception as e:
            logger.error(f"❌ Tool execution error: {str(e)}", exc_info=True)
            return {
                "success": False,
                "result": {},
                "error": str(e),
                "error_type": "execution_error"
            }

    async def query(self, query_text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process natural language query to Scrum Master with tool calling.
        
        Can execute actions like creating tickets, getting sprint data, etc.
        
        Returns:
            Dictionary with 'response' (text) and 'data' (structured tool results)
        """
        from utils.openai_llm import get_llm_client
        import json
        import logging
        
        logger = logging.getLogger(__name__)
        query_preview = query_text[:200] + ("..." if len(query_text) > 200 else "")
        logger.info(f"📥 Query received: {query_preview}")
        
        llm_client = get_llm_client()
        
        system_message = """You are an AI Scrum Master assistant with access to multiple tools via MCP (Model Context Protocol).

CRITICAL: When calling tools, you MUST provide ALL required parameters. Check the tool schema for required fields.

For Jira tools:
- jira_get_issue: REQUIRES 'issue_key' parameter (e.g., SCRUM-1). If you only have a story name, use jira_search_issues first.
- jira_search_issues: REQUIRES 'jql' parameter. Example: To find a story named 'Task 3', use jql: 'summary ~ "Task 3"' or 'text ~ "Task 3"'.

Available tools include:
- ServiceNow: Create, list, update incidents; search knowledge base
- Jira: Create stories, get sprint data, assign tasks, check team capacity, search issues

When users ask to:
- Create a ticket/incident → Use servicenow_create_incident
- Query incidents → Use servicenow_list_incidents
- Get incident details → Use servicenow_get_incident_by_number
- Update/close incidents → Use servicenow_update_incident
- Search for Jira issues by name → Use jira_search_issues (REQUIRES jql parameter with JQL query)
- Get Jira issue by key → Use jira_get_issue (REQUIRES issue_key parameter)
- Create Jira story → Use jira_create_story
- Get sprint info → Use jira_get_sprint_data
- Get team capacity → Use jira_get_team_capacity

ALWAYS use the appropriate tool - don't just say you can do it. Actually execute the action.
ALWAYS provide all required parameters when calling tools. If a tool fails, check the error message and provide the missing required parameters.

IMPORTANT FORMATTING: When presenting tool results to the user:
- Use the formatted tool result message EXACTLY as provided - it's already well-formatted with proper structure
- Present tool results in a clear, readable format with proper line breaks
- Use bold formatting (**text**) for labels and important information
- Keep the formatting consistent and easy to read
- Don't reformat or simplify the tool results - they're already optimized for readability

Extract all relevant information from the user's request and use the tools to complete the task."""
        
        # Get available tools
        tools = self._get_available_tools()
        logger.info(f"🔧 Tools configured: {len(tools)} tool(s)")
        
        # Initial messages
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": query_text}
        ]
        
        # Call LLM with function calling
        max_iterations = 5  # Prevent infinite loops - STRICT LIMIT
        iteration = 0
        
        while iteration < max_iterations:
            logger.info(f"🔄 LLM call iteration {iteration + 1}/{max_iterations}")
            
            try:
                response = llm_client.chat_completion(
                    messages=messages,
                    temperature=0.7,
                    tools=tools,  # Use tools format (newer API)
                    tool_choice="auto"  # Let LLM decide when to call tools
                )
                
                # Safely extract content
                content = response.get("content") or ""
                content_preview = content[:100] if content else "(empty)"
                logger.info(f"📤 LLM response received. Content: {content_preview}")
                logger.info(f"📋 Full response keys: {list(response.keys())}")
                logger.info(f"📋 Response: {response}")
                
                # Add assistant response to messages
                assistant_message = {"role": "assistant", "content": content}
                
                # Handle tool calls (new format)
                tool_calls = response.get("tool_calls")
                function_call = response.get("function_call")  # Legacy format
                
                logger.info(f"🔍 Tool calls type: {type(tool_calls)}, value: {tool_calls}")
                logger.info(f"🔍 Function call type: {type(function_call)}, value: {function_call}")
                
                if tool_calls:
                    assistant_message["tool_calls"] = tool_calls
                    logger.info(f"✅ Tool calls detected: {len(tool_calls) if tool_calls else 0}")
                elif function_call:
                    assistant_message["function_call"] = function_call
                    logger.info(f"✅ Function call detected (legacy format)")
                
                messages.append(assistant_message)
                
                # Check if LLM wants to call a tool/function
                if tool_calls:
                    logger.info(f"🛠️ Processing {len(tool_calls)} tool call(s)...")
                    # New format: tool_calls is a list of ToolCall objects
                    for idx, tool_call in enumerate(tool_calls):
                        logger.info(f"🔨 Processing tool call {idx + 1}: {tool_call}")
                        
                        # Handle both object attributes and dict access
                        if hasattr(tool_call, 'function'):
                            function_name = tool_call.function.name
                            function_args_str = tool_call.function.arguments
                            tool_call_id = tool_call.id
                        elif isinstance(tool_call, dict):
                            function_name = tool_call.get("function", {}).get("name")
                            function_args_str = tool_call.get("function", {}).get("arguments", "{}")
                            tool_call_id = tool_call.get("id")
                        else:
                            # Try to access as object
                            function_name = getattr(tool_call, 'function', {}).name if hasattr(getattr(tool_call, 'function', None), 'name') else None
                            function_args_str = getattr(tool_call, 'function', {}).arguments if hasattr(getattr(tool_call, 'function', None), 'arguments') else "{}"
                            tool_call_id = getattr(tool_call, 'id', None)
                        
                        logger.info(f"📋 Parsed: function_name={function_name}, tool_call_id={tool_call_id}")
                        
                        if not function_name:
                            logger.warning(f"⚠️ Could not extract function name from tool_call")
                            continue
                        
                        try:
                            function_args = json.loads(function_args_str) if isinstance(function_args_str, str) else function_args_str
                        except Exception as e:
                            logger.error(f"❌ Failed to parse function args: {e}")
                            function_args = {}
                        
                        logger.info(f"🔧 Executing: {function_name}({function_args})")
                        
                        # Execute the function
                        raw_tool_result = await self._execute_tool_call(function_name, function_args)
                        
                        logger.info(f"✅ Raw tool result: {raw_tool_result}")
                        
                        # Format the result for better LLM understanding
                        formatted_result = self._format_tool_result(function_name, raw_tool_result)
                        message_preview = formatted_result.get('message', '')[:200] + ("..." if len(formatted_result.get('message', '')) > 200 else "")
                        logger.info(f"📝 Formatted result: {message_preview}")
                        
                        # Store formatted result for final response
                        if not hasattr(self, '_last_tool_result'):
                            self._last_tool_result = {}
                        self._last_tool_result[function_name] = formatted_result
                        
                        # Add function result to messages (new format uses tool_call_id)
                        # Use formatted message for LLM to generate better response
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": function_name,
                            "content": json.dumps({
                                "success": formatted_result["success"],
                                "message": formatted_result["message"],
                                "data": formatted_result["data"]
                            })
                        })
                    
                    iteration += 1
                    continue
                
                elif function_call:
                    logger.info(f"🛠️ Processing function call (legacy format)...")
                    # Legacy format: function_call is a dict
                    function_name = function_call.get("name")
                    function_args = json.loads(function_call.get("arguments", "{}"))
                    
                    logger.info(f"🔧 Executing (legacy): {function_name}({function_args})")
                    
                    # Execute the function
                    raw_tool_result = await self._execute_tool_call(function_name, function_args)
                    
                    logger.info(f"✅ Raw tool result: {raw_tool_result}")
                    
                    # Format the result for better LLM understanding
                    formatted_result = self._format_tool_result(function_name, raw_tool_result)
                    message_preview = formatted_result.get('message', '')[:200] + ("..." if len(formatted_result.get('message', '')) > 200 else "")
                    logger.info(f"📝 Formatted result: {message_preview}")
                    
                    # Store formatted result for final response
                    if not hasattr(self, '_last_tool_result'):
                        self._last_tool_result = {}
                    self._last_tool_result[function_name] = formatted_result
                    
                    # Add function result to messages
                    messages.append({
                        "role": "function",
                        "name": function_name,
                        "content": json.dumps({
                            "success": formatted_result["success"],
                            "message": formatted_result["message"],
                            "data": formatted_result["data"]
                        })
                    })
                    
                    iteration += 1
                    continue
                
                # No function/tool call - return the response
                logger.info("📝 No tool calls - returning response")
                
                # If we have tool results, include them in the response
                final_content = content or "I apologize, but I couldn't process your request."
                
                # Prepare response with structured data
                response_data = {
                    "response": final_content,
                    "tool_results": None
                }
                
                # Check if we have formatted tool results to include
                if hasattr(self, '_last_tool_result') and self._last_tool_result:
                    logger.info(f"📊 Tool results available: {list(self._last_tool_result.keys())}")
                    # Return formatted tool results for frontend
                    response_data["tool_results"] = self._last_tool_result
                    # Clean up for next query
                    self._last_tool_result = {}
                
                return response_data
            
            except Exception as e:
                logger.error(f"❌ Error in query processing: {str(e)}", exc_info=True)
                return {
                    "response": f"I encountered an error processing your request: {str(e)}",
                    "tool_results": None
                }
        
        # If we've done multiple iterations, return the last response
        logger.warning(f"⚠️ Max iterations reached")
        final_content = messages[-1].get("content", "I processed your request but encountered some issues.")
        
        response_data = {
            "response": final_content,
            "tool_results": None
        }
        
        # Include tool results if available
        if hasattr(self, '_last_tool_result') and self._last_tool_result:
            response_data["tool_results"] = self._last_tool_result
            self._last_tool_result = {}
        
        return response_data

    # ========================================================================
    # Utility Methods
    # ========================================================================

    async def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow status (lightweight - from graph memory)."""
        try:
            config = {"configurable": {"thread_id": workflow_id}}
            state = await self.feature_graph.aget_state(config)
            if state:
                return {"workflow_id": workflow_id, "status": "active"}
        except:
            pass
        return None

    def list_active_workflows(self) -> List[str]:
        """List active workflow IDs."""
        return list(self.active_workflows.keys())

    def _get_default_team(self) -> List[Dict[str, Any]]:
        """
        Get default team configuration from environment variables.
        
        Tries multiple sources:
        1. TEAM_MEMBERS env variable: name1:email1:role1,name2:email2:role2
        2. JIRA_USER_DESIGNATIONS: {"email": "role", ...}
        3. Fallback to minimal default team
        
        Returns:
            List of team member dictionaries
        """
        import os
        import json
        import logging
        logger = logging.getLogger(__name__)
        
        team_members_env = os.getenv("TEAM_MEMBERS", "")
        
        # Try TEAM_MEMBERS first
        if not team_members_env:
            # Try JIRA_USER_DESIGNATIONS as fallback
            jira_designations = os.getenv("JIRA_USER_DESIGNATIONS", "")
            if jira_designations:
                try:
                    designations = json.loads(jira_designations)
                    logger.info(f"📋 Loading team from JIRA_USER_DESIGNATIONS: {len(designations)} members")
                    
                    team = []
                    for idx, (email, role) in enumerate(designations.items()):
                        # Extract name from email if possible
                        name = email.split("@")[0].replace(".", " ").title()
                        
                        # Map role to experience level
                        experience_level = "mid"
                        if any(keyword in role.lower() for keyword in ["senior", "lead", "principal", "architect"]):
                            experience_level = "senior"
                        elif any(keyword in role.lower() for keyword in ["junior", "associate", "intern"]):
                            experience_level = "junior"
                        
                        # Extract skills from role
                        skills = []
                        role_lower = role.lower()
                        if "developer" in role_lower or "engineer" in role_lower:
                            skills.extend(["backend", "api", "database", "development", "developer"])
                        if "frontend" in role_lower:
                            skills.extend(["frontend", "ui", "javascript"])
                        if "devops" in role_lower or "sre" in role_lower:
                            skills.extend(["devops", "infrastructure", "monitoring"])
                        if "qa" in role_lower or "test" in role_lower:
                            skills.extend(["testing", "automation", "quality", "qa", "tester"])
                        if "architect" in role_lower:
                            skills.extend(["architecture", "design", "senior"])
                        if not skills:
                            skills = ["general", "software development"]
                        
                        team.append({
                            "id": f"jira_user_{idx}",
                            "name": name,
                            "email": email,
                            "job_title": role,
                            "experience_level": experience_level,
                            "skills": list(set(skills)),
                            "max_capacity": 40,
                            "current_load": 0,
                            "available_capacity": 40
                        })
                        logger.info(f"  ✅ {name} ({role}) - skills: {skills}")
                    
                    if team:
                        logger.info(f"✅ Loaded {len(team)} team members from JIRA_USER_DESIGNATIONS")
                        return team
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JIRA_USER_DESIGNATIONS: {e}")
            
            logger.warning("⚠️ No team configuration found, using minimal default team")
            # Minimal default team
            return [
                {
                    "id": "default_dev_1",
                    "name": "Developer 1",
                    "email": "dev1@example.com",
                    "job_title": "Software Engineer",
                    "experience_level": "mid",
                    "skills": ["backend", "frontend", "database"],
                    "max_capacity": 40,
                    "current_load": 0,
                    "available_capacity": 40
                },
                {
                    "id": "default_dev_2",
                    "name": "Developer 2",
                    "email": "dev2@example.com",
                    "job_title": "Senior Software Engineer",
                    "experience_level": "senior",
                    "skills": ["backend", "devops", "architecture"],
                    "max_capacity": 40,
                    "current_load": 0,
                    "available_capacity": 40
                }
            ]
        
        # Parse TEAM_MEMBERS: name1:email1:role1,name2:email2:role2
        team = []
        members = team_members_env.split(",")
        
        for idx, member_str in enumerate(members):
            parts = member_str.strip().split(":")
            if len(parts) >= 3:
                name, email, role = parts[0].strip(), parts[1].strip(), parts[2].strip()
                
                # Map role to experience level
                experience_level = "mid"
                if any(keyword in role.lower() for keyword in ["senior", "lead", "principal", "architect"]):
                    experience_level = "senior"
                elif any(keyword in role.lower() for keyword in ["junior", "associate", "intern"]):
                    experience_level = "junior"
                
                # Default skills based on role
                skills = []
                if "backend" in role.lower() or "developer" in role.lower():
                    skills = ["backend", "api", "database"]
                if "frontend" in role.lower():
                    skills.extend(["frontend", "ui", "javascript"])
                if "devops" in role.lower() or "sre" in role.lower():
                    skills.extend(["devops", "infrastructure", "monitoring"])
                if "qa" in role.lower() or "test" in role.lower():
                    skills.extend(["testing", "automation", "quality"])
                if not skills:
                    skills = ["general", "software development"]
                
                team.append({
                    "id": f"env_member_{idx}",
                    "name": name,
                    "email": email,
                    "job_title": role,
                    "experience_level": experience_level,
                    "skills": list(set(skills)),
                    "max_capacity": 40,
                    "current_load": 0,
                    "available_capacity": 40
                })
                logger.info(f"✅ Loaded team member from .env: {name} ({role})")
        
        logger.info(f"✅ Loaded {len(team)} team members from .env")
        return team if team else [
            {
                "id": "fallback_dev",
                "name": "Default Developer",
                "email": "dev@example.com",
                "job_title": "Software Engineer",
                "experience_level": "mid",
                "skills": ["backend", "frontend"],
                "max_capacity": 40,
                "current_load": 0,
                "available_capacity": 40
            }
        ]


# Singleton instance
_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    """Get or create orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
