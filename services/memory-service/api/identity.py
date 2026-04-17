"""Canonical user identity — map Telegram / MAX external ids to stable UUIDs."""

from fastapi import APIRouter, HTTPException, Query, status

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
