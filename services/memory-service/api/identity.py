"""Canonical user identity — map Telegram / MAX external ids to stable UUIDs."""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from shared.config import get_settings

router = APIRouter()


def _get_redis():
    import main as memory_main

    client = memory_main.redis_client
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis client not available",
        )
    return client


@router.get("/identity/resolve")
async def resolve_identity(
    provider: str = Query(..., description="telegram | max"),
    external_id: str = Query(..., description="Platform-specific user id (decimal string)"),
) -> dict:
    """
    Return canonical_user_id for this provider + external id.

    On first request, allocates a UUID, stores mapping, and renames legacy
    Redis keys (e.g. chats:12345 or chats:max:9) to the new namespace when present.
    """
    redis_client = _get_redis()
    try:
        canonical, created = await redis_client.resolve_canonical_user(provider, external_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return {"canonical_user_id": canonical, "created": created}


class IdentityLinkRequest(BaseModel):
    """Attach a provider external id to an existing canonical user id (merge accounts)."""

    canonical_user_id: str = Field(
        ...,
        description="Target UUID — e.g. from GET /identity/resolve for your Telegram account",
    )
    provider: str = Field(..., description="telegram | max")
    external_id: str = Field(..., description="User id on that platform (decimal string)")


@router.post("/identity/link")
async def link_identity(
    body: IdentityLinkRequest,
    x_balbes_identity_link_secret: str | None = Header(
        None,
        alias="X-Balbes-Identity-Link-Secret",
    ),
) -> dict[str, Any]:
    """
    Point `identity:link:{provider}:{external_id}` at `canonical_user_id`.

    Use this to merge MAX and Telegram into one memory namespace: choose one
    canonical UUID (typically from Telegram `resolve`), then link the other channel.

    When `IDENTITY_LINK_SECRET` is set in the environment, requests must send the
    same value in the `X-Balbes-Identity-Link-Secret` header.
    """
    settings = get_settings()
    secret = settings.identity_link_secret
    if secret and (not x_balbes_identity_link_secret or x_balbes_identity_link_secret != secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-Balbes-Identity-Link-Secret",
        )

    redis_client = _get_redis()
    try:
        return await redis_client.link_identity_to_canonical(
            body.provider, body.external_id, body.canonical_user_id
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
