"""
Orchestrator API routes for task management.
"""

import logging

from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger("orchestrator.api.tasks")

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("")
async def create_task(
    user_id: str,
    description: str,
    chat_id: str | None = None,
    agent_id: str | None = None,
    model_id: str | None = None,
    source: str = "user",
    debug: bool = False,
    mode: str = "agent",
) -> dict:
    """
    Create and execute a task within a chat session.

    Args:
        user_id: User identifier (Telegram user_id)
        description: Task / message text
        chat_id: Chat session ID (optional, uses active chat if omitted)
        agent_id: Agent to use (orchestrator | coder | ...). Defaults to 'orchestrator'.
        model_id: Override model for this task (e.g. heartbeat uses a fixed free model).
        source: Origin of the task — "user" | "heartbeat" (used for activity log tagging).
        debug: If true, collect execution trace events and return them in response.
        mode: "agent" (all tools) | "ask" (no exec/write tools — read-only).
    """
    import main as orchestrator_main

    if not orchestrator_main.orchestrator_agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator not initialized",
        )

    try:
        result = await orchestrator_main.orchestrator_agent.execute_task(
            description=description,
            user_id=user_id,
            chat_id=chat_id,
            agent_id=agent_id,
            model_id=model_id,
            context={"source": source, "debug": debug, "mode": mode},
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


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    """Get task status and results."""
    return {
        "task_id": task_id,
        "status": "completed",
        "result": "Task result placeholder",
    }
