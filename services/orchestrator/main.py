"""
Orchestrator Service - FastAPI приложение для главного агента.

Управляет:
- Task processing API
- Orchestrator Agent lifecycle
- Telegram Bot integration
- WebSocket для realtime updates
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from agent import OrchestratorAgent
from api import notifications as notifications_api
from api import tasks as tasks_api
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from notifications import NotificationService

from shared.config import get_settings

# Initialize settings
settings = get_settings()

# Setup logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("orchestrator")


# Global instances
orchestrator_agent: OrchestratorAgent | None = None
notification_service: NotificationService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    FastAPI lifespan context manager.

    Handles startup and shutdown of agent and services.
    """
    global orchestrator_agent, notification_service

    logger.info("Starting Orchestrator Service...")

    try:
        # Initialize agent
        orchestrator_agent = OrchestratorAgent()
        await orchestrator_agent.connect()
        logger.info("Orchestrator Agent initialized")

        # Initialize notification service
        notification_service = NotificationService()
        await notification_service.connect()
        logger.info("Notification Service initialized")

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise

    # App is running
    yield

    # Shutdown
    logger.info("Shutting down Orchestrator Service...")

    if orchestrator_agent:
        await orchestrator_agent.close()

    if notification_service:
        await notification_service.close()

    logger.info("Orchestrator Service stopped")


# Create FastAPI application
app = FastAPI(
    title="Orchestrator API",
    description="Main orchestrator agent for Balbes Multi-Agent System",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions"""
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "error_code": "INTERNAL_ERROR",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


# Health check endpoint
@app.get("/health")
async def health_check() -> dict:
    """
    Health check endpoint.

    Returns:
        dict: Health status
    """
    if not orchestrator_agent:
        return {
            "service": "orchestrator",
            "status": "unhealthy",
            "reason": "Agent not initialized",
        }

    agent_status = await orchestrator_agent.get_agent_status()

    return {
        "service": "orchestrator",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent_status,
    }


# Include API routers
app.include_router(tasks_api.router)
app.include_router(notifications_api.router)


# Root endpoint
@app.get("/")
async def root() -> dict:
    """Root endpoint with service information"""
    return {
        "service": "Orchestrator",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/api/v1/status")
async def get_status() -> dict:
    """
    Get orchestrator status.

    Returns:
        Orchestrator status
    """
    if not orchestrator_agent:
        return {
            "status": "unavailable",
        }

    return await orchestrator_agent.get_agent_status()


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Orchestrator Service on port {settings.orchestrator_port}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.orchestrator_port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )
