"""Pydantic schemas for API request/response validation."""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class StoryStatus(str, Enum):
    """Story status enumeration."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    BLOCKED = "blocked"


# ============================================================================
# Feature Schemas
# ============================================================================

class FeatureBase(BaseModel):
    """Base feature schema."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)


class FeatureCreate(FeatureBase):
    """Schema for creating a new feature."""
    pass


class FeatureUpdate(BaseModel):
    """Schema for updating a feature."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    context_json: Optional[Dict[str, Any]] = None


class FeatureResponse(FeatureBase):
    """Schema for feature response."""
    id: int
    context_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    first_question: Optional[str] = None
    workflow_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Story Schemas
# ============================================================================

class StoryBase(BaseModel):
    """Base story schema."""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    acceptance_criteria: Optional[List[str]] = None
    story_points: Optional[int] = Field(None, ge=0, le=100)
    assignee: Optional[str] = None


class StoryCreate(StoryBase):
    """Schema for creating a new story."""
    feature_id: int


class StoryUpdate(BaseModel):
    """Schema for updating a story."""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    acceptance_criteria: Optional[List[str]] = None
    story_points: Optional[int] = Field(None, ge=0, le=100)
    assignee: Optional[str] = None
    status: Optional[StoryStatus] = None
    sprint_id: Optional[int] = None


class StoryResponse(StoryBase):
    """Schema for story response."""
    id: int
    feature_id: int
    jira_key: Optional[str] = None
    status: StoryStatus
    sprint_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Sprint Schemas
# ============================================================================

class SprintBase(BaseModel):
    """Base sprint schema."""
    name: str = Field(..., min_length=1, max_length=255)
    start_date: datetime
    end_date: datetime
    velocity: Optional[int] = Field(None, ge=0)


class SprintCreate(SprintBase):
    """Schema for creating a new sprint."""
    pass


class SprintUpdate(BaseModel):
    """Schema for updating a sprint."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    velocity: Optional[int] = Field(None, ge=0)
    sentiment_avg: Optional[float] = Field(None, ge=-1, le=1)


class SprintResponse(SprintBase):
    """Schema for sprint response."""
    id: int
    sentiment_avg: Optional[float] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Sentiment Log Schemas
# ============================================================================

class SentimentLogBase(BaseModel):
    """Base sentiment log schema."""
    meeting_id: str
    meeting_date: datetime
    mood_score: Optional[float] = Field(None, ge=-1, le=1)
    blockers_detected: Optional[List[str]] = None
    action_items: Optional[List[str]] = None
    transcript_summary: Optional[str] = None


class SentimentLogCreate(SentimentLogBase):
    """Schema for creating a sentiment log."""
    sprint_id: Optional[int] = None


class SentimentLogResponse(SentimentLogBase):
    """Schema for sentiment log response."""
    id: int
    sprint_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Agent Log Schemas
# ============================================================================

class AgentLogCreate(BaseModel):
    """Schema for creating an agent log."""
    agent_name: str
    action: str
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    execution_time: Optional[float] = None
    status: str
    error_message: Optional[str] = None


class AgentLogResponse(AgentLogCreate):
    """Schema for agent log response."""
    id: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Agent Communication Schemas
# ============================================================================

class ClarificationRequest(BaseModel):
    """Request for feature clarification by Dynamic Agent."""
    feature_id: int
    user_response: Optional[str] = None


class ClarificationResponse(BaseModel):
    """Response from Dynamic Agent with next question or completion."""
    feature_id: int
    question: Optional[str] = None
    is_complete: bool
    context_summary: Optional[Dict[str, Any]] = None


class GenerateStoriesRequest(BaseModel):
    """Request to generate stories from clarified feature."""
    feature_id: int


class GenerateStoriesResponse(BaseModel):
    """Response with generated stories."""
    feature_id: int
    stories: List[StoryResponse]
    epic_summary: Optional[str] = None


class QueryRequest(BaseModel):
    """General query to the Scrum Master."""
    query: str
    context: Optional[Dict[str, Any]] = None


class QueryResponse(BaseModel):
    """Response from the Scrum Master."""
    response: str
    data: Optional[Dict[str, Any]] = None
    suggestions: Optional[List[str]] = None


class AnalyticsRequest(BaseModel):
    """Request for sprint analytics."""
    sprint_id: Optional[int] = None


class AnalyticsResponse(BaseModel):
    """Sprint analytics response."""
    sprint_id: int
    sprint_name: str
    total_stories: int
    completed_stories: int
    total_points: int
    completed_points: int
    velocity: int
    sentiment_avg: Optional[float] = None
    top_blockers: Optional[List[str]] = None
    team_load: Optional[Dict[str, Any]] = None

