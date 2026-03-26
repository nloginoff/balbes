"""
Tasks API endpoints.
"""

import logging

from auth import TaskCreate
from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger("web_backend.api.tasks")

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("")
async def get_tasks(agent_id: str = None, user_id: str = None) -> dict:
    """
    Get tasks.

    Args:
        agent_id: Optional agent ID filter

    Returns:
        List of tasks
    """
    import main as backend_main

    if not backend_main.api_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API service not initialized",
        )

    tasks = await backend_main.api_service.get_tasks(agent_id)

    return {
        "total": len(tasks),
        "tasks": tasks,
    }


@router.post("")
async def create_task(request: TaskCreate, user_id: str) -> dict:
    """
    Create and submit task.

    Args:
        request: Task creation request

    Returns:
        Created task result
    """
    import main as backend_main

    if not backend_main.api_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API service not initialized",
        )

    result = await backend_main.api_service.submit_task(
        agent_id=request.agent_id,
        description=request.description,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create task",
        )

    return result


@router.get("/{task_id}")
async def get_task(task_id: str, user_id: str) -> dict:
    """
    Get task details.

    Args:
        task_id: Task ID

    Returns:
        Task details
    """
    return {
        "task_id": task_id,
        "status": "completed",
        "result": "Task details placeholder",
    }
