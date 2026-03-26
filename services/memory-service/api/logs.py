"""
Logs API endpoints (PostgreSQL-backed action logs).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

router = APIRouter()


class LogCreateRequest(BaseModel):
    """Request model for creating log entry"""

    agent_id: str = Field(..., description="Agent identifier")
    action: str = Field(..., description="Action name")
    details: dict[str, Any] = Field(default_factory=dict, description="Action details")
    task_id: UUID | None = Field(default=None, description="Related task ID")
    duration_ms: int | None = Field(default=None, description="Action duration")
    success: bool = Field(default=True, description="Success flag")
    error: str | None = Field(default=None, description="Error message if failed")


@router.post("/logs", status_code=status.HTTP_201_CREATED)
async def create_log(
    request: LogCreateRequest,
) -> dict[str, str]:
    """
    Create action log entry.

    Args:
        request: Log data

    Returns:
        Log ID
    """
    import main as memory_main

    postgres_client = memory_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL client not available",
        )

    log_id = await postgres_client.create_log(
        agent_id=request.agent_id,
        action=request.action,
        details=request.details,
        task_id=request.task_id,
        duration_ms=request.duration_ms,
        success=request.success,
        error=request.error,
    )

    return {"log_id": str(log_id), "status": "created"}


@router.get("/logs")
async def query_logs(  # noqa: B008
    agent_id: str | None = Query(default=None, description="Filter by agent"),
    task_id: UUID | None = Query(default=None, description="Filter by task"),
    action: str | None = Query(default=None, description="Filter by action"),
    success: bool | None = Query(default=None, description="Filter by success"),
    from_time: datetime | None = Query(default=None, description="Start time"),
    to_time: datetime | None = Query(default=None, description="End time"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
) -> dict[str, Any]:
    """
    Query action logs with filters.

    Args:
        Various filters

    Returns:
        Logs list with pagination
    """
    import main as memory_main

    postgres_client = memory_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL client not available",
        )

    result = await postgres_client.query_logs(
        agent_id=agent_id,
        task_id=task_id,
        action=action,
        success=success,
        from_time=from_time,
        to_time=to_time,
        limit=limit,
        offset=offset,
    )

    # Format logs
    formatted_logs = []
    for log in result["logs"]:
        formatted_log = {
            "id": str(log["id"]),
            "agent_id": log["agent_id"],
            "timestamp": log["timestamp"].isoformat(),
            "action": log["action"],
            "details": log["details"],
            "task_id": str(log["task_id"]) if log["task_id"] else None,
            "duration_ms": log["duration_ms"],
            "success": log["success"],
            "error": log["error"],
        }
        formatted_logs.append(formatted_log)

    return {
        "logs": formatted_logs,
        "total": result["total"],
        "limit": result["limit"],
        "offset": result["offset"],
    }
