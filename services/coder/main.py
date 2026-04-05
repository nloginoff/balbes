"""
Coder Service - FastAPI приложение для Coder Agent.

Управляет:
- Skill generation API
- Full LLM + tools execution (HTTP) for orchestrator delegation
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from agent import CoderAgent as SkillCoderAgent
from api import execute as execute_api
from api import skills as skills_api
from coder_llm import connect_coding_engine, get_coding_engine
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

# Global skill-builder (legacy API) + full LLM engine
skill_coder: SkillCoderAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Startup: skill builder + OrchestratorAgent(coder) for /api/v1/agent/execute."""
    global skill_coder

    logger.info("Starting Coder Service...")

    try:
        skill_coder = SkillCoderAgent()
        await skill_coder.connect()

        await connect_coding_engine()
        app.state.coding_engine = get_coding_engine()

        logger.info("Coder Service (skills + LLM engine) initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Coder Service: {e}")
        raise

    yield

    logger.info("Shutting down Coder Service...")

    eng = getattr(app.state, "coding_engine", None)
    if eng:
        await eng.close()

    if skill_coder:
        await skill_coder.close()

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


# Include API routers
app.include_router(skills_api.router)
app.include_router(execute_api.router)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict:
    """Health status for skill builder and LLM engine."""
    eng = getattr(app.state, "coding_engine", None)
    if not skill_coder or not eng:
        return {
            "service": "coder",
            "status": "unhealthy",
            "reason": "Agents not initialized",
        }

    return {
        "service": "coder",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "skill_agent_id": skill_coder.agent_id,
        "llm_engine_id": getattr(eng, "agent_id", None),
    }


# Root endpoint
@app.get("/")
async def root() -> dict:
    """Root endpoint for service information"""
    return {
        "service": "Coder",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
        "description": "Skills API + LLM/tools execute for delegation",
    }


# Status endpoint
@app.get("/api/v1/status")
async def get_status() -> dict:
    """Coder service status"""
    if not skill_coder:
        return {"status": "unavailable"}

    generated_skills = await skill_coder.get_generated_skills()
    eng = getattr(app.state, "coding_engine", None)

    return {
        "service": "coder",
        "status": "online",
        "skill_agent_id": skill_coder.agent_id,
        "generated_skills_count": len(generated_skills),
        "llm_engine_ready": eng is not None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
