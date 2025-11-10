"""Query and conversational interface routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from db.database import get_db
from db import models, schemas
from orchestrator import get_orchestrator
from memory.redis_client import get_redis_client

router = APIRouter(prefix="/api/query", tags=["query"])


@router.post("/", response_model=schemas.QueryResponse)
async def query_scrum_master(
    query: schemas.QueryRequest,
    db: Session = Depends(get_db)
):
    """
    Query the AI Scrum Master with natural language.
    
    Examples:
    - "What's my sprint progress?"
    - "Show me team capacity"
    - "What are the blockers?"
    - "Who is overloaded?"
    """
    orchestrator = get_orchestrator()
    
    try:
        # Process query through orchestrator
        result = await orchestrator.query(
            query_text=query.query,
            context=query.context
        )
        
        # Extract response text and tool results
        response_text = result.get("response", "I apologize, but I couldn't process your request.")
        tool_results = result.get("tool_results")
        
        # Format tool results for frontend if available
        formatted_data = None
        if tool_results:
            # Extract structured data from tool results
            formatted_data = {}
            for tool_name, tool_result in tool_results.items():
                formatted_data[tool_name] = {
                    "success": tool_result.get("success", False),
                    "message": tool_result.get("message", ""),
                    "data": tool_result.get("data", {}),
                    "metadata": tool_result.get("metadata", {})
                }
        
        return schemas.QueryResponse(
            response=response_text,
            data=formatted_data,
            suggestions=None
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query processing failed: {str(e)}"
        )


@router.post("/prioritize")
async def prioritize_stories(
    stories: List[schemas.StoryResponse],
    team_id: str = None,
    db: Session = Depends(get_db)
):
    """
    Prioritize and assign stories to team members.
    
    Uses the Prioritization Agent to optimize assignments.
    """
    orchestrator = get_orchestrator()
    
    # Convert story responses to dicts
    story_dicts = [
        {
            "id": story.id,
            "title": story.title,
            "story_points": story.story_points or 3,
            "priority": "medium",
            "dependencies": []
        }
        for story in stories
    ]
    
    try:
        result = await orchestrator.run_prioritization_workflow(
            stories=story_dicts,
            team_id=team_id,
            auto_assign_to_jira=False
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prioritization failed: {str(e)}"
        )


@router.get("/conversation/{session_id}")
async def get_conversation_history(session_id: str):
    """
    Get conversation history for a session.
    
    Useful for resuming conversations.
    """
    redis_client = get_redis_client()
    messages = redis_client.get_conversation_messages(session_id)
    
    return {
        "session_id": session_id,
        "messages": messages,
        "count": len(messages)
    }


@router.delete("/conversation/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_conversation(session_id: str):
    """Clear conversation history for a session."""
    redis_client = get_redis_client()
    # Delete conversation messages
    # (Implementation would clear Redis keys)
    
    return None


@router.get("/workflows")
async def list_workflows():
    """
    List active workflows.
    
    Shows ongoing clarifications, story generations, etc.
    """
    orchestrator = get_orchestrator()
    active_workflows = orchestrator.list_active_workflows()
    
    workflow_details = []
    for workflow_id in active_workflows:
        status = orchestrator.get_workflow_status(workflow_id)
        if status:
            workflow_details.append(status)
    
    return {
        "count": len(workflow_details),
        "workflows": workflow_details
    }


@router.get("/workflow/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Get detailed status of a workflow."""
    orchestrator = get_orchestrator()
    status = orchestrator.get_workflow_status(workflow_id)
    
    if not status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )
    
    return status



