"""
Redis client for fast context, chat history and session storage.

Provides methods for:
- Context storage (with TTL)
- Multi-chat management (Sorted Set history, lazy cleanup)
- Chat model preferences
- Token budget tracking
- Alert flags
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import redis.asyncio as aioredis

from shared.config import get_settings
from shared.exceptions import MemoryRetrievalError, MemoryStorageError

settings = get_settings()
logger = logging.getLogger("memory-service.redis")

CHAT_TTL_SECONDS = 7 * 24 * 3600  # 7 days


class RedisClient:
    """
    Async Redis client for context, chat history and session management.
    """

    def __init__(self):
        self.client: aioredis.Redis | None = None
        self._url = settings.redis_url

    async def connect(self) -> None:
        """Connect to Redis"""
        try:
            self.client = await aioredis.from_url(
                self._url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=settings.connection_pool_size,
            )
            await self.client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise MemoryStorageError(f"Redis connection failed: {e}")

    async def close(self) -> None:
        """Close Redis connection"""
        if self.client:
            await self.client.aclose()
            logger.info("Redis connection closed")

    async def ping(self) -> bool:
        """Check Redis connection"""
        if not self.client:
            return False
        try:
            await self.client.ping()
            return True
        except Exception:
            return False

    # =========================================================================
    # Context Methods (Fast Memory with TTL)
    # =========================================================================

    def _context_key(self, agent_id: str, key: str) -> str:
        return f"context:{agent_id}:{key}"

    async def set_context(
        self,
        agent_id: str,
        key: str,
        value: dict[str, Any],
        ttl: int = 3600,
    ) -> dict[str, Any]:
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        try:
            redis_key = self._context_key(agent_id, key)
            value_json = json.dumps(value)
            await self.client.setex(redis_key, ttl, value_json)
            expires_at = datetime.now(timezone.utc).timestamp() + ttl
            logger.debug(f"Set context: {redis_key} (TTL: {ttl}s)")
            return {
                "status": "ok",
                "key": key,
                "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to set context: {e}")
            raise MemoryStorageError(f"Failed to store context: {e}")

    async def get_context(self, agent_id: str, key: str) -> dict[str, Any] | None:
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")

        try:
            redis_key = self._context_key(agent_id, key)
            value_json = await self.client.get(redis_key)
            if not value_json:
                return None
            ttl_remaining = await self.client.ttl(redis_key)
            value = json.loads(value_json)
            return {
                "key": key,
                "value": value,
                "ttl_remaining": ttl_remaining if ttl_remaining > 0 else 0,
            }
        except json.JSONDecodeError as e:
            raise MemoryRetrievalError(f"Invalid JSON in context: {e}")
        except Exception as e:
            raise MemoryRetrievalError(f"Failed to retrieve context: {e}")

    async def delete_context(self, agent_id: str, key: str) -> dict[str, str]:
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        try:
            redis_key = self._context_key(agent_id, key)
            await self.client.delete(redis_key)
            return {"status": "deleted"}
        except Exception as e:
            raise MemoryStorageError(f"Failed to delete context: {e}")

    # =========================================================================
    # Multi-Chat Methods
    # Keys:
    #   chats:{user_id}                  Hash  { chat_id → name }
    #   active_chat:{user_id}            String  chat_id
    #   chat_meta:{user_id}:{chat_id}    Hash  { name, model_id, agent_id, created_at, last_used_at }  TTL=7d
    #   history:{user_id}:{chat_id}      Sorted Set  score=unix_ts, value=json  TTL=7d
    # =========================================================================

    def _chats_key(self, user_id: str) -> str:
        return f"chats:{user_id}"

    def _active_chat_key(self, user_id: str) -> str:
        return f"active_chat:{user_id}"

    def _chat_meta_key(self, user_id: str, chat_id: str) -> str:
        return f"chat_meta:{user_id}:{chat_id}"

    def _history_key(self, user_id: str, chat_id: str) -> str:
        return f"history:{user_id}:{chat_id}"

    async def create_chat(
        self,
        user_id: str,
        chat_name: str,
        model_id: str | None = None,
        agent_id: str | None = None,
    ) -> str:
        """Create a new chat and return its chat_id."""
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        chat_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        pipe = self.client.pipeline()
        # Register chat in user's chat list
        pipe.hset(self._chats_key(user_id), chat_id, chat_name)
        # Store chat metadata
        meta = {
            "name": chat_name,
            "model_id": model_id or "",
            "agent_id": agent_id or "orchestrator",
            "created_at": now,
            "last_used_at": now,
        }
        pipe.hset(self._chat_meta_key(user_id, chat_id), mapping=meta)
        pipe.expire(self._chat_meta_key(user_id, chat_id), CHAT_TTL_SECONDS)
        await pipe.execute()

        logger.info(
            f"Created chat {chat_id} for user {user_id}: '{chat_name}' agent={agent_id or 'orchestrator'}"
        )
        return chat_id

    async def get_chats(self, user_id: str) -> list[dict[str, Any]]:
        """
        Return list of active chats for a user.
        Performs lazy cleanup: removes chat entries whose metadata has expired.
        """
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")

        all_chats = await self.client.hgetall(self._chats_key(user_id))
        if not all_chats:
            return []

        live_chats: list[dict[str, Any]] = []
        dead_ids: list[str] = []

        for chat_id, name in all_chats.items():
            meta = await self.client.hgetall(self._chat_meta_key(user_id, chat_id))
            if meta:
                live_chats.append(
                    {
                        "chat_id": chat_id,
                        "name": meta.get("name", name),
                        "model_id": meta.get("model_id", ""),
                        "agent_id": meta.get("agent_id", "orchestrator"),
                        "debug": meta.get("debug", "false") == "true",
                        "mode": meta.get("mode", "ask"),
                        "created_at": meta.get("created_at", ""),
                        "last_used_at": meta.get("last_used_at", ""),
                    }
                )
            else:
                dead_ids.append(chat_id)

        if dead_ids:
            await self.client.hdel(self._chats_key(user_id), *dead_ids)
            logger.debug(f"Lazy cleanup: removed {len(dead_ids)} dead chats for user {user_id}")

        live_chats.sort(key=lambda c: c.get("last_used_at", ""), reverse=True)
        return live_chats

    async def get_active_chat(self, user_id: str) -> str | None:
        """Return active chat_id for user, or None if not set."""
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")
        return await self.client.get(self._active_chat_key(user_id))

    async def set_active_chat(self, user_id: str, chat_id: str) -> None:
        """Set active chat for user and update last_used_at."""
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        await self.client.set(self._active_chat_key(user_id), chat_id)
        await self._touch_chat(user_id, chat_id)

    async def get_or_create_default_chat(self, user_id: str) -> str:
        """
        Return active chat_id. If user has no active chat, create a default one
        and set it as active.
        """
        chat_id = await self.get_active_chat(user_id)
        if chat_id:
            meta = await self.client.hgetall(self._chat_meta_key(user_id, chat_id))
            if meta:
                return chat_id

        chat_id = await self.create_chat(user_id, "Новый чат")
        await self.client.set(self._active_chat_key(user_id), chat_id)
        return chat_id

    async def rename_chat(self, user_id: str, chat_id: str, name: str) -> None:
        """Rename a chat."""
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        pipe = self.client.pipeline()
        pipe.hset(self._chats_key(user_id), chat_id, name)
        pipe.hset(self._chat_meta_key(user_id, chat_id), "name", name)
        pipe.expire(self._chat_meta_key(user_id, chat_id), CHAT_TTL_SECONDS)
        await pipe.execute()
        logger.info(f"Renamed chat {chat_id} for user {user_id}: '{name}'")

    async def delete_chat(self, user_id: str, chat_id: str) -> None:
        """Delete a chat and all its data."""
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        pipe = self.client.pipeline()
        pipe.hdel(self._chats_key(user_id), chat_id)
        pipe.delete(self._chat_meta_key(user_id, chat_id))
        pipe.delete(self._history_key(user_id, chat_id))
        await pipe.execute()

        active = await self.client.get(self._active_chat_key(user_id))
        if active == chat_id:
            await self.client.delete(self._active_chat_key(user_id))

        logger.info(f"Deleted chat {chat_id} for user {user_id}")

    async def get_chat_model(self, user_id: str, chat_id: str) -> str | None:
        """Return model_id assigned to the chat, or None."""
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")
        model_id = await self.client.hget(self._chat_meta_key(user_id, chat_id), "model_id")
        return model_id if model_id else None

    async def set_chat_model(self, user_id: str, chat_id: str, model_id: str) -> None:
        """Assign a model to a specific chat."""
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        pipe = self.client.pipeline()
        pipe.hset(self._chat_meta_key(user_id, chat_id), "model_id", model_id)
        pipe.expire(self._chat_meta_key(user_id, chat_id), CHAT_TTL_SECONDS)
        await pipe.execute()
        logger.info(f"Set model {model_id} for chat {chat_id} / user {user_id}")

    async def get_chat_agent(self, user_id: str, chat_id: str) -> str:
        """Return agent_id assigned to the chat (defaults to 'orchestrator')."""
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")
        agent_id = await self.client.hget(self._chat_meta_key(user_id, chat_id), "agent_id")
        return agent_id if agent_id else "orchestrator"

    async def set_chat_agent(self, user_id: str, chat_id: str, agent_id: str) -> None:
        """Assign an agent to a specific chat."""
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        pipe = self.client.pipeline()
        pipe.hset(self._chat_meta_key(user_id, chat_id), "agent_id", agent_id)
        pipe.expire(self._chat_meta_key(user_id, chat_id), CHAT_TTL_SECONDS)
        await pipe.execute()
        logger.info(f"Set agent {agent_id} for chat {chat_id} / user {user_id}")

    async def get_chat_settings(self, user_id: str, chat_id: str) -> dict[str, Any]:
        """Return per-chat settings: debug mode and agent/ask mode."""
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")
        meta = await self.client.hgetall(self._chat_meta_key(user_id, chat_id))
        return {
            "debug": meta.get("debug", "false") == "true",
            "mode": meta.get("mode", "ask"),
        }

    async def set_chat_settings(
        self,
        user_id: str,
        chat_id: str,
        debug: bool | None = None,
        mode: str | None = None,
    ) -> None:
        """Update per-chat settings (debug and/or mode)."""
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        updates: dict[str, str] = {}
        if debug is not None:
            updates["debug"] = "true" if debug else "false"
        if mode is not None:
            updates["mode"] = mode
        if not updates:
            return
        pipe = self.client.pipeline()
        pipe.hset(self._chat_meta_key(user_id, chat_id), mapping=updates)
        pipe.expire(self._chat_meta_key(user_id, chat_id), CHAT_TTL_SECONDS)
        await pipe.execute()
        logger.info(f"Updated settings {updates} for chat {chat_id} / user {user_id}")

    async def add_to_chat_history(
        self,
        user_id: str,
        chat_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Add a message to chat history (Sorted Set, score = unix timestamp).
        Resets TTL on both history and chat_meta keys.
        """
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        ts = datetime.now(timezone.utc).timestamp()
        message = {
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        }
        message_json = json.dumps(message, ensure_ascii=False)
        history_key = self._history_key(user_id, chat_id)

        pipe = self.client.pipeline()
        pipe.zadd(history_key, {message_json: ts})
        pipe.expire(history_key, CHAT_TTL_SECONDS)
        # Update last_used_at and reset TTL on meta
        pipe.hset(
            self._chat_meta_key(user_id, chat_id),
            "last_used_at",
            datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        )
        pipe.expire(self._chat_meta_key(user_id, chat_id), CHAT_TTL_SECONDS)
        await pipe.execute()

    async def get_chat_history(
        self,
        user_id: str,
        chat_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Return last `limit` messages from chat history, chronological order.
        """
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")

        history_key = self._history_key(user_id, chat_id)
        # Get last N items by score (most recent)
        raw = await self.client.zrange(history_key, -limit, -1)
        messages = []
        for item in raw:
            try:
                messages.append(json.loads(item))
            except json.JSONDecodeError:
                logger.warning("Failed to decode history message")
        return messages

    async def clear_chat_history(self, user_id: str, chat_id: str) -> None:
        """Delete all messages from a chat's history."""
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        await self.client.delete(self._history_key(user_id, chat_id))
        logger.info(f"Cleared history for chat {chat_id} / user {user_id}")

    async def _touch_chat(self, user_id: str, chat_id: str) -> None:
        """Reset TTL and update last_used_at."""
        if not self.client:
            return
        now = datetime.now(timezone.utc).isoformat()
        pipe = self.client.pipeline()
        pipe.hset(self._chat_meta_key(user_id, chat_id), "last_used_at", now)
        pipe.expire(self._chat_meta_key(user_id, chat_id), CHAT_TTL_SECONDS)
        pipe.expire(self._history_key(user_id, chat_id), CHAT_TTL_SECONDS)
        await pipe.execute()

    # =========================================================================
    # Legacy History Methods (kept for backward compatibility)
    # =========================================================================

    def _history_key_legacy(self, agent_id: str) -> str:
        return f"history:{agent_id}"

    async def add_to_history(
        self,
        agent_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        redis_key = self._history_key_legacy(agent_id)
        message = {
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.client.rpush(redis_key, json.dumps(message))
        await self.client.ltrim(redis_key, -50, -1)
        length = await self.client.llen(redis_key)
        return {"status": "ok", "history_length": length}

    async def get_history(self, agent_id: str, limit: int = 50) -> dict[str, Any]:
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")

        redis_key = self._history_key_legacy(agent_id)
        messages_json = await self.client.lrange(redis_key, -limit, -1)
        messages = []
        for msg_json in messages_json:
            try:
                messages.append(json.loads(msg_json))
            except json.JSONDecodeError:
                continue
        total = await self.client.llen(redis_key)
        return {"messages": messages, "total": total}

    async def clear_history(self, agent_id: str) -> dict[str, str]:
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        redis_key = self._history_key_legacy(agent_id)
        await self.client.delete(redis_key)
        return {"status": "cleared"}

    # =========================================================================
    # Token Budget Methods
    # =========================================================================

    def _token_key(self, agent_id: str, period: str) -> str:
        return f"tokens:{agent_id}:{period}"

    async def increment_tokens(
        self,
        agent_id: str,
        tokens: int,
        cost: float,
    ) -> dict[str, Any]:
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        now = datetime.now(timezone.utc)
        today_key = self._token_key(agent_id, now.strftime("%Y-%m-%d"))
        hour_key = self._token_key(agent_id, now.strftime("%Y-%m-%d-%H"))

        pipe = self.client.pipeline()
        pipe.hincrby(today_key, "tokens", tokens)
        pipe.hincrbyfloat(today_key, "cost", cost)
        pipe.expire(today_key, 86400 * 7)
        pipe.hincrby(hour_key, "tokens", tokens)
        pipe.hincrbyfloat(hour_key, "cost", cost)
        pipe.expire(hour_key, 3600 * 24)
        results = await pipe.execute()

        return {
            "tokens_today": results[0],
            "cost_today": results[1],
            "tokens_hour": results[3],
        }

    async def get_token_usage(self, agent_id: str) -> dict[str, Any]:
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")

        now = datetime.now(timezone.utc)
        today_key = self._token_key(agent_id, now.strftime("%Y-%m-%d"))
        hour_key = self._token_key(agent_id, now.strftime("%Y-%m-%d-%H"))
        today_data = await self.client.hgetall(today_key)
        hour_data = await self.client.hgetall(hour_key)
        return {
            "tokens_today": int(today_data.get("tokens", 0)),
            "cost_today": float(today_data.get("cost", 0)),
            "tokens_hour": int(hour_data.get("tokens", 0)),
        }

    # =========================================================================
    # Alert Flags
    # =========================================================================

    def _alert_key(self, agent_id: str, alert_type: str) -> str:
        return f"alert:{agent_id}:{alert_type}"

    async def set_alert_flag(self, agent_id: str, alert_type: str, ttl: int = 3600) -> None:
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        await self.client.setex(self._alert_key(agent_id, alert_type), ttl, "1")

    async def check_alert_flag(self, agent_id: str, alert_type: str) -> bool:
        if not self.client:
            return False
        try:
            exists = await self.client.exists(self._alert_key(agent_id, alert_type))
            return bool(exists)
        except Exception:
            return False
