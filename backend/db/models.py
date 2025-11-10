"""SQLAlchemy models for AutoScrum database."""

from sqlalchemy import Column, Integer, String, Text, JSON, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
from .database import Base


class StoryStatus(str, enum.Enum):
    """Story status enumeration."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    BLOCKED = "blocked"


class Feature(Base):
    """
    Feature model representing a product feature request.
    
    Attributes:
        id: Primary key
        name: Feature name
        description: Initial feature description
        context_json: JSON containing clarified context from Dynamic Agent
        created_at: Timestamp of creation
        updated_at: Timestamp of last update
        stories: Relationship to Story objects
    """
    __tablename__ = "features"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False)
    context_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    stories = relationship("Story", back_populates="feature", cascade="all, delete-orphan")


class Story(Base):
    """
    Story model representing Jira user stories.
    
    Attributes:
        id: Primary key
        feature_id: Foreign key to Feature
        jira_key: Jira story key (e.g., PROJ-123)
        title: Story title
        description: Story description
        acceptance_criteria: List of acceptance criteria
        story_points: Estimated story points
        assignee: Assigned team member
        status: Current story status
        sprint_id: Foreign key to Sprint
        created_at: Timestamp of creation
        updated_at: Timestamp of last update
    """
    __tablename__ = "stories"

    id = Column(Integer, primary_key=True, index=True)
    feature_id = Column(Integer, ForeignKey("features.id"), nullable=False)
    jira_key = Column(String(50), unique=True, nullable=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    acceptance_criteria = Column(JSON, nullable=True)
    story_points = Column(Integer, nullable=True)
    assignee = Column(String(255), nullable=True)
    status = Column(Enum(StoryStatus), default=StoryStatus.TODO)
    sprint_id = Column(Integer, ForeignKey("sprints.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    feature = relationship("Feature", back_populates="stories")
    sprint = relationship("Sprint", back_populates="stories")


class Sprint(Base):
    """
    Sprint model representing Scrum sprints.
    
    Attributes:
        id: Primary key
        name: Sprint name
        start_date: Sprint start date
        end_date: Sprint end date
        velocity: Team velocity (story points per sprint)
        sentiment_avg: Average sentiment score for the sprint
        created_at: Timestamp of creation
        stories: Relationship to Story objects
        sentiment_logs: Relationship to SentimentLog objects
    """
    __tablename__ = "sprints"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    velocity = Column(Integer, nullable=True)
    sentiment_avg = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    stories = relationship("Story", back_populates="sprint")
    sentiment_logs = relationship("SentimentLog", back_populates="sprint")


class SentimentLog(Base):
    """
    Sentiment log from meeting transcript analysis.
    
    Attributes:
        id: Primary key
        sprint_id: Foreign key to Sprint
        meeting_id: Zoom meeting ID
        meeting_date: Date of the meeting
        mood_score: Overall mood score (-1 to 1)
        blockers_detected: List of detected blockers
        action_items: Generated action items
        transcript_summary: AI-generated summary
        created_at: Timestamp of log creation
    """
    __tablename__ = "sentiment_logs"

    id = Column(Integer, primary_key=True, index=True)
    sprint_id = Column(Integer, ForeignKey("sprints.id"), nullable=True)
    meeting_id = Column(String(100), nullable=False, index=True)
    meeting_date = Column(DateTime(timezone=True), nullable=False)
    mood_score = Column(Float, nullable=True)  # -1 (negative) to 1 (positive)
    blockers_detected = Column(JSON, nullable=True)
    action_items = Column(JSON, nullable=True)
    transcript_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    sprint = relationship("Sprint", back_populates="sentiment_logs")


class AgentLog(Base):
    """
    Agent activity log for monitoring and debugging.
    
    Attributes:
        id: Primary key
        agent_name: Name of the agent (e.g., DynamicContextAgent)
        action: Action performed
        input_data: Input data snapshot
        output_data: Output data snapshot
        execution_time: Time taken to execute (seconds)
        status: Success or failure status
        error_message: Error message if failed
        timestamp: Timestamp of action
    """
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, index=True)
    agent_name = Column(String(100), nullable=False, index=True)
    action = Column(String(255), nullable=False)
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    execution_time = Column(Float, nullable=True)
    status = Column(String(50), nullable=False)  # success, failure, partial
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)




class TranscriptAction(Base):
    """
    Persisted actions created by the transcript agent to avoid duplicates and for audit.
    """
    __tablename__ = "transcript_actions"

    id = Column(Integer, primary_key=True, index=True)
    action_key = Column(String(512), unique=True, nullable=False, index=True)
    person = Column(String(255), nullable=True, index=True)
    story = Column(String(100), nullable=True, index=True)
    diagnosis = Column(String(100), nullable=False, index=True)
    confidence = Column(Float, nullable=True)
    payload = Column(JSON, nullable=True)
    response = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
