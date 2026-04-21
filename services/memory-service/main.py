"""
Memory Service - FastAPI application for managing agent memory.

Provides endpoints for:
- Fast context storage (Redis)
- Conversation history (Redis)
- Long-term memory (Qdrant)
- Agent state (PostgreSQL)
- Task tracking (PostgreSQL)
- Logs (PostgreSQL)
- Token statistics (PostgreSQL)
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.config import get_settings
from shared.exceptions import BalbesException

# Initialize settings
settings = get_settings()

# Setup logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("memory-service")


# Global clients (will be initialized in lifespan)
redis_client = None
qdrant_client = None
postgres_client = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    FastAPI lifespan context manager.

    Handles startup and shutdown of database connections.
    """
    global redis_client, qdrant_client, postgres_client

    logger.info("Starting Memory Service...")

    # Import clients here to avoid circular imports
    from clients.postgres_client import PostgresClient
    from clients.qdrant_client import QdrantClient
    from clients.redis_client import RedisClient

    # Initialize clients
    try:
        logger.info("Connecting to Redis...")
        redis_client = RedisClient()
        await redis_client.connect()

        logger.info("Connecting to Qdrant...")
        qdrant_client = QdrantClient()
        await qdrant_client.connect()

        logger.info("Connecting to PostgreSQL...")
        postgres_client = PostgresClient()
        await postgres_client.connect()

        logger.info("All database connections established")

    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        raise

    # App is running
    yield

    # Shutdown: close connections
    logger.info("Shutting down Memory Service...")

    if redis_client:
        await redis_client.close()
    if qdrant_client:
        await qdrant_client.close()
    if postgres_client:
        await postgres_client.close()

    logger.info("Memory Service stopped")


# Create FastAPI application
app = FastAPI(
    title="Memory Service API",
    description="Memory management for Balbes Multi-Agent System",
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
@app.exception_handler(BalbesException)
async def balbes_exception_handler(request: Request, exc: BalbesException) -> JSONResponse:
    """Handle custom Balbes exceptions"""
    logger.warning(f"Balbes exception: {exc.message}", extra={"details": exc.details})
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": exc.message,
            "error_code": exc.__class__.__name__,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


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
        dict: Health status of the service and all connections
    """
    health_status = {
        "service": "memory-service",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Check Redis connection
    try:
        if redis_client:
            await redis_client.ping()
            health_status["redis"] = "connected"
        else:
            health_status["redis"] = "not_initialized"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        health_status["redis"] = "disconnected"
        health_status["status"] = "unhealthy"

    # Check Qdrant connection
    try:
        if qdrant_client:
            await qdrant_client.health_check()
            health_status["qdrant"] = "connected"
        else:
            health_status["qdrant"] = "not_initialized"
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        health_status["qdrant"] = "disconnected"
        health_status["status"] = "unhealthy"

    # Check PostgreSQL connection
    try:
        if postgres_client:
            await postgres_client.health_check()
            health_status["postgres"] = "connected"
        else:
            health_status["postgres"] = "not_initialized"
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        health_status["postgres"] = "disconnected"
        health_status["status"] = "unhealthy"

    return health_status


# Root endpoint
@app.get("/")
async def root() -> dict:
    """Root endpoint with service information"""
    return {
        "service": "Memory Service",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


# Import and include API routers
from api import (
    agent_session,
    agents,
    context,
    history,
    identity,
    logs,
    memory,
    tasks,
    tokens,
    user_settings,
)

app.include_router(context.router, prefix="/api/v1", tags=["context"])
app.include_router(history.router, prefix="/api/v1", tags=["history"])
app.include_router(memory.router, prefix="/api/v1", tags=["memory"])
app.include_router(agent_session.router, prefix="/api/v1", tags=["agent-session"])
app.include_router(agents.router, prefix="/api/v1", tags=["agents"])
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
app.include_router(logs.router, prefix="/api/v1", tags=["logs"])
app.include_router(tokens.router, prefix="/api/v1", tags=["tokens"])
app.include_router(identity.router, prefix="/api/v1", tags=["identity"])
app.include_router(user_settings.router, prefix="/api/v1", tags=["user-settings"])


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Memory Service on port {settings.memory_service_port}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.memory_service_port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )
