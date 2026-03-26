"""
Tasks API endpoints (PostgreSQL-backed task tracking).
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from shared.models import TaskStatus

router = APIRouter()


class TaskCreateRequest(BaseModel):
    """Request model for creating task"""

    agent_id: str = Field(..., description="Target agent ID")
    description: str = Field(..., description="Task description")
    payload: dict[str, Any] = Field(default_factory=dict, description="Task payload")
    created_by: str = Field(..., description="Creator (agent or user)")
    parent_task_id: UUID | None = Field(default=None, description="Parent task ID")


class TaskUpdateRequest(BaseModel):
    """Request model for updating task"""

    status: TaskStatus = Field(..., description="New status")
    result: dict[str, Any] | None = Field(default=None, description="Task result")
    error: str | None = Field(default=None, description="Error message if failed")


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(
    request: TaskCreateRequest,
) -> dict[str, Any]:
    """
    Create new task.

    Args:
        request: Task data

    Returns:
        Created task
    """
    import main as memory_main

    postgres_client = memory_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL client not available",
        )

    task = await postgres_client.create_task(
        agent_id=request.agent_id,
        description=request.description,
        created_by=request.created_by,
        payload=request.payload,
        parent_task_id=request.parent_task_id,
    )

    return {
        "task_id": str(task["id"]),
        "status": task["status"],
        "created_at": task["created_at"].isoformat(),
    }


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: UUID,
) -> dict[str, Any]:
    """
    Get task by ID.

    Args:
        task_id: Task UUID

    Returns:
        Task data

    Raises:
        404: If task not found
    """
    import main as memory_main

    postgres_client = memory_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL client not available",
        )

    task = await postgres_client.get_task(task_id=task_id)

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )

    # Parse payload if it's a JSON string
    import json

    payload = task.get("payload", {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}

    # Format response
    duration_ms = None
    if task["started_at"] and task["completed_at"]:
        duration = task["completed_at"] - task["started_at"]
        duration_ms = int(duration.total_seconds() * 1000)

    return {
        "id": str(task["id"]),
        "agent_id": task["agent_id"],
        "description": task["description"],
        "status": task["status"],
        "result": task["result"],
        "error": task["error"],
        "created_at": task["created_at"].isoformat(),
        "started_at": task["started_at"].isoformat() if task["started_at"] else None,
        "completed_at": task["completed_at"].isoformat() if task["completed_at"] else None,
        "duration_ms": duration_ms,
        "tokens_used": payload.get("tokens_used", 0),
    }


@router.get("/tasks")
async def list_tasks(
    agent_id: str | None = Query(default=None, description="Filter by agent"),
    status: TaskStatus | None = Query(default=None, description="Filter by status"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> dict[str, Any]:
    """
    List tasks with filters.

    Args:
        agent_id: Optional agent filter
        status: Optional status filter
        limit: Max results
        offset: Pagination offset

    Returns:
        Tasks list with pagination
    """
    import main as memory_main

    postgres_client = memory_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL client not available",
        )

    result = await postgres_client.list_tasks(
        agent_id=agent_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    # Format tasks
    formatted_tasks = []
    for task in result["tasks"]:
        formatted_task = {
            "id": str(task["id"]),
            "agent_id": task["agent_id"],
            "description": task["description"],
            "status": task["status"],
            "created_by": task["created_by"],
            "created_at": task["created_at"].isoformat(),
            "started_at": task["started_at"].isoformat() if task["started_at"] else None,
            "completed_at": task["completed_at"].isoformat() if task["completed_at"] else None,
        }
        formatted_tasks.append(formatted_task)

    return {
        "tasks": formatted_tasks,
        "total": result["total"],
        "limit": result["limit"],
        "offset": result["offset"],
    }


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: UUID,
    request: TaskUpdateRequest,
) -> dict[str, str]:
    """
    Update task status and result.

    Args:
        task_id: Task UUID
        request: Update data

    Returns:
        Status
    """
    import main as memory_main

    postgres_client = memory_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL client not available",
        )

    await postgres_client.update_task_status(
        task_id=task_id,
        status=request.status,
        result=request.result,
        error=request.error,
    )

    return {"status": "updated"}
