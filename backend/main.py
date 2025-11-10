"""
AutoScrum - AI-powered Scrum Master Assistant

Main FastAPI application entry point.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time
import logging
import os
from typing import Dict, Any

from db.database import init_db, engine
from routes import (
    feature_router,
    query_router,
    analytics_router,
    servicenow_router,
    transcript_router
)
from utils.config_loader import get_config
from memory.redis_client import get_redis_client




# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

init_db()

# ============================================================================
# Application Lifecycle Events
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("🚀 Starting AutoScrum backend...")
    
    # Initialize database
    try:
        init_db()
        db_type = "SQLite" if os.getenv("DATABASE_URL", "").startswith("sqlite") else "PostgreSQL"
        logger.info(f"✅ Database initialized ({db_type})")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
    
    # Test Redis connection (mandatory)
    try:
        redis_client = get_redis_client()
        if redis_client.ping():
            logger.info("✅ Redis connected successfully")
        else:
            logger.error("❌ Redis connection failed")
            raise ConnectionError("Redis is not responding. Please start Redis server.")
    except ConnectionError as e:
        logger.error(f"❌ Redis connection required but failed: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Redis initialization error: {e}")
        raise
    
    # Load configuration
    try:
        config = get_config()
        config_status = config.to_dict()
        logger.info(f"✅ Configuration loaded: {config_status}")
    except Exception as e:
        logger.error(f"❌ Configuration loading failed: {e}")
    
    logger.info("🎉 AutoScrum backend ready!")
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down AutoScrum backend...")


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="AutoScrum API",
    description="AI-powered Scrum Master assistant with multi-agent orchestration",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)


# ============================================================================
# Middleware
# ============================================================================

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add response time to headers."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    logger.info(f"📥 {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"📤 {request.method} {request.url.path} - {response.status_code}")
    return response


# ============================================================================
# Exception Handlers
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"❌ Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "path": request.url.path
        }
    )


# ============================================================================
# Root Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "AutoScrum API",
        "version": "1.0.0",
        "description": "AI-powered Scrum Master assistant",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint.
    
    Returns service health status and component availability.
    """
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "components": {}
    }
    
    # Check database
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health_status["components"]["database"] = "healthy"
    except Exception as e:
        health_status["components"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check Redis (mandatory)
    try:
        redis_client = get_redis_client()
        if redis_client.ping():
            health_status["components"]["redis"] = "healthy"
        else:
            health_status["components"]["redis"] = "unhealthy: not responding"
            health_status["status"] = "unhealthy"
    except Exception as e:
        health_status["components"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"
    
    # Check OpenAI
    try:
        from utils.openai_llm import get_llm_client
        llm_client = get_llm_client()
        health_status["components"]["openai"] = "configured"
    except Exception as e:
        health_status["components"]["openai"] = f"not configured: {str(e)}"
    
    # Check MCP clients
    config = get_config()
    health_status["components"]["jira"] = "configured" if config.jira else "not configured"
    health_status["components"]["servicenow"] = "configured" if config.servicenow else "not configured"
    
    return health_status


@app.get("/config")
async def get_configuration():
    """
    Get sanitized configuration status.
    
    Does not expose sensitive credentials.
    """
    config = get_config()
    return config.to_dict()


@app.get("/agents")
async def list_agents():
    """
    List available agents and their status.
    """
    return {
        "agents": [
            {
                "name": "DynamicContextAgent",
                "description": "Clarifies feature requirements through conversation",
                "status": "available"
            },
            {
                "name": "StoryCreatorAgent",
                "description": "Generates Jira stories from clarified context",
                "status": "available"
            },
            {
                "name": "PrioritizationAgent",
                "description": "Assigns tasks based on team capacity and skills",
                "status": "available"
            }
        ],
        "orchestrator": {
            "name": "Orchestrator",
            "description": "Coordinates multi-agent workflows",
            "status": "available"
        }
    }


# ============================================================================
# Include Routers
# ============================================================================

app.include_router(feature_router)
app.include_router(query_router)
app.include_router(analytics_router)
app.include_router(servicenow_router)
app.include_router(transcript_router)



# ============================================================================
# Development Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Load config for port
    config = get_config()
    host = config.app.api_host if config.app else "0.0.0.0"
    port = config.app.api_port if config.app else 8000
    
    logger.info(f"🚀 Starting development server on {host}:{port}")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )

