"""Per-user settings not tied to a chat (e.g. vision tier for /vision)."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from shared.image_gen_models import validate_image_gen_model_id
from shared.vision_models import validate_vision_model_id

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


class VisionModelBody(BaseModel):
    model_id: str = Field(..., description="openrouter/... id from config vision_models")


class ImageGenModelBody(BaseModel):
    model_id: str = Field(..., description="openrouter/... id from config image_generation_models")


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


@router.get("/users/{user_id}/vision-model")
async def get_vision_model(user_id: str) -> dict[str, Any]:
    """Selected vision model id (openrouter/...), or null = use yaml default."""
    redis_client = _get_redis()
    mid = await redis_client.get_vision_model_id(user_id)
    return {"user_id": user_id, "model_id": mid}


@router.put("/users/{user_id}/vision-model")
async def put_vision_model(user_id: str, body: VisionModelBody) -> dict[str, Any]:
    mid = body.model_id.strip()
    if not validate_vision_model_id(mid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="model_id is not in vision_models allowlist (config/providers.yaml)",
        )
    redis_client = _get_redis()
    await redis_client.set_vision_model_id(user_id, mid)
    return {"user_id": user_id, "model_id": mid, "status": "ok"}


@router.get("/users/{user_id}/image-generation-tier")
async def get_image_generation_tier(user_id: str) -> dict[str, Any]:
    """Current image generation model tier (or null = use yaml default_tier)."""
    redis_client = _get_redis()
    tier = await redis_client.get_image_gen_tier(user_id)
    return {"user_id": user_id, "tier": tier}


@router.put("/users/{user_id}/image-generation-tier")
async def put_image_generation_tier(user_id: str, body: VisionTierBody) -> dict[str, Any]:
    t = body.tier.strip().lower()
    if t not in _VALID_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"tier must be one of: {', '.join(sorted(_VALID_TIERS))}",
        )
    redis_client = _get_redis()
    await redis_client.set_image_gen_tier(user_id, t)
    return {"user_id": user_id, "tier": t, "status": "ok"}


@router.get("/users/{user_id}/image-generation-model")
async def get_image_generation_model(user_id: str) -> dict[str, Any]:
    """Selected image generation model id, or null."""
    redis_client = _get_redis()
    mid = await redis_client.get_image_gen_model_id(user_id)
    return {"user_id": user_id, "model_id": mid}


@router.put("/users/{user_id}/image-generation-model")
async def put_image_generation_model(user_id: str, body: ImageGenModelBody) -> dict[str, Any]:
    mid = body.model_id.strip()
    if not validate_image_gen_model_id(mid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="model_id is not in image_generation_models allowlist (config/providers.yaml)",
        )
    redis_client = _get_redis()
    await redis_client.set_image_gen_model_id(user_id, mid)
    return {"user_id": user_id, "model_id": mid, "status": "ok"}
