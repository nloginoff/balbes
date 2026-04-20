"""
Redis client for fast context, chat history and session storage.

Provides methods for:
- Context storage (with TTL)
- Multi-chat management (Sorted Set history, lazy cleanup)
- Chat model preferences
- Token budget tracking
- Alert flags
"""

import asyncio
import json
import logging
import secrets
import string
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import redis.asyncio as aioredis

from shared.config import get_settings
from shared.exceptions import MemoryRetrievalError, MemoryStorageError

settings = get_settings()
logger = logging.getLogger("memory-service.redis")

CHAT_TTL_SECONDS = 7 * 24 * 3600  # 7 days
PAIRING_CODE_TTL_SECONDS = 600  # 10 minutes
PAIRING_CODE_LENGTH = 8


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
            "agent_id": agent_id or "balbes",
            "created_at": now,
            "last_used_at": now,
        }
        pipe.hset(self._chat_meta_key(user_id, chat_id), mapping=meta)
        pipe.expire(self._chat_meta_key(user_id, chat_id), CHAT_TTL_SECONDS)
        await pipe.execute()

        logger.info(
            f"Created chat {chat_id} for user {user_id}: '{chat_name}' agent={agent_id or 'balbes'}"
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
                        "agent_id": meta.get("agent_id", "balbes"),
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
        """Return agent_id assigned to the chat (defaults to 'balbes')."""
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")
        agent_id = await self.client.hget(self._chat_meta_key(user_id, chat_id), "agent_id")
        return agent_id if agent_id else "balbes"

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
    # Canonical user id (cross-channel identity)
    # identity:link:{provider}:{external_id} → UUID string
    # Legacy Redis user keys: telegram = decimal string; MAX = "max:{id}"
    # =========================================================================

    def _identity_link_key(self, provider: str, external_id: str) -> str:
        return f"identity:link:{provider}:{external_id}"

    def _identity_lock_key(self, provider: str, external_id: str) -> str:
        return f"identity:lock:{provider}:{external_id}"

    def _legacy_user_id(self, provider: str, external_id: str) -> str:
        p = provider.lower()
        if p == "telegram":
            return external_id.strip()
        if p == "max":
            return f"max:{external_id.strip()}"
        raise ValueError(f"unsupported identity provider: {provider}")

    def _identity_peers_key(self, canonical: str) -> str:
        return f"identity:peers:{canonical.strip()}"

    def _channel_presence_key(self, canonical: str) -> str:
        return f"channel_presence:{canonical.strip()}"

    async def _ensure_identity_peer(self, canonical: str, provider: str, external_id: str) -> None:
        """SADD identity:peers:{canonical} → member telegram:id | max:id."""
        if not self.client:
            return
        p = provider.lower().strip()
        ext = external_id.strip()
        if p not in ("telegram", "max") or not ext:
            return
        try:
            UUID(canonical.strip())
        except ValueError:
            return
        await self.client.sadd(self._identity_peers_key(canonical), f"{p}:{ext}")

    async def _backfill_identity_peers(self, canonical: str) -> None:
        """If peers set is empty, scan identity:link:* pointing at this canonical id."""
        if not self.client:
            return
        cnorm = canonical.strip()
        for pattern in ("identity:link:telegram:*", "identity:link:max:*"):
            cur = 0
            while True:
                cur, keys = await self.client.scan(cursor=cur, match=pattern, count=200)
                for k in keys or []:
                    val = await self.client.get(k)
                    if val != cnorm:
                        continue
                    suf = k[len("identity:link:") :] if k.startswith("identity:link:") else ""
                    if not suf:
                        continue
                    prov, _, rest = suf.partition(":")
                    if prov == "telegram" and rest:
                        await self._ensure_identity_peer(cnorm, "telegram", rest)
                    elif prov == "max" and rest:
                        await self._ensure_identity_peer(cnorm, "max", rest)
                if cur == 0:
                    break

    async def list_identity_peers(self, canonical_user_id: str) -> list[dict[str, str]]:
        """Return [{'provider': 'telegram'|'max', 'external_id': '...'}, ...]."""
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        try:
            UUID(canonical_user_id.strip())
        except ValueError as e:
            raise MemoryStorageError("canonical_user_id must be a UUID string") from e
        key = self._identity_peers_key(canonical_user_id)
        members = await self.client.smembers(key)
        if not members:
            await self._backfill_identity_peers(canonical_user_id)
            members = await self.client.smembers(key)
        out: list[dict[str, str]] = []
        for raw in members or []:
            m = raw if isinstance(raw, str) else str(raw)
            if ":" not in m:
                continue
            prov, eid = m.split(":", 1)
            if prov in ("telegram", "max") and eid:
                out.append({"provider": prov, "external_id": eid})
        return out

    async def touch_channel_presence(self, canonical_user_id: str, channel: str) -> None:
        """Record last inbound activity for a messenger (telegram | max)."""
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        try:
            UUID(canonical_user_id.strip())
        except ValueError as e:
            raise MemoryStorageError("canonical_user_id must be a UUID string") from e
        ch = channel.lower().strip()
        if ch not in ("telegram", "max"):
            raise MemoryStorageError("channel must be telegram or max")
        now = str(int(time.time()))
        await self.client.hset(self._channel_presence_key(canonical_user_id), ch, now)

    async def is_channel_presence_active(
        self, canonical_user_id: str, channel: str, ttl_seconds: int
    ) -> bool:
        if not self.client:
            return False
        try:
            UUID(canonical_user_id.strip())
        except ValueError:
            return False
        ch = channel.lower().strip()
        if ch not in ("telegram", "max"):
            return False
        raw = await self.client.hget(self._channel_presence_key(canonical_user_id), ch)
        if not raw:
            return False
        try:
            ts = int(raw if isinstance(raw, str) else str(raw))
        except (TypeError, ValueError):
            return False
        return (int(time.time()) - ts) <= int(ttl_seconds)

    async def _rename_if_dest_missing(self, src: str, dest: str) -> None:
        if not self.client:
            return
        if await self.client.exists(dest):
            return
        if not await self.client.exists(src):
            return
        await self.client.rename(src, dest)

    async def _migrate_user_redis_keys(self, legacy: str, canonical: str) -> None:
        """Move chat/history/agent_session keys from legacy user id to canonical."""
        if not self.client or legacy == canonical:
            return
        if await self.client.exists(self._chats_key(canonical)):
            return

        has_legacy = await self.client.exists(self._chats_key(legacy)) or await self.client.exists(
            self._active_chat_key(legacy)
        )
        if not has_legacy:
            # Still scan agent_session:{legacy}:*
            cursor = 0
            while True:
                cursor, keys = await self.client.scan(
                    cursor=cursor, match=f"agent_session:{legacy}:*", count=50
                )
                if keys:
                    has_legacy = True
                    break
                if cursor == 0:
                    break

        if not has_legacy:
            return

        await self._rename_if_dest_missing(self._chats_key(legacy), self._chats_key(canonical))
        await self._rename_if_dest_missing(
            self._active_chat_key(legacy), self._active_chat_key(canonical)
        )

        chat_ids = list(await self.client.hkeys(self._chats_key(canonical)))
        active_only = await self.client.get(self._active_chat_key(canonical))
        if active_only and active_only not in chat_ids:
            chat_ids.append(active_only)

        for cid in chat_ids or []:
            await self._rename_if_dest_missing(
                self._chat_meta_key(legacy, cid), self._chat_meta_key(canonical, cid)
            )
            await self._rename_if_dest_missing(
                self._history_key(legacy, cid), self._history_key(canonical, cid)
            )

        cursor = 0
        while True:
            cursor, keys = await self.client.scan(
                cursor=cursor, match=f"agent_session:{legacy}:*", count=50
            )
            for old_k in keys or []:
                suffix = old_k.split(f"agent_session:{legacy}:", 1)[-1]
                new_k = f"agent_session:{canonical}:{suffix}"
                await self._rename_if_dest_missing(old_k, new_k)
            if cursor == 0:
                break

        logger.info("Migrated Redis user keys %s → %s", legacy, canonical)

    async def resolve_canonical_user(self, provider: str, external_id: str) -> tuple[str, bool]:
        """
        Return (canonical_user_id, created).

        Creates a new UUID on first sight, persists mapping, and renames legacy
        per-user keys when present (telegram decimal id, max:... id).
        """
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        p = provider.lower().strip()
        if p not in ("telegram", "max"):
            raise MemoryStorageError(f"unsupported provider: {provider}")
        ext = external_id.strip()
        if not ext:
            raise MemoryStorageError("external_id is required")

        link_key = self._identity_link_key(p, ext)
        existing = await self.client.get(link_key)
        if existing:
            await self._ensure_identity_peer(existing, p, ext)
            return existing, False

        legacy = self._legacy_user_id(p, ext)
        lock_key = self._identity_lock_key(p, ext)

        for _ in range(50):
            if await self.client.set(lock_key, "1", nx=True, ex=30):
                try:
                    existing2 = await self.client.get(link_key)
                    if existing2:
                        return existing2, False
                    canonical = str(uuid4())
                    await self._migrate_user_redis_keys(legacy, canonical)
                    await self.client.set(link_key, canonical)
                    await self._ensure_identity_peer(canonical, p, ext)
                    return canonical, True
                finally:
                    await self.client.delete(lock_key)
            await asyncio.sleep(0.05)
            existing3 = await self.client.get(link_key)
            if existing3:
                await self._ensure_identity_peer(existing3, p, ext)
                return existing3, False

        raise MemoryStorageError("could not acquire identity lock")

    async def _user_has_memory_data(self, user_id: str) -> bool:
        """True if user_id has multi-chat records, active chat, or agent_session keys."""
        if not self.client:
            return False
        try:
            chats_key = self._chats_key(user_id)
            if await self.client.exists(chats_key) and await self.client.hlen(chats_key) > 0:
                return True
            if await self.client.exists(self._active_chat_key(user_id)):
                return True
            cur = 0
            while True:
                cur, keys = await self.client.scan(
                    cursor=cur, match=f"agent_session:{user_id}:*", count=30
                )
                if keys:
                    return True
                if cur == 0:
                    break
        except Exception:
            return False
        return False

    async def delete_all_user_memory_data(self, user_id: str) -> None:
        """
        Remove all multi-chat Redis keys for this user id namespace (chats, meta, history, sessions).
        Does not touch identity:link:* or pairing keys.
        """
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        uid = user_id.strip()
        if not uid:
            return

        cids = await self.client.hkeys(self._chats_key(uid))
        pipe = self.client.pipeline()
        for cid in cids or []:
            pipe.delete(self._chat_meta_key(uid, cid))
            pipe.delete(self._history_key(uid, cid))
        pipe.delete(self._chats_key(uid))
        pipe.delete(self._active_chat_key(uid))
        await pipe.execute()

        cur = 0
        while True:
            cur, keys = await self.client.scan(
                cursor=cur, match=f"agent_session:{uid}:*", count=100
            )
            if keys:
                await self.client.delete(*keys)
            if cur == 0:
                break

        logger.info("Deleted all Redis memory keys for user namespace %s", uid)

    def _pairing_key(self, code: str) -> str:
        return f"identity:pair:{code.strip().upper()}"

    def _random_pairing_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(PAIRING_CODE_LENGTH))

    async def create_pairing_code(
        self, target_canonical_id: str, intended_provider: str
    ) -> tuple[str, int]:
        """
        Create a one-time code. The user must redeem it from `intended_provider`
        (telegram or max) to attach that account to target_canonical_id.
        """
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        try:
            UUID(target_canonical_id.strip())
        except ValueError as e:
            raise MemoryStorageError("target_canonical_id must be a UUID string") from e

        ip = intended_provider.lower().strip()
        if ip not in ("telegram", "max"):
            raise MemoryStorageError("intended_provider must be telegram or max")

        for _ in range(64):
            code = self._random_pairing_code()
            key = self._pairing_key(code)
            payload = json.dumps(
                {"target_canonical_id": target_canonical_id.strip(), "intended_provider": ip},
                ensure_ascii=False,
            )
            ok = await self.client.set(
                key,
                payload,
                nx=True,
                ex=PAIRING_CODE_TTL_SECONDS,
            )
            if ok:
                return code, PAIRING_CODE_TTL_SECONDS

        raise MemoryStorageError("failed to allocate a unique pairing code")

    async def redeem_pairing_code(
        self, code: str, provider: str, external_id: str
    ) -> dict[str, Any]:
        """
        Attach identity:link:{provider}:{external_id} to the canonical id from the code.

        Deletes all Memory data for the secondary namespace before linking (so the initiator's
        history is kept; the redeemer's old isolated history is removed).
        """
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        p = provider.lower().strip()
        ext = external_id.strip()
        if p not in ("telegram", "max") or not ext:
            raise MemoryStorageError("unsupported provider or empty external_id")

        key = self._pairing_key(code)
        raw = await self.client.get(key)
        if not raw:
            raise MemoryStorageError("invalid or expired pairing code")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise MemoryStorageError("corrupt pairing record") from e

        intended = data.get("intended_provider")
        target = data.get("target_canonical_id")
        if not target or not isinstance(target, str):
            raise MemoryStorageError("corrupt pairing record")
        if intended != p:
            raise MemoryStorageError(
                f"this code must be entered in {intended}, not another messenger"
            )

        try:
            UUID(target)
        except ValueError as e:
            raise MemoryStorageError("corrupt pairing target id") from e

        lock_key = self._identity_lock_key(p, ext)
        for _ in range(50):
            if await self.client.set(lock_key, "1", nx=True, ex=30):
                try:
                    link_key = self._identity_link_key(p, ext)
                    legacy = self._legacy_user_id(p, ext)
                    old_link = await self.client.get(link_key)

                    to_wipe: set[str] = set()
                    if old_link:
                        to_wipe.add(old_link)
                    to_wipe.add(legacy)

                    wiped_any = False
                    for uid in to_wipe:
                        if not uid or uid == target:
                            continue
                        await self.delete_all_user_memory_data(uid)
                        wiped_any = True

                    await self.client.set(link_key, target)
                    await self._ensure_identity_peer(target, p, ext)
                    await self.client.delete(key)
                    return {
                        "canonical_user_id": target,
                        "linked_provider": p,
                        "secondary_data_wiped": wiped_any,
                    }
                finally:
                    await self.client.delete(lock_key)
            await asyncio.sleep(0.05)

        raise MemoryStorageError("could not acquire identity lock for redeem")

    async def link_identity_to_canonical(
        self, provider: str, external_id: str, to_canonical: str
    ) -> dict[str, Any]:
        """
        Point identity:link:{provider}:{external_id} to an existing canonical UUID.

        Migrates Redis data from the prior mapping (or legacy max: / tg id layout)
        when needed. Raises if both source and target already have non-empty data
        (merge not implemented).
        """
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        try:
            UUID(to_canonical)
        except ValueError as e:
            raise MemoryStorageError("canonical_user_id must be a UUID string") from e

        p = provider.lower().strip()
        if p not in ("telegram", "max"):
            raise MemoryStorageError(f"unsupported provider: {provider}")
        ext = external_id.strip()
        if not ext:
            raise MemoryStorageError("external_id is required")

        link_key = self._identity_link_key(p, ext)
        legacy = self._legacy_user_id(p, ext)
        lock_key = self._identity_lock_key(p, ext)

        for _ in range(50):
            if await self.client.set(lock_key, "1", nx=True, ex=30):
                try:
                    old_link = await self.client.get(link_key)
                    if old_link == to_canonical:
                        await self._ensure_identity_peer(to_canonical, p, ext)
                        return {
                            "canonical_user_id": to_canonical,
                            "migrated": False,
                            "detail": "already linked",
                        }

                    primary_src: str | None = old_link
                    if not primary_src and await self._user_has_memory_data(legacy):
                        primary_src = legacy

                    migrated = False
                    if primary_src and primary_src != to_canonical:
                        has_t = await self._user_has_memory_data(to_canonical)
                        has_s = await self._user_has_memory_data(primary_src)
                        if has_t and has_s:
                            raise MemoryStorageError(
                                "both the target canonical id and the other identity have chat data; "
                                "merge is not supported — clear or export one side first"
                            )
                        await self._migrate_user_redis_keys(primary_src, to_canonical)
                        migrated = True

                    await self.client.set(link_key, to_canonical)
                    await self._ensure_identity_peer(to_canonical, p, ext)
                    return {
                        "canonical_user_id": to_canonical,
                        "migrated": migrated,
                        "detail": "linked",
                    }
                finally:
                    await self.client.delete(lock_key)
            await asyncio.sleep(0.05)
            cur = await self.client.get(link_key)
            if cur == to_canonical:
                await self._ensure_identity_peer(to_canonical, p, ext)
                return {
                    "canonical_user_id": to_canonical,
                    "migrated": False,
                    "detail": "already linked",
                }

        raise MemoryStorageError("could not acquire identity lock for link")

    # =========================================================================
    # Per-agent session (last chat + bot used for this logical agent)
    # Key: agent_session:{user_id}:{agent_id}  JSON, TTL=7d
    # =========================================================================

    def _agent_session_key(self, user_id: str, agent_id: str) -> str:
        return f"agent_session:{user_id}:{agent_id}"

    async def get_agent_session(self, user_id: str, agent_id: str) -> dict[str, Any] | None:
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")
        raw = await self.client.get(self._agent_session_key(user_id, agent_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set_agent_session(
        self,
        user_id: str,
        agent_id: str,
        chat_id: str,
        bot_id: str | None = None,
        extra: dict[str, Any] | None = None,
        ttl: int = CHAT_TTL_SECONDS,
    ) -> dict[str, Any]:
        if not self.client:
            raise MemoryStorageError("Redis client not connected")
        now = datetime.now(timezone.utc).isoformat()
        data: dict[str, Any] = {
            "user_id": user_id,
            "agent_id": agent_id,
            "chat_id": chat_id,
            "bot_id": bot_id or "",
            "updated_at": now,
        }
        if extra:
            data.update(extra)
        await self.client.setex(
            self._agent_session_key(user_id, agent_id),
            ttl,
            json.dumps(data, ensure_ascii=False),
        )
        return data

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
