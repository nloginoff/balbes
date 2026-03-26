"""
PostgreSQL client for skills storage and metadata.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

import asyncpg

from shared.config import get_settings
from shared.exceptions import DatabaseConnectionError, DatabaseQueryError

settings = get_settings()
logger = logging.getLogger("skills-registry.postgres")


class PostgresClient:
    """PostgreSQL client for skills storage"""

    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Create connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                host=settings.postgres_host,
                port=settings.postgres_port,
                database=settings.postgres_db,
                user=settings.postgres_user,
                password=settings.postgres_password,
                min_size=settings.connection_pool_size,
                max_size=settings.connection_pool_size,
                timeout=30,
            )
            logger.info("PostgreSQL connection pool established")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise DatabaseConnectionError(f"PostgreSQL connection failed: {e}")

    async def close(self) -> None:
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")

    async def health_check(self) -> bool:
        """Health check"""
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    async def create_skill(
        self,
        skill_id: str,
        name: str,
        description: str,
        version: str,
        tags: list[str],
        category: str,
        implementation_url: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        estimated_tokens: int,
        authors: list[str],
        dependencies: list[str],
    ) -> dict[str, Any]:
        """Create a new skill"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                now = datetime.now(UTC)

                row = await conn.fetchrow(
                    """
                    INSERT INTO skills (
                        skill_id,
                        name,
                        description,
                        version,
                        tags,
                        category,
                        implementation_url,
                        input_schema,
                        output_schema,
                        estimated_tokens,
                        authors,
                        dependencies,
                        created_at,
                        updated_at,
                        usage_count,
                        rating
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11, $12, $13, $14, $15, $16)
                    RETURNING *
                """,
                    skill_id,
                    name,
                    description,
                    version,
                    tags,
                    category,
                    implementation_url,
                    json.dumps(input_schema),
                    json.dumps(output_schema),
                    estimated_tokens,
                    authors,
                    dependencies,
                    now,
                    now,
                    0,
                    0.0,
                )

                logger.info(f"Created skill: {skill_id} (name: {name})")
                return dict(row)

        except asyncpg.UniqueViolationError:
            raise DatabaseQueryError(f"Skill with ID {skill_id} already exists")
        except Exception as e:
            logger.error(f"Failed to create skill: {e}")
            raise DatabaseQueryError(f"Failed to create skill: {e}")

    async def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        """Get skill by ID"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM skills WHERE skill_id = $1", skill_id)
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Failed to get skill: {e}")
            raise DatabaseQueryError(f"Failed to get skill: {e}")

    async def get_all_skills(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """Get all skills with pagination"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                # Get total count
                total = await conn.fetchval("SELECT COUNT(*) FROM skills")

                # Get skills
                rows = await conn.fetch(
                    """
                    SELECT * FROM skills
                    ORDER BY created_at DESC
                    LIMIT $1 OFFSET $2
                """,
                    limit,
                    offset,
                )

                skills = [dict(row) for row in rows]

                return {
                    "skills": skills,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }
        except Exception as e:
            logger.error(f"Failed to get skills: {e}")
            raise DatabaseQueryError(f"Failed to get skills: {e}")

    async def search_skills_by_category_tags(
        self,
        category: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search skills by category and tags"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                query = "SELECT * FROM skills WHERE 1=1"
                params = []

                if category:
                    params.append(category)
                    query += f" AND category = ${len(params)}"

                if tags:
                    # Search for skills that have any of the tags
                    params.append(tags)
                    query += f" AND tags && ${len(params)}"

                query += " ORDER BY rating DESC, usage_count DESC LIMIT " + str(limit)

                rows = await conn.fetch(query, *params)
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to search skills: {e}")
            raise DatabaseQueryError(f"Failed to search skills: {e}")

    async def update_skill_usage(
        self,
        skill_id: str,
        success: bool,
        tokens_used: int,
    ) -> None:
        """Update skill usage statistics"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                now = datetime.now(UTC)

                await conn.execute(
                    """
                    UPDATE skills
                    SET
                        usage_count = usage_count + 1,
                        updated_at = $2
                    WHERE skill_id = $1
                """,
                    skill_id,
                    now,
                )

                logger.debug(f"Updated skill usage: {skill_id}")

        except Exception as e:
            logger.error(f"Failed to update skill usage: {e}")
            raise DatabaseQueryError(f"Failed to update skill usage: {e}")

    async def rate_skill(
        self,
        skill_id: str,
        rating: float,  # 0-5
    ) -> None:
        """Update skill rating (simple average)"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                # Get current rating and usage count
                row = await conn.fetchrow(
                    "SELECT rating, usage_count FROM skills WHERE skill_id = $1", skill_id
                )

                if not row:
                    raise DatabaseQueryError(f"Skill {skill_id} not found")

                current_rating = row["rating"]
                row["usage_count"]

                # Simple average: (current_rating * count + new_rating) / (count + 1)
                # But we'll use a simpler approach: exponential moving average
                new_rating = (current_rating * 0.7) + (rating * 0.3)

                await conn.execute(
                    """
                    UPDATE skills
                    SET rating = $2
                    WHERE skill_id = $1
                """,
                    skill_id,
                    new_rating,
                )

                logger.debug(f"Updated skill rating: {skill_id} = {new_rating:.2f}")

        except Exception as e:
            logger.error(f"Failed to rate skill: {e}")
            raise DatabaseQueryError(f"Failed to rate skill: {e}")
