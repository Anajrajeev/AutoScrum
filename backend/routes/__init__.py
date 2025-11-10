"""API routes package for AutoScrum."""

from .feature_routes import router as feature_router
from .query_routes import router as query_router
from .analytics_routes import router as analytics_router
from .servicenow_routes import router as servicenow_router
from .transcript_routes import router as transcript_router

__all__ = [
    "feature_router",
    "query_router",
    "analytics_router",
    "servicenow_router",
    "transcript_router"
]

