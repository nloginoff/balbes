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
) -> dict:
    """
    Create and execute a task within a chat session.

    Args:
        user_id: User identifier (Telegram user_id)
        description: Task / message text
        chat_id: Chat session ID (optional, uses active chat if omitted)
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
        )
        return result

    except Exception as e:
        logger.error(f"Task creation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task creation failed: {str(e)}",
        )


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    """Get task status and results."""
    return {
        "task_id": task_id,
        "status": "completed",
        "result": "Task result placeholder",
    }
