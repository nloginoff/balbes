"""
History API endpoints (conversation history in Redis).
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

router = APIRouter()


class HistoryAddRequest(BaseModel):
    """Request model for adding to history"""

    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., description="Message content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional metadata")


@router.post("/history/{agent_id}")
async def add_to_history(
    agent_id: str,
    request: HistoryAddRequest,
) -> dict[str, Any]:
    """
    Add message to agent's conversation history.

    Args:
        agent_id: Agent identifier
        request: Message data

    Returns:
        Status and history length
    """
    import main as memory_main

    redis_client = memory_main.redis_client

    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis client not available",
        )

    result = await redis_client.add_to_history(
        agent_id=agent_id,
        role=request.role,
        content=request.content,
        metadata=request.metadata,
    )

    return result


@router.get("/history/{agent_id}")
async def get_history(
    agent_id: str,
    limit: int = Query(default=50, ge=1, le=100, description="Max messages to return"),
) -> dict[str, Any]:
    """
    Get agent's conversation history.

    Args:
        agent_id: Agent identifier
        limit: Maximum messages to return

    Returns:
        Messages list and total count
    """
    import main as memory_main

    redis_client = memory_main.redis_client

    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis client not available",
        )

    result = await redis_client.get_history(agent_id=agent_id, limit=limit)
    return result


@router.delete("/history/{agent_id}")
async def clear_history(
    agent_id: str,
) -> dict[str, str]:
    """
    Clear agent's conversation history.

    Args:
        agent_id: Agent identifier

    Returns:
        Status
    """
    import main as memory_main

    redis_client = memory_main.redis_client

    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis client not available",
        )

    result = await redis_client.clear_history(agent_id=agent_id)
    return result
