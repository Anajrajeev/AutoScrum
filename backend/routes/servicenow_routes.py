"""ServiceNow integration routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional, List, Dict, Any

from mcp_tools import ServiceNowClient

router = APIRouter(prefix="/api/servicenow", tags=["servicenow"])


@router.post("/incidents")
async def create_incident(
    short_description: str,
    description: str,
    priority: str = "3",
    category: Optional[str] = None,
    assigned_to: Optional[str] = None
):
    """
    Create a ServiceNow incident.
    
    Priority levels:
    - 1: Critical
    - 2: High
    - 3: Medium (default)
    - 4: Low
    """
    client = ServiceNowClient()
    
    try:
        incident = await client.create_incident(
            short_description=short_description,
            description=description,
            priority=priority,
            category=category,
            assigned_to=assigned_to
        )
        return incident
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create incident: {str(e)}"
        )


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """Get incident details by ID or number."""
    client = ServiceNowClient()
    
    try:
        incident = await client.get_incident(incident_id)
        return incident
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get incident: {str(e)}"
        )


@router.put("/incidents/{incident_id}")
async def update_incident(
    incident_id: str,
    updates: Dict[str, Any]
):
    """Update an existing incident."""
    client = ServiceNowClient()
    
    try:
        result = await client.update_incident(incident_id, updates)
        return result
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update incident: {str(e)}"
        )


@router.get("/incidents")
async def list_incidents(
    assigned_to: Optional[str] = None,
    state: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 100
):
    """
    List incidents with optional filters.
    
    State values:
    - 1: New
    - 2: In Progress
    - 3: On Hold
    - 6: Resolved
    - 7: Closed
    """
    client = ServiceNowClient()
    
    try:
        incidents = await client.list_incidents(
            assigned_to=assigned_to,
            state=state,
            priority=priority,
            limit=limit
        )
        return {
            "count": len(incidents),
            "incidents": incidents
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list incidents: {str(e)}"
        )


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: str,
    resolution_notes: str,
    close_code: str = "Resolved"
):
    """Resolve and close an incident."""
    client = ServiceNowClient()
    
    try:
        result = await client.resolve_incident(
            incident_id=incident_id,
            resolution_notes=resolution_notes,
            close_code=close_code
        )
        return result
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve incident: {str(e)}"
        )


@router.post("/incidents/{incident_id}/notes")
async def add_work_note(
    incident_id: str,
    note: str
):
    """Add a work note to an incident."""
    client = ServiceNowClient()
    
    try:
        result = await client.add_work_note(incident_id, note)
        return result
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add work note: {str(e)}"
        )


@router.get("/incidents/{incident_id}/history")
async def get_incident_history(incident_id: str):
    """Get update history for an incident."""
    client = ServiceNowClient()
    
    try:
        history = await client.get_incident_history(incident_id)
        return {
            "incident_id": incident_id,
            "count": len(history),
            "history": history
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get incident history: {str(e)}"
        )


@router.post("/incidents/batch")
async def create_incidents_batch(
    incidents: List[Dict[str, Any]]
):
    """
    Create multiple incidents in batch.
    
    Useful for creating incidents from meeting blockers.
    """
    client = ServiceNowClient()
    results = []
    errors = []
    
    for incident_data in incidents:
        try:
            incident = await client.create_incident(
                short_description=incident_data.get("short_description", ""),
                description=incident_data.get("description", ""),
                priority=incident_data.get("priority", "3"),
                category=incident_data.get("category"),
                assigned_to=incident_data.get("assigned_to")
            )
            results.append(incident)
        except Exception as e:
            errors.append({
                "incident": incident_data,
                "error": str(e)
            })
    
    return {
        "created": len(results),
        "failed": len(errors),
        "incidents": results,
        "errors": errors
    }

