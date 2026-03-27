"""
Qdrant client for skill embeddings and semantic search.
"""

import logging
from typing import Any

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

settings = get_settings()
logger = logging.getLogger("skills-registry.qdrant")


class QdrantClient:
    """Qdrant client for skill embeddings"""

    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIMENSION = 1536
    COLLECTION_NAME = "skill_embeddings"

    def __init__(self):
        self.client: AsyncQdrantClient | None = None
        self.http_client: httpx.AsyncClient | None = None
        self._openrouter_key = settings.openrouter_api_key

    async def connect(self) -> None:
        """Connect to Qdrant"""
        try:
            self.client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
                https=False,
                timeout=30,
            )

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
            collections = await self.client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.COLLECTION_NAME in collection_names:
                logger.info(f"Collection '{self.COLLECTION_NAME}' already exists")
                return

            logger.info(f"Creating collection '{self.COLLECTION_NAME}'...")

            await self.client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=self.EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )

            # Create indices
            await self.client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="category",
                field_schema="keyword",
            )

            await self.client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="tags",
                field_schema="keyword",
            )

            logger.info(f"Collection '{self.COLLECTION_NAME}' created successfully")

        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
            raise MemoryStorageError(f"Failed to create collection: {e}")

    async def _generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for text"""
        if not self.http_client:
            raise MemoryStorageError("HTTP client not initialized")

        if not self._openrouter_key:
            raise MemoryStorageError("OpenRouter API key not configured")

        try:
            response = await self.http_client.post(
                "https://openrouter.ai/api/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self._openrouter_key}",
                    "Content-Type": "application/json",
                },
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
            logger.error(f"OpenRouter API error: {e.response.status_code}")
            raise MemoryStorageError(f"Failed to generate embedding: {e}")
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise MemoryStorageError(f"Failed to generate embedding: {e}")

    async def index_skill(
        self,
        skill_id: str,
        name: str,
        description: str,
        category: str,
        tags: list[str],
    ) -> None:
        """Index a skill for semantic search"""
        if not self.client:
            raise MemoryStorageError("Qdrant client not connected")

        try:
            # Create searchable text
            search_text = f"{name} {description} {' '.join(tags)}"

            # Generate embedding
            embedding = await self._generate_embedding(search_text)

            # Create point
            point = PointStruct(
                id=skill_id,
                vector=embedding,
                payload={
                    "skill_id": skill_id,
                    "name": name,
                    "description": description,
                    "category": category,
                    "tags": tags,
                },
            )

            # Upsert (insert or update)
            await self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=[point],
            )

            logger.info(f"Indexed skill: {skill_id}")

        except Exception as e:
            logger.error(f"Failed to index skill: {e}")
            raise MemoryStorageError(f"Failed to index skill: {e}")

    async def search_skills(
        self,
        query: str,
        category: str | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for skills using semantic search"""
        if not self.client:
            raise MemorySearchError("Qdrant client not connected")

        try:
            # Generate query embedding
            query_embedding = await self._generate_embedding(query)

            # Build filter
            must_conditions = []

            if category:
                must_conditions.append(
                    FieldCondition(
                        key="category",
                        match=MatchValue(value=category),
                    )
                )

            if tags:
                must_conditions.append(
                    FieldCondition(
                        key="tags",
                        match=MatchValue(value=tags[0]),  # Match at least one tag
                    )
                )

            search_filter = Filter(must=must_conditions) if must_conditions else None

            # Search
            search_response = await self.client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=query_embedding,
                query_filter=search_filter,
                limit=limit,
                score_threshold=0.3,
            )

            # Format results
            results = []
            for hit in search_response.points:
                result = {
                    "skill_id": hit.payload.get("skill_id", ""),
                    "name": hit.payload.get("name", ""),
                    "description": hit.payload.get("description", ""),
                    "category": hit.payload.get("category", ""),
                    "tags": hit.payload.get("tags", []),
                    "score": hit.score,
                }
                results.append(result)

            logger.info(f"Found {len(results)} skills for query: {query[:30]}")

            return results

        except Exception as e:
            logger.error(f"Failed to search skills: {e}")
            raise MemorySearchError(f"Failed to search skills: {e}")
