"""
Redis client for fast context and history storage.

Provides methods for:
- Context storage (with TTL)
- Conversation history (last N messages)
- Token budget tracking
- Alert flags
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis

from shared.config import get_settings
from shared.exceptions import MemoryRetrievalError, MemoryStorageError

settings = get_settings()
logger = logging.getLogger("memory-service.redis")


class RedisClient:
    """
    Async Redis client for context and history management.
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
            # Test connection
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
        """Generate Redis key for context"""
        return f"context:{agent_id}:{key}"

    async def set_context(
        self,
        agent_id: str,
        key: str,
        value: dict[str, Any],
        ttl: int = 3600,
    ) -> dict[str, Any]:
        """
        Store context in Redis with TTL.

        Args:
            agent_id: Agent identifier
            key: Context key
            value: Context data (dict)
            ttl: Time to live in seconds (default 1 hour)

        Returns:
            dict: Status and expiration info
        """
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        try:
            redis_key = self._context_key(agent_id, key)
            value_json = json.dumps(value)

            await self.client.setex(redis_key, ttl, value_json)

            expires_at = datetime.now(UTC).timestamp() + ttl

            logger.debug(f"Set context: {redis_key} (TTL: {ttl}s)")

            return {
                "status": "ok",
                "key": key,
                "expires_at": datetime.fromtimestamp(expires_at, tz=UTC).isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to set context: {e}")
            raise MemoryStorageError(f"Failed to store context: {e}")

    async def get_context(
        self,
        agent_id: str,
        key: str,
    ) -> dict[str, Any] | None:
        """
        Retrieve context from Redis.

        Args:
            agent_id: Agent identifier
            key: Context key

        Returns:
            dict: Context data with TTL info, or None if not found
        """
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")

        try:
            redis_key = self._context_key(agent_id, key)

            # Get value and TTL
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
            logger.error(f"Failed to decode context JSON: {e}")
            raise MemoryRetrievalError(f"Invalid JSON in context: {e}")
        except Exception as e:
            logger.error(f"Failed to get context: {e}")
            raise MemoryRetrievalError(f"Failed to retrieve context: {e}")

    async def delete_context(self, agent_id: str, key: str) -> dict[str, str]:
        """
        Delete context from Redis.

        Args:
            agent_id: Agent identifier
            key: Context key

        Returns:
            dict: Status
        """
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        try:
            redis_key = self._context_key(agent_id, key)
            await self.client.delete(redis_key)
            logger.debug(f"Deleted context: {redis_key}")
            return {"status": "deleted"}
        except Exception as e:
            logger.error(f"Failed to delete context: {e}")
            raise MemoryStorageError(f"Failed to delete context: {e}")

    # =========================================================================
    # History Methods (Conversation History)
    # =========================================================================

    def _history_key(self, agent_id: str) -> str:
        """Generate Redis key for history"""
        return f"history:{agent_id}"

    async def add_to_history(
        self,
        agent_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Add message to conversation history.

        Args:
            agent_id: Agent identifier
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata

        Returns:
            dict: Status and history length
        """
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        try:
            redis_key = self._history_key(agent_id)

            message = {
                "role": role,
                "content": content,
                "metadata": metadata or {},
                "timestamp": datetime.now(UTC).isoformat(),
            }

            message_json = json.dumps(message)

            # Add to list (right push)
            await self.client.rpush(redis_key, message_json)

            # Keep only last 50 messages
            await self.client.ltrim(redis_key, -50, -1)

            # Get current length
            length = await self.client.llen(redis_key)

            logger.debug(f"Added to history: {agent_id} (length: {length})")

            return {
                "status": "ok",
                "history_length": length,
            }

        except Exception as e:
            logger.error(f"Failed to add to history: {e}")
            raise MemoryStorageError(f"Failed to add to history: {e}")

    async def get_history(
        self,
        agent_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Get conversation history.

        Args:
            agent_id: Agent identifier
            limit: Maximum number of messages (default 50)

        Returns:
            dict: Messages list and total count
        """
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")

        try:
            redis_key = self._history_key(agent_id)

            # Get last N messages
            messages_json = await self.client.lrange(redis_key, -limit, -1)

            # Parse JSON (messages already in chronological order)
            messages = []
            for msg_json in messages_json:
                try:
                    msg = json.loads(msg_json)
                    messages.append(msg)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to decode history message: {msg_json[:50]}")
                    continue

            total = await self.client.llen(redis_key)

            return {
                "messages": messages,
                "total": total,
            }

        except Exception as e:
            logger.error(f"Failed to get history: {e}")
            raise MemoryRetrievalError(f"Failed to retrieve history: {e}")

    async def clear_history(self, agent_id: str) -> dict[str, str]:
        """
        Clear conversation history.

        Args:
            agent_id: Agent identifier

        Returns:
            dict: Status
        """
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        try:
            redis_key = self._history_key(agent_id)
            await self.client.delete(redis_key)
            logger.debug(f"Cleared history: {agent_id}")
            return {"status": "cleared"}
        except Exception as e:
            logger.error(f"Failed to clear history: {e}")
            raise MemoryStorageError(f"Failed to clear history: {e}")

    # =========================================================================
    # Token Budget Methods
    # =========================================================================

    def _token_key(self, agent_id: str, period: str) -> str:
        """Generate Redis key for token tracking"""
        return f"tokens:{agent_id}:{period}"

    async def increment_tokens(
        self,
        agent_id: str,
        tokens: int,
        cost: float,
    ) -> dict[str, Any]:
        """
        Increment token usage for agent.

        Args:
            agent_id: Agent identifier
            tokens: Number of tokens used
            cost: Cost in USD

        Returns:
            dict: Updated token counts
        """
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        try:
            now = datetime.now(UTC)
            today_key = self._token_key(agent_id, now.strftime("%Y-%m-%d"))
            hour_key = self._token_key(agent_id, now.strftime("%Y-%m-%d-%H"))

            # Increment tokens and cost
            pipe = self.client.pipeline()

            # Daily counters
            pipe.hincrby(today_key, "tokens", tokens)
            pipe.hincrbyfloat(today_key, "cost", cost)
            pipe.expire(today_key, 86400 * 7)  # Keep for 7 days

            # Hourly counters
            pipe.hincrby(hour_key, "tokens", tokens)
            pipe.hincrbyfloat(hour_key, "cost", cost)
            pipe.expire(hour_key, 3600 * 24)  # Keep for 24 hours

            results = await pipe.execute()

            tokens_today = results[0]
            cost_today = results[1]
            tokens_hour = results[3]

            return {
                "tokens_today": tokens_today,
                "cost_today": cost_today,
                "tokens_hour": tokens_hour,
            }

        except Exception as e:
            logger.error(f"Failed to increment tokens: {e}")
            raise MemoryStorageError(f"Failed to track tokens: {e}")

    async def get_token_usage(
        self,
        agent_id: str,
    ) -> dict[str, Any]:
        """
        Get current token usage for agent.

        Args:
            agent_id: Agent identifier

        Returns:
            dict: Token usage stats
        """
        if not self.client:
            raise MemoryRetrievalError("Redis client not connected")

        try:
            now = datetime.now(UTC)
            today_key = self._token_key(agent_id, now.strftime("%Y-%m-%d"))
            hour_key = self._token_key(agent_id, now.strftime("%Y-%m-%d-%H"))

            # Get both counters
            today_data = await self.client.hgetall(today_key)
            hour_data = await self.client.hgetall(hour_key)

            return {
                "tokens_today": int(today_data.get("tokens", 0)),
                "cost_today": float(today_data.get("cost", 0)),
                "tokens_hour": int(hour_data.get("tokens", 0)),
            }

        except Exception as e:
            logger.error(f"Failed to get token usage: {e}")
            raise MemoryRetrievalError(f"Failed to retrieve token usage: {e}")

    # =========================================================================
    # Alert Flags
    # =========================================================================

    def _alert_key(self, agent_id: str, alert_type: str) -> str:
        """Generate Redis key for alert flag"""
        return f"alert:{agent_id}:{alert_type}"

    async def set_alert_flag(
        self,
        agent_id: str,
        alert_type: str,
        ttl: int = 3600,
    ) -> None:
        """
        Set alert flag (to prevent duplicate alerts).

        Args:
            agent_id: Agent identifier
            alert_type: Type of alert (e.g., "token_limit", "error")
            ttl: Time to live in seconds
        """
        if not self.client:
            raise MemoryStorageError("Redis client not connected")

        try:
            redis_key = self._alert_key(agent_id, alert_type)
            await self.client.setex(redis_key, ttl, "1")
            logger.debug(f"Set alert flag: {redis_key}")
        except Exception as e:
            logger.error(f"Failed to set alert flag: {e}")

    async def check_alert_flag(
        self,
        agent_id: str,
        alert_type: str,
    ) -> bool:
        """
        Check if alert flag exists.

        Args:
            agent_id: Agent identifier
            alert_type: Type of alert

        Returns:
            bool: True if flag exists
        """
        if not self.client:
            return False

        try:
            redis_key = self._alert_key(agent_id, alert_type)
            exists = await self.client.exists(redis_key)
            return bool(exists)
        except Exception as e:
            logger.error(f"Failed to check alert flag: {e}")
            return False
