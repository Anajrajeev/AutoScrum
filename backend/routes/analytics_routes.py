"""Analytics and reporting routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime, timedelta
import logging
import asyncio

from db.database import get_db
from db import models, schemas
from mcp_tools.tools.jira_client import JiraClient

logger = logging.getLogger("autoscrum.routes")

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/sprint/{sprint_id}", response_model=schemas.AnalyticsResponse)
async def get_sprint_analytics(
    sprint_id: int,
    db: Session = Depends(get_db)
):
    """
    Get comprehensive sprint analytics.
    
    Includes:
    - Story completion stats
    - Velocity metrics
    - Team sentiment
    - Blocker summary
    """
    # Get sprint
    sprint = db.query(models.Sprint).filter(
        models.Sprint.id == sprint_id
    ).first()
    
    if not sprint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sprint not found"
        )
    
    # Get sprint stories
    stories = db.query(models.Story).filter(
        models.Story.sprint_id == sprint_id
    ).all()
    
    # Calculate metrics
    total_stories = len(stories)
    completed_stories = sum(1 for s in stories if s.status == models.StoryStatus.DONE)
    total_points = sum(s.story_points or 0 for s in stories)
    completed_points = sum(
        s.story_points or 0 for s in stories
        if s.status == models.StoryStatus.DONE
    )
    
    # Sentiment analysis removed - return default values
    avg_sentiment = None
    top_blockers = []
    
    # Team load (mock for now)
    team_load = {
        "average_load_percentage": 75.0,
        "overloaded_members": 1,
        "available_capacity": 25.0
    }
    
    return schemas.AnalyticsResponse(
        sprint_id=sprint_id,
        sprint_name=sprint.name,
        total_stories=total_stories,
        completed_stories=completed_stories,
        total_points=total_points,
        completed_points=completed_points,
        velocity=sprint.velocity or completed_points,
        sentiment_avg=avg_sentiment,
        top_blockers=top_blockers,
        team_load=team_load
    )


@router.get("/sprints", response_model=List[schemas.SprintResponse])
async def list_sprints(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all sprints."""
    sprints = db.query(models.Sprint).offset(skip).limit(limit).all()
    return sprints


@router.post("/sprints", response_model=schemas.SprintResponse)
async def create_sprint(
    sprint: schemas.SprintCreate,
    db: Session = Depends(get_db)
):
    """Create a new sprint."""
    db_sprint = models.Sprint(
        name=sprint.name,
        start_date=sprint.start_date,
        end_date=sprint.end_date,
        velocity=sprint.velocity
    )
    db.add(db_sprint)
    db.commit()
    db.refresh(db_sprint)
    
    return db_sprint


@router.get("/sentiment/logs")
async def get_sentiment_logs(
    sprint_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    Get sentiment analysis logs.
    
    Note: Sentiment analysis feature has been removed.
    This endpoint returns empty data for backward compatibility.
    """
    return {
        "count": 0,
        "logs": []
    }


@router.get("/agent-logs")
async def get_agent_logs(
    agent_name: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Get agent execution logs.
    
    Useful for debugging and monitoring agent performance.
    """
    query = db.query(models.AgentLog)
    
    if agent_name:
        query = query.filter(models.AgentLog.agent_name == agent_name)
    
    logs = query.order_by(models.AgentLog.timestamp.desc()).limit(limit).all()
    
    return {
        "count": len(logs),
        "logs": [
            {
                "id": log.id,
                "agent_name": log.agent_name,
                "action": log.action,
                "status": log.status,
                "execution_time": log.execution_time,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "error_message": log.error_message
            }
            for log in logs
        ]
    }


@router.get("/dashboard")
async def get_dashboard_data(db: Session = Depends(get_db)):
    """
    Get comprehensive dashboard data.
    
    Includes high-level metrics across all sprints and features.
    Fetches active and closed stories from Jira API.
    """
    # Feature stats
    total_features = db.query(func.count(models.Feature.id)).scalar()
    features_with_context = db.query(func.count(models.Feature.id)).filter(
        models.Feature.context_json.isnot(None)
    ).scalar()
    
    # Story stats from database
    total_stories = db.query(func.count(models.Story.id)).scalar()
    completed_stories = db.query(func.count(models.Story.id)).filter(
        models.Story.status == models.StoryStatus.DONE
    ).scalar()
    
    # Fetch active and closed stories from Jira
    active_stories_count = 0
    closed_stories_count = 0
    
    try:
        jira_client = JiraClient()
        project_key = jira_client.config.default_project
        
        if project_key:
            logger.info(f"[ANALYTICS] Fetching Jira stories for project: {project_key}")
            
            # Run synchronous Jira calls in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            # Get active stories (status != Done)
            active_jql = f'project = "{project_key}" AND status != Done AND type = Story'
            active_result = await loop.run_in_executor(
                None, 
                lambda: jira_client.search(active_jql, max_results=1000)
            )
            active_stories_count = active_result.get("total", 0)
            
            # Get closed stories (status = Done)
            closed_jql = f'project = "{project_key}" AND status = Done AND type = Story'
            closed_result = await loop.run_in_executor(
                None,
                lambda: jira_client.search(closed_jql, max_results=1000)
            )
            closed_stories_count = closed_result.get("total", 0)
            
            logger.info(f"[ANALYTICS] Jira stats - Active: {active_stories_count}, Closed: {closed_stories_count}")
        else:
            logger.warning("[ANALYTICS] JIRA_DEFAULT_PROJECT not configured, using database stats only")
    except Exception as e:
        logger.error(f"[ANALYTICS] Error fetching Jira stories: {e}", exc_info=True)
        # Fall back to database stats if Jira fails
    
    # Use Jira counts if available, otherwise fall back to database
    total_stories_jira = active_stories_count + closed_stories_count
    if total_stories_jira > 0:
        total_stories = total_stories_jira
        completed_stories = closed_stories_count
    
    # Sprint stats
    total_sprints = db.query(func.count(models.Sprint.id)).scalar()
    active_sprints = total_sprints  # For now, use total as active
    
    # Sentiment analysis removed - return default values
    return {
        "features": {
            "total": total_features,
            "with_context": features_with_context
        },
        "stories": {
            "total": total_stories,
            "completed": completed_stories,
            "active": active_stories_count,
            "closed": closed_stories_count,
            "completion_rate": (completed_stories / total_stories * 100) if total_stories > 0 else 0
        },
        "sprints": {
            "total": total_sprints,
            "active": active_sprints
        },
        "sentiment": {
            "recent_average": None,
            "recent_count": 0
        }
    }


@router.get("/team-health")
async def get_team_health(db: Session = Depends(get_db)):
    """
    Calculate overall team health score.
    
    Note: Sentiment analysis feature has been removed.
    Returns default health metrics based on story completion rates.
    """
    # Calculate health based on story completion rates (last 30 days)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    recent_stories = db.query(models.Story).filter(
        models.Story.created_at >= thirty_days_ago
    ).all()
    
    if not recent_stories:
        return {
            "health_score": 50.0,
            "status": "unknown",
            "message": "Insufficient data for health calculation",
            "avg_sentiment": None,
            "total_blockers": 0,
            "meetings_analyzed": 0
        }
    
    # Calculate completion rate
    total_stories = len(recent_stories)
    completed_stories = sum(1 for s in recent_stories if s.status == models.StoryStatus.DONE)
    completion_rate = (completed_stories / total_stories * 100) if total_stories > 0 else 0
    
    # Health score based on completion rate
    health_score = completion_rate
    
    # Determine status
    if health_score >= 80:
        status = "excellent"
    elif health_score >= 60:
        status = "good"
    elif health_score >= 40:
        status = "fair"
    else:
        status = "needs_attention"
    
    return {
        "health_score": round(health_score, 2),
        "status": status,
        "avg_sentiment": None,
        "total_blockers": 0,
        "meetings_analyzed": 0
    }

