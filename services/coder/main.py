"""
Coder Service - FastAPI приложение для Coder Agent.

Управляет:
- Skill generation API
- Code execution and testing
- Skill validation
- Registry integration
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from agent import CoderAgent
from api import skills as skills_api
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.config import get_settings

# Initialize settings
settings = get_settings()

# Setup logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("coder")


# Global agent instance
coder_agent: CoderAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    FastAPI lifespan context manager.

    Handles startup and shutdown of Coder Agent.
    """
    global coder_agent

    logger.info("Starting Coder Service...")

    try:
        coder_agent = CoderAgent()
        await coder_agent.connect()
        logger.info("Coder Agent initialized")

    except Exception as e:
        logger.error(f"Failed to initialize Coder Agent: {e}")
        raise

    # App is running
    yield

    # Shutdown
    logger.info("Shutting down Coder Service...")

    if coder_agent:
        await coder_agent.close()

    logger.info("Coder Service stopped")


# Create FastAPI application
app = FastAPI(
    title="Coder API",
    description="Autonomous code generation and skill creation service",
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
            "timestamp": datetime.now(UTC).isoformat(),
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
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


# Include API routers
app.include_router(skills_api.router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict:
    """
    Health check endpoint.

    Returns:
        dict: Health status
    """
    if not coder_agent:
        return {
            "service": "coder",
            "status": "unhealthy",
            "reason": "Agent not initialized",
        }

    return {
        "service": "coder",
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_id": coder_agent.agent_id,
    }


# Root endpoint
@app.get("/")
async def root() -> dict:
    """Root endpoint with service information"""
    return {
        "service": "Coder",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
        "description": "Autonomous code generation and skill creation",
    }


# Status endpoint
@app.get("/api/v1/status")
async def get_status() -> dict:
    """
    Get Coder service status.

    Returns:
        Coder service status
    """
    if not coder_agent:
        return {"status": "unavailable"}

    generated_skills = await coder_agent.get_generated_skills()

    return {
        "service": "coder",
        "status": "online",
        "agent_id": coder_agent.agent_id,
        "generated_skills_count": len(generated_skills),
        "timestamp": datetime.now(UTC).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Coder Service on port {settings.coder_port}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.coder_port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )
