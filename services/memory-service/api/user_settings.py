"""Per-user settings not tied to a chat (e.g. vision tier for /vision)."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter()

_VALID_TIERS = frozenset({"cheap", "medium", "premium"})


def _get_redis():
    import main as memory_main

    client = memory_main.redis_client
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis client not available",
        )
    return client


class VisionTierBody(BaseModel):
    tier: str = Field(..., description="cheap | medium | premium")


@router.get("/users/{user_id}/vision-tier")
async def get_vision_tier(user_id: str) -> dict[str, Any]:
    """Return current vision tier for canonical user (or null = use yaml default)."""
    redis_client = _get_redis()
    tier = await redis_client.get_vision_tier(user_id)
    return {"user_id": user_id, "tier": tier}


@router.put("/users/{user_id}/vision-tier")
async def put_vision_tier(user_id: str, body: VisionTierBody) -> dict[str, Any]:
    t = body.tier.strip().lower()
    if t not in _VALID_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"tier must be one of: {', '.join(sorted(_VALID_TIERS))}",
        )
    redis_client = _get_redis()
    await redis_client.set_vision_tier(user_id, t)
    return {"user_id": user_id, "tier": t, "status": "ok"}
