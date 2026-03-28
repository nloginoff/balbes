"""
History API endpoints — multi-chat conversation history in Redis.

Supports both:
- New chat-scoped endpoints: /history/{user_id}/{chat_id}
- Legacy agent-scoped endpoints: /history/{agent_id}  (backward compat)
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

router = APIRouter()


class HistoryAddRequest(BaseModel):
    role: str = Field(..., description="Message role: user | assistant | system")
    content: str = Field(..., description="Message content")
    metadata: dict[str, Any] = Field(default_factory=dict)


def _get_redis():
    import main as memory_main

    client = memory_main.redis_client
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis client not available",
        )
    return client


# ---------------------------------------------------------------------------
# Chat-scoped endpoints  /history/{user_id}/{chat_id}
# ---------------------------------------------------------------------------


@router.post("/history/{user_id}/{chat_id}")
async def chat_add_message(
    user_id: str,
    chat_id: str,
    request: HistoryAddRequest,
) -> dict[str, Any]:
    """Add a message to a specific chat's history."""
    redis_client = _get_redis()
    await redis_client.add_to_chat_history(
        user_id=user_id,
        chat_id=chat_id,
        role=request.role,
        content=request.content,
        metadata=request.metadata,
    )
    return {"status": "ok"}


@router.get("/history/{user_id}/{chat_id}")
async def chat_get_history(
    user_id: str,
    chat_id: str,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Return chat history (last N messages, chronological order)."""
    redis_client = _get_redis()
    messages = await redis_client.get_chat_history(
        user_id=user_id,
        chat_id=chat_id,
        limit=limit,
    )
    return {"messages": messages, "total": len(messages)}


@router.delete("/history/{user_id}/{chat_id}")
async def chat_clear_history(user_id: str, chat_id: str) -> dict[str, str]:
    """Clear all messages from a specific chat."""
    redis_client = _get_redis()
    await redis_client.clear_chat_history(user_id=user_id, chat_id=chat_id)
    return {"status": "cleared"}


# ---------------------------------------------------------------------------
# Chat management endpoints  /chats/{user_id}
# ---------------------------------------------------------------------------


class CreateChatRequest(BaseModel):
    name: str = Field(default="Новый чат")
    model_id: str | None = Field(default=None)


@router.post("/chats/{user_id}")
async def create_chat(user_id: str, request: CreateChatRequest) -> dict[str, Any]:
    """Create a new chat for a user."""
    redis_client = _get_redis()
    chat_id = await redis_client.create_chat(
        user_id=user_id,
        chat_name=request.name,
        model_id=request.model_id,
    )
    return {"chat_id": chat_id, "name": request.name}


@router.get("/chats/{user_id}")
async def list_chats(user_id: str) -> dict[str, Any]:
    """List all active chats for a user (with lazy cleanup)."""
    redis_client = _get_redis()
    chats = await redis_client.get_chats(user_id=user_id)
    return {"chats": chats, "total": len(chats)}


@router.get("/chats/{user_id}/active")
async def get_active_chat(user_id: str) -> dict[str, Any]:
    """Return active chat_id for a user, creating a default one if needed."""
    redis_client = _get_redis()
    chat_id = await redis_client.get_or_create_default_chat(user_id=user_id)
    return {"chat_id": chat_id}


@router.put("/chats/{user_id}/active")
async def set_active_chat(user_id: str, chat_id: str) -> dict[str, str]:
    """Switch active chat for a user."""
    redis_client = _get_redis()
    await redis_client.set_active_chat(user_id=user_id, chat_id=chat_id)
    return {"status": "ok", "chat_id": chat_id}


class RenameChatRequest(BaseModel):
    name: str


@router.put("/chats/{user_id}/{chat_id}/name")
async def rename_chat(
    user_id: str,
    chat_id: str,
    request: RenameChatRequest,
) -> dict[str, str]:
    """Rename a chat."""
    redis_client = _get_redis()
    await redis_client.rename_chat(user_id=user_id, chat_id=chat_id, name=request.name)
    return {"status": "ok", "name": request.name}


@router.delete("/chats/{user_id}/{chat_id}")
async def delete_chat(user_id: str, chat_id: str) -> dict[str, str]:
    """Delete a chat and all its messages."""
    redis_client = _get_redis()
    await redis_client.delete_chat(user_id=user_id, chat_id=chat_id)
    return {"status": "deleted"}


@router.get("/chats/{user_id}/{chat_id}/model")
async def get_chat_model(user_id: str, chat_id: str) -> dict[str, Any]:
    """Get the model assigned to a specific chat."""
    redis_client = _get_redis()
    model_id = await redis_client.get_chat_model(user_id=user_id, chat_id=chat_id)
    return {"model_id": model_id}


class SetModelRequest(BaseModel):
    model_id: str


@router.put("/chats/{user_id}/{chat_id}/model")
async def set_chat_model(
    user_id: str,
    chat_id: str,
    request: SetModelRequest,
) -> dict[str, str]:
    """Assign a model to a specific chat."""
    redis_client = _get_redis()
    await redis_client.set_chat_model(
        user_id=user_id,
        chat_id=chat_id,
        model_id=request.model_id,
    )
    return {"status": "ok", "model_id": request.model_id}


# ---------------------------------------------------------------------------
# Legacy endpoints  /history/{agent_id}
# ---------------------------------------------------------------------------


@router.post("/history/{agent_id}")
async def add_to_history(agent_id: str, request: HistoryAddRequest) -> dict[str, Any]:
    """Legacy: add message to agent history."""
    redis_client = _get_redis()
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
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """Legacy: get agent history."""
    redis_client = _get_redis()
    return await redis_client.get_history(agent_id=agent_id, limit=limit)


@router.delete("/history/{agent_id}")
async def clear_history(agent_id: str) -> dict[str, str]:
    """Legacy: clear agent history."""
    redis_client = _get_redis()
    return await redis_client.clear_history(agent_id=agent_id)
