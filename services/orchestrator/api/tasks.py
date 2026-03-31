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
    mode: str = "ask",
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
    Poll background task progress for a specific user+agent pair.
    Returns accumulated debug events (drains the buffer) and current status.
    Pass consume_result=true when the client is ready to display the final result
    (removes it from the internal store so get_agent_result tool won't double-report).
    """
    import main as orchestrator_main

    if not orchestrator_main.orchestrator_agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator not initialized",
        )
    return orchestrator_main.orchestrator_agent.poll_bg_task(
        user_id=user_id,
        agent_id=agent_id,
        consume_result=consume_result,
    )


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    """Get task status and results."""
    import main as orchestrator_main

    if not orchestrator_main.orchestrator_agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator not initialized",
        )
    agent = orchestrator_main.orchestrator_agent
    entry = agent._task_registry.get(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    return entry
