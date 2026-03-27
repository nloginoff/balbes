"""
Skills Registry Service - FastAPI application for managing agent skills.

Provides endpoints for:
- Skill registration and management
- Semantic search across skills
- Version management
- Metadata storage
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
logger = logging.getLogger("skills-registry")


# Global clients (will be initialized in lifespan)
postgres_client = None
qdrant_client = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    FastAPI lifespan context manager.

    Handles startup and shutdown of database connections.
    """
    global postgres_client, qdrant_client

    logger.info("Starting Skills Registry Service...")

    # Import clients here to avoid circular imports
    from clients.postgres_client import PostgresClient
    from clients.qdrant_client import QdrantClient

    # Initialize clients
    try:
        logger.info("Connecting to PostgreSQL...")
        postgres_client = PostgresClient()
        await postgres_client.connect()

        logger.info("Connecting to Qdrant...")
        qdrant_client = QdrantClient()
        await qdrant_client.connect()

        logger.info("All database connections established")

    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        raise

    # App is running
    yield

    # Shutdown: close connections
    logger.info("Shutting down Skills Registry Service...")

    if postgres_client:
        await postgres_client.close()
    if qdrant_client:
        await qdrant_client.close()

    logger.info("Skills Registry Service stopped")


# Create FastAPI application
app = FastAPI(
    title="Skills Registry API",
    description="Skill management and discovery for Balbes Multi-Agent System",
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
        "service": "skills-registry",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

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

    return health_status


# Root endpoint
@app.get("/")
async def root() -> dict:
    """Root endpoint with service information"""
    return {
        "service": "Skills Registry",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


# Import and include API routers
from api import search, skills

app.include_router(skills.router, prefix="/api/v1", tags=["skills"])
app.include_router(search.router, prefix="/api/v1", tags=["search"])


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Skills Registry Service on port {settings.skills_registry_port}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.skills_registry_port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )
