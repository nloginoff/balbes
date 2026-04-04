"""
Post queue management for the Blogger service.

Manages the draft → pending_approval → approved → scheduled → published lifecycle.
Enforces a daily publishing quota (default: 3 posts/day).
"""

import logging
import uuid
from datetime import datetime

import asyncpg

logger = logging.getLogger("blogger.post_queue")


class PostQueue:
    """PostgreSQL-backed post queue with daily quota enforcement."""

    def __init__(self, db: asyncpg.Pool, daily_quota: int = 3):
        self.db = db
        self.daily_quota = daily_quota

    async def create_draft(
        self,
        content_ru: str,
        content_en: str,
        post_type: str,
        source_refs: list[str],
        notes: str = "",
        title: str = "",
    ) -> str:
        """
        Insert a new draft post. Returns post UUID.
        Status starts as 'pending_approval'.
        """
        post_id = str(uuid.uuid4())
        import json

        content_json = json.dumps({"ru": content_ru, "en": content_en}, ensure_ascii=False)
        source_refs_json = json.dumps(source_refs, ensure_ascii=False)

        await self.db.execute(
            """
            INSERT INTO blog_posts (id, title, content, post_type, status, source_refs, notes)
            VALUES ($1, $2, $3::jsonb, $4, 'pending_approval', $5::jsonb, $6)
            """,
            post_id,
            title or "",
            content_json,
            post_type,
            source_refs_json,
            notes or "",
        )
        logger.info("Created draft post %s (type=%s)", post_id, post_type)
        return post_id

    async def get_post(self, post_id: str) -> dict | None:
        """Fetch a single post by ID."""
        row = await self.db.fetchrow(
            """
            SELECT p.*, bc.tg_channel_id, bc.language, bc.auto_publish, bc.name as channel_name
            FROM blog_posts p
            LEFT JOIN blog_channels bc ON bc.id = p.channel_id
            WHERE p.id = $1
            """,
            post_id,
        )
        return dict(row) if row else None

    async def list_posts(
        self,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """List posts filtered by status.

        ``status='draft'`` matches both ``draft`` and ``pending_approval`` (what :meth:`create_draft`
        inserts). ``pending`` is an alias for ``pending_approval`` (LLM / users say «pending»).
        """
        if status == "pending":
            status = "pending_approval"
        if status:
            if status == "draft":
                rows = await self.db.fetch(
                    """
                    SELECT p.id, p.title, p.post_type, p.status, p.created_at, p.scheduled_at,
                           p.published_at, p.notes, bc.name as channel_name, bc.language
                    FROM blog_posts p
                    LEFT JOIN blog_channels bc ON bc.id = p.channel_id
                    WHERE p.status IN ('draft', 'pending_approval')
                    ORDER BY p.created_at DESC
                    LIMIT $1
                    """,
                    limit,
                )
            else:
                rows = await self.db.fetch(
                    """
                    SELECT p.id, p.title, p.post_type, p.status, p.created_at, p.scheduled_at,
                           p.published_at, p.notes, bc.name as channel_name, bc.language
                    FROM blog_posts p
                    LEFT JOIN blog_channels bc ON bc.id = p.channel_id
                    WHERE p.status = $1
                    ORDER BY p.created_at DESC
                    LIMIT $2
                    """,
                    status,
                    limit,
                )
        else:
            rows = await self.db.fetch(
                """
                SELECT p.id, p.title, p.post_type, p.status, p.created_at, p.scheduled_at,
                       p.published_at, p.notes, bc.name as channel_name, bc.language
                FROM blog_posts p
                LEFT JOIN blog_channels bc ON bc.id = p.channel_id
                ORDER BY p.created_at DESC
                LIMIT $1
                """,
                limit,
            )
        return [dict(r) for r in rows]

    async def set_approval_message_id(self, post_id: str, message_id: int) -> None:
        """Store Telegram message_id for the approval preview message."""
        await self.db.execute(
            "UPDATE blog_posts SET approval_message_id = $1, updated_at = NOW() WHERE id = $2",
            message_id,
            post_id,
        )

    async def approve(self, post_id: str) -> bool:
        """Mark post as approved (moves to queue)."""
        result = await self.db.execute(
            """
            UPDATE blog_posts
            SET status = 'approved', updated_at = NOW()
            WHERE id = $1 AND status = 'pending_approval'
            """,
            post_id,
        )
        return result.endswith("1")

    async def reject(self, post_id: str) -> bool:
        """Mark post as rejected."""
        result = await self.db.execute(
            """
            UPDATE blog_posts
            SET status = 'rejected', updated_at = NOW()
            WHERE id = $1 AND status IN ('pending_approval', 'approved')
            """,
            post_id,
        )
        return result.endswith("1")

    async def update_content(
        self,
        post_id: str,
        content_ru: str,
        content_en: str,
        title: str = "",
    ) -> bool:
        """Update post content after revision. Status back to pending_approval."""
        import json

        content_json = json.dumps({"ru": content_ru, "en": content_en}, ensure_ascii=False)
        result = await self.db.execute(
            """
            UPDATE blog_posts
            SET content = $1::jsonb,
                title = COALESCE(NULLIF($2, ''), title),
                status = 'pending_approval',
                updated_at = NOW()
            WHERE id = $3
            """,
            content_json,
            title,
            post_id,
        )
        return result.endswith("1")

    async def schedule(self, post_id: str, publish_at: datetime) -> bool:
        """Schedule an approved post for publishing at a specific time."""
        result = await self.db.execute(
            """
            UPDATE blog_posts
            SET status = 'scheduled', scheduled_at = $1, updated_at = NOW()
            WHERE id = $2 AND status = 'approved'
            """,
            publish_at,
            post_id,
        )
        return result.endswith("1")

    async def mark_published(self, post_id: str, channel_id: int) -> bool:
        """Mark post as published."""
        result = await self.db.execute(
            """
            UPDATE blog_posts
            SET status = 'published', published_at = NOW(), channel_id = $1, updated_at = NOW()
            WHERE id = $2
            """,
            channel_id,
            post_id,
        )
        return result.endswith("1")

    async def published_today_count(self) -> int:
        """Return number of posts published today."""
        row = await self.db.fetchrow(
            """
            SELECT COUNT(*) as cnt
            FROM blog_posts
            WHERE status = 'published' AND DATE(published_at) = CURRENT_DATE
            """
        )
        return int(row["cnt"]) if row else 0

    async def get_publishable(self) -> list[dict]:
        """
        Return approved/scheduled posts ready to publish (respects daily quota).
        Only returns posts where scheduled_at <= NOW() or scheduled_at IS NULL.
        """
        published_today = await self.published_today_count()
        remaining = self.daily_quota - published_today
        if remaining <= 0:
            logger.info("Daily quota reached (%d/%d)", published_today, self.daily_quota)
            return []

        rows = await self.db.fetch(
            """
            SELECT p.id, p.title, p.content, p.post_type, p.source_refs, p.notes,
                   bc.tg_channel_id, bc.language, bc.name as channel_name, bc.id as channel_db_id,
                   bc.auto_publish
            FROM blog_posts p
            JOIN blog_channels bc ON bc.id = p.channel_id
            WHERE p.status IN ('approved', 'scheduled')
              AND (p.scheduled_at IS NULL OR p.scheduled_at <= NOW())
              AND bc.is_active = TRUE
            ORDER BY p.created_at ASC
            LIMIT $1
            """,
            remaining,
        )
        return [dict(r) for r in rows]

    async def get_published_posts(self, limit: int = 10) -> list[dict]:
        """Return recent published posts for context (avoid repetition)."""
        rows = await self.db.fetch(
            """
            SELECT p.id, p.title, p.content, p.post_type, p.published_at,
                   bc.language, bc.name as channel_name
            FROM blog_posts p
            LEFT JOIN blog_channels bc ON bc.id = p.channel_id
            WHERE p.status = 'published'
            ORDER BY p.published_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]

    async def get_channels(self) -> list[dict]:
        """Return all active blog channels."""
        rows = await self.db.fetch(
            "SELECT * FROM blog_channels WHERE is_active = TRUE ORDER BY language"
        )
        return [dict(r) for r in rows]
