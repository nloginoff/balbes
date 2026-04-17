"""
Qdrant client for long-term memory with semantic search.

Provides methods for:
- Storing memories with vector embeddings
- Semantic search across memories
- Memory filtering and deletion
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from shared.config import get_settings
from shared.exceptions import MemorySearchError, MemoryStorageError
from shared.openrouter_http import openrouter_json_headers

settings = get_settings()
logger = logging.getLogger("memory-service.qdrant")


class QdrantClient:
    """
    Async Qdrant client for vector memory storage.
    """

    # Embedding model configuration
    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIMENSION = 1536
    COLLECTION_NAME = settings.qdrant_collection

    def __init__(self):
        self.client: AsyncQdrantClient | None = None
        self.http_client: httpx.AsyncClient | None = None
        self._openrouter_key = settings.openrouter_api_key

    async def connect(self) -> None:
        """Connect to Qdrant and ensure collection exists"""
        try:
            # Initialize Qdrant client
            self.client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
                https=False,
                timeout=30,
            )

            # Initialize HTTP client for embeddings
            self.http_client = httpx.AsyncClient(timeout=60.0)

            # Check connection
            collections = await self.client.get_collections()
            logger.info(f"Connected to Qdrant ({len(collections.collections)} collections)")

            # Ensure collection exists
            await self._ensure_collection()

        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            raise MemoryStorageError(f"Qdrant connection failed: {e}")

    async def close(self) -> None:
        """Close Qdrant connection"""
        if self.http_client:
            await self.http_client.aclose()
        if self.client:
            await self.client.close()
        logger.info("Qdrant connection closed")

    async def health_check(self) -> bool:
        """Check Qdrant connection"""
        if not self.client:
            return False
        try:
            await self.client.get_collections()
            return True
        except Exception:
            return False

    async def _ensure_collection(self) -> None:
        """Create collection if it doesn't exist"""
        try:
            # Check if collection exists
            collections = await self.client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.COLLECTION_NAME in collection_names:
                logger.info(f"Collection '{self.COLLECTION_NAME}' already exists")
                return

            # Create collection
            logger.info(f"Creating collection '{self.COLLECTION_NAME}'...")

            await self.client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=self.EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )

            # Create payload indices for filtering
            await self.client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="agent_id",
                field_schema="keyword",
            )

            await self.client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="scope",
                field_schema="keyword",
            )

            logger.info(f"Collection '{self.COLLECTION_NAME}' created successfully")

        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
            raise MemoryStorageError(f"Failed to create collection: {e}")

    async def _generate_embedding(self, text: str) -> list[float]:
        """
        Generate embedding for text using OpenRouter.

        Args:
            text: Text to embed

        Returns:
            list[float]: Embedding vector
        """
        if not self.http_client:
            raise MemoryStorageError("HTTP client not initialized")

        if not self._openrouter_key:
            raise MemoryStorageError("OpenRouter API key not configured")

        try:
            response = await self.http_client.post(
                "https://openrouter.ai/api/v1/embeddings",
                headers=openrouter_json_headers(settings, api_key=self._openrouter_key),
                json={
                    "model": "openai/text-embedding-3-small",
                    "input": text,
                },
            )

            response.raise_for_status()
            data = response.json()

            embedding = data["data"][0]["embedding"]
            logger.debug(f"Generated embedding (dimension: {len(embedding)})")

            return embedding

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter API error: {e.response.status_code} - {e.response.text}")
            raise MemoryStorageError(f"Failed to generate embedding: {e}")
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise MemoryStorageError(f"Failed to generate embedding: {e}")

    # =========================================================================
    # Memory Storage Methods
    # =========================================================================

    async def store_memory(
        self,
        agent_id: str,
        content: str,
        scope: str = "personal",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Store memory with vector embedding.

        Args:
            agent_id: Agent identifier
            content: Memory content
            scope: Memory scope (personal, shared)
            metadata: Optional metadata (tags, task_id, etc.)

        Returns:
            dict: Memory ID and status
        """
        if not self.client:
            raise MemoryStorageError("Qdrant client not connected")

        try:
            # Generate embedding
            logger.debug(f"Generating embedding for memory (length: {len(content)})")
            embedding = await self._generate_embedding(content)

            # Generate memory ID
            memory_id = str(uuid4())

            # Prepare payload
            payload = {
                "agent_id": agent_id,
                "content": content,
                "scope": scope,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            # Store in Qdrant
            point = PointStruct(
                id=memory_id,
                vector=embedding,
                payload=payload,
            )

            await self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=[point],
            )

            logger.info(f"Stored memory: {memory_id} (agent: {agent_id}, scope: {scope})")

            return {
                "memory_id": memory_id,
                "status": "stored",
            }

        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            raise MemoryStorageError(f"Failed to store memory: {e}")

    async def search_memory(
        self,
        agent_id: str,
        query: str,
        scope: str | None = None,
        limit: int = 5,
        score_threshold: float = 0.3,
    ) -> dict[str, Any]:
        """
        Semantic search across agent's memories.

        Args:
            agent_id: Agent identifier
            query: Search query
            scope: Filter by scope (personal, shared, or None for both)
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)

        Returns:
            dict: Search results with scores
        """
        if not self.client:
            raise MemorySearchError("Qdrant client not connected")

        try:
            # Generate query embedding
            logger.debug(f"Searching memory: {query[:50]}...")
            query_embedding = await self._generate_embedding(query)

            # Build filter
            must_conditions = [
                FieldCondition(
                    key="agent_id",
                    match=MatchValue(value=agent_id),
                )
            ]

            if scope:
                must_conditions.append(
                    FieldCondition(
                        key="scope",
                        match=MatchValue(value=scope),
                    )
                )

            search_filter = Filter(must=must_conditions) if must_conditions else None

            # Search (qdrant-client>=1.17 uses query_points for vector search)
            search_response = await self.client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=query_embedding,
                query_filter=search_filter,
                limit=limit,
                score_threshold=score_threshold,
            )

            # Format results
            results = []
            for hit in search_response.points:
                result = {
                    "id": str(hit.id),
                    "content": hit.payload.get("content", ""),
                    "score": hit.score,
                    "metadata": hit.payload.get("metadata", {}),
                    "timestamp": hit.payload.get("created_at", ""),
                }
                results.append(result)

            logger.info(f"Found {len(results)} memories for query: {query[:30]}")

            return {
                "results": results,
                "total": len(results),
            }

        except Exception as e:
            logger.error(f"Failed to search memory: {e}")
            raise MemorySearchError(f"Failed to search memory: {e}")

    async def delete_memory(self, memory_id: str) -> dict[str, str]:
        """
        Delete memory by ID.

        Args:
            memory_id: Memory UUID

        Returns:
            dict: Status
        """
        if not self.client:
            raise MemoryStorageError("Qdrant client not connected")

        try:
            await self.client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=[memory_id],
            )
            logger.debug(f"Deleted memory: {memory_id}")
            return {"status": "deleted"}
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            raise MemoryStorageError(f"Failed to delete memory: {e}")
