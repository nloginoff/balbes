"""
Context API endpoints (Redis-backed fast memory).
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter()


class ContextSetRequest(BaseModel):
    """Request model for setting context"""

    key: str = Field(..., description="Context key")
    value: dict[str, Any] = Field(..., description="Context value")
    ttl: int = Field(default=3600, ge=1, le=86400, description="TTL in seconds (1s - 24h)")


@router.post("/context/{agent_id}")
async def set_context(
    agent_id: str,
    request: ContextSetRequest,
) -> dict[str, Any]:
    """
    Set context for agent.

    Args:
        agent_id: Agent identifier
        request: Context data

    Returns:
        Status and expiration info
    """
    # Get Redis client from app state (injected in main.py)
    import main as memory_main

    redis_client = memory_main.redis_client

    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis client not available",
        )

    result = await redis_client.set_context(
        agent_id=agent_id,
        key=request.key,
        value=request.value,
        ttl=request.ttl,
    )

    return result


@router.get("/context/{agent_id}/{key}")
async def get_context(
    agent_id: str,
    key: str,
) -> dict[str, Any]:
    """
    Get context for agent.

    Args:
        agent_id: Agent identifier
        key: Context key

    Returns:
        Context data with TTL

    Raises:
        404: If key not found or expired
    """
    import main as memory_main

    redis_client = memory_main.redis_client

    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis client not available",
        )

    result = await redis_client.get_context(agent_id=agent_id, key=key)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found or expired",
        )

    return result


@router.delete("/context/{agent_id}/{key}")
async def delete_context(
    agent_id: str,
    key: str,
) -> dict[str, str]:
    """
    Delete context for agent.

    Args:
        agent_id: Agent identifier
        key: Context key

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

    result = await redis_client.delete_context(agent_id=agent_id, key=key)
    return result
