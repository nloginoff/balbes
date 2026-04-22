"""
Orchestrator API routes for task management.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger("orchestrator.api.tasks")

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class TaskCreateRequest(BaseModel):
    """JSON body for POST /api/v1/tasks (application/json)."""

    user_id: str = Field(..., description="Canonical user id (Memory UUID)")
    description: str = Field(..., description="User message / task text")
    chat_id: str | None = None
    agent_id: str | None = None
    model_id: str | None = None
    source: str = "user"
    debug: bool = False
    mode: str = "ask"
    bot_id: str | None = None
    attachments: list[dict[str, Any]] | None = None
    vision_tier: str | None = Field(
        default=None,
        description="Override vision tier for this request: cheap | medium | premium",
    )
    image_generation_tier: str | None = Field(
        default=None,
        description="Override image generation tier for generate_image: cheap | medium | premium",
    )


@router.post("")
async def create_task(req: TaskCreateRequest) -> dict:
    """
    Create and execute a task within a chat session.

    Clients must send ``Content-Type: application/json`` with a TaskCreateRequest body.
    """
    import main as orchestrator_main

    if not orchestrator_main.orchestrator_agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator not initialized",
        )

    try:
        result = await orchestrator_main.orchestrator_agent.execute_task(
            description=req.description,
            user_id=req.user_id,
            chat_id=req.chat_id,
            agent_id=req.agent_id,
            model_id=req.model_id,
            context={
                "source": req.source,
                "debug": req.debug,
                "mode": req.mode,
                "bot_id": req.bot_id,
                "attachments": req.attachments,
                "vision_tier": req.vision_tier,
                "image_generation_tier": req.image_generation_tier,
            },
        )
        return result

    except Exception as e:
        logger.error(f"Task creation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task creation failed: {str(e)}",
        )


@router.post("/cancel")
async def cancel_task(user_id: str) -> dict:
    """
    Cancel any in-progress task for the given user.
    The cancellation flag is checked between LLM tool-call rounds.
    """
    import main as orchestrator_main

    if not orchestrator_main.orchestrator_agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator not initialized",
        )
    orchestrator_main.orchestrator_agent.cancel_task(user_id)
    return {"status": "cancel_requested", "user_id": user_id}


@router.get("")
async def list_tasks(user_id: str | None = None, limit: int = 20) -> dict:
    """
    List recent tasks from the registry.
    If user_id given, filter to that user. Running tasks appear first.
    """
    import main as orchestrator_main

    if not orchestrator_main.orchestrator_agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator not initialized",
        )
    tasks = orchestrator_main.orchestrator_agent.list_tasks(user_id=user_id, limit=limit)
    return {"tasks": tasks, "count": len(tasks)}


@router.get("/fg/events")
async def fg_events(
    user_id: str,
    agent_id: str,
) -> dict:
    """
    Poll live debug events for a FOREGROUND task that is currently executing.
    Returns accumulated events (drains the buffer) and whether the task is still running.
    Use this while waiting for POST /api/v1/tasks to return — poll every 5s.
    """
    import main as orchestrator_main

    if not orchestrator_main.orchestrator_agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator not initialized",
        )
    return orchestrator_main.orchestrator_agent.drain_fg_debug(user_id, agent_id)


@router.get("/bg/events")
async def bg_events(
    user_id: str,
    agent_id: str,
    consume_result: bool = False,
) -> dict:
    """
    Poll background task status and optional debug events.
    """
    import main as orchestrator_main

    if not orchestrator_main.orchestrator_agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator not initialized",
        )
    return orchestrator_main.orchestrator_agent.poll_bg_task(
        user_id, agent_id, consume_result=consume_result
    )
