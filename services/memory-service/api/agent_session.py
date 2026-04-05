"""Per-user per-agent session (last chat_id, bot_id) in Redis."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter()


class AgentSessionPatch(BaseModel):
    chat_id: str = Field(..., min_length=1)
    bot_id: str | None = Field(default=None, description="Logical bot id (e.g. main | alt)")
    extra: dict[str, Any] = Field(default_factory=dict)


def _redis():
    import main as memory_main

    r = memory_main.redis_client
    if not r:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis client not available",
        )
    return r


@router.get("/agent-session/{user_id}/{agent_id}")
async def get_agent_session(user_id: str, agent_id: str) -> dict[str, Any]:
    redis_client = _redis()
    data = await redis_client.get_agent_session(user_id, agent_id)
    if not data:
        raise HTTPException(status_code=404, detail="No session stored for this agent")
    return data


@router.patch("/agent-session/{user_id}/{agent_id}")
async def patch_agent_session(
    user_id: str,
    agent_id: str,
    body: AgentSessionPatch,
) -> dict[str, Any]:
    redis_client = _redis()
    return await redis_client.set_agent_session(
        user_id=user_id,
        agent_id=agent_id,
        chat_id=body.chat_id,
        bot_id=body.bot_id,
        extra=body.extra or None,
    )
