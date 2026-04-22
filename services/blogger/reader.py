"""
Data readers for the Blogger agent.

Three sources:
  - ChatReader: reads agent chat history from memory-service REST API
  - CursorFileReader: reads Markdown files exported from Cursor AI
  - BusinessChatReader: reads anonymized messages from business_messages table
"""

import logging
from datetime import datetime
from pathlib import Path

import asyncpg
import httpx

logger = logging.getLogger("blogger.reader")

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


class ChatReader:
    """Reads chat history from the memory service.

    History is stored under /history/{user_id}/{chat_id} where user_id is
    the owner's Telegram user_id. Reads all chats for that user and merges
    the messages.
    """

    def __init__(self, memory_url: str, http: httpx.AsyncClient):
        self.memory_url = memory_url.rstrip("/")
        self.http = http

    async def _list_chats(self, user_id: str) -> list[dict]:
        """Return all chats for a user from the memory service."""
        try:
            resp = await self.http.get(
                f"{self.memory_url}/api/v1/chats/{user_id}",
                timeout=10.0,
            )
            if resp.status_code == 200:
                return resp.json().get("chats", [])
            logger.warning("list_chats user=%s → %s", user_id, resp.status_code)
        except Exception as exc:
            logger.warning("ChatReader._list_chats error: %s", exc)
        return []

    async def read(
        self,
        user_id: str,
        from_ts: datetime | None = None,
        limit: int = 100,
        agent_ids: set[str] | None = None,
    ) -> list[dict]:
        """
        Fetch recent messages for the owner across all their chats.

        Args:
            user_id:  Owner's Telegram user_id (string).
            from_ts:  Only return messages newer than this timestamp.
            limit:    Max messages to fetch per chat.
            agent_ids: If set, only process chats whose ``agent_id`` (from list_chats) is
                in this set (e.g. ``{'balbes', 'coder'}`` for dev-blog). Case-insensitive.

        Returns list of {chat_id, chat_name, role, content, timestamp}.
        """
        chats = await self._list_chats(user_id)
        if agent_ids is not None and agent_ids:
            want = {a.strip().lower() for a in agent_ids if a and str(a).strip()}
            if want:
                before = len(chats)
                filtered = []
                for c in chats:
                    aid = (c.get("agent_id") or "balbes") or "balbes"
                    if str(aid).lower() in want:
                        filtered.append(c)
                chats = filtered
                logger.info(
                    "ChatReader: agent_id filter %s → %d/%d chats for user %s",
                    want,
                    len(chats),
                    before,
                    user_id,
                )
        if not chats:
            logger.info("ChatReader: no chats found for user %s", user_id)
            return []

        results: list[dict] = []
        for chat in chats:
            chat_id = chat.get("chat_id") or chat.get("id", "")
            chat_name = chat.get("name", chat_id)
            if not chat_id:
                continue
            try:
                resp = await self.http.get(
                    f"{self.memory_url}/api/v1/history/{user_id}/{chat_id}",
                    params={"limit": limit},
                    timeout=15.0,
                )
                if resp.status_code != 200:
                    logger.warning(
                        "ChatReader: history %s/%s → %s", user_id, chat_id, resp.status_code
                    )
                    continue
                messages = resp.json().get("messages", [])
                for m in messages:
                    ts_str = m.get("timestamp") or m.get("created_at", "")
                    if from_ts and ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if ts < from_ts:
                                continue
                        except ValueError:
                            pass
                    results.append(
                        {
                            "chat_id": chat_id,
                            "chat_name": chat_name,
                            "role": m.get("role", ""),
                            "content": m.get("content", ""),
                            "timestamp": ts_str,
                        }
                    )
            except Exception as exc:
                logger.warning("ChatReader error for chat %s: %s", chat_id, exc)

        logger.info(
            "ChatReader: read %d messages from %d chats for user %s",
            len(results),
            len(chats),
            user_id,
        )
        return results


class CursorFileReader:
    """Reads Markdown files exported from Cursor AI sessions."""

    def __init__(self, cursor_dir: Path | None = None):
        self.cursor_dir = cursor_dir or (_PROJECT_ROOT / "data" / "cursor_chats")

    def list_files(self) -> list[Path]:
        """List all .md files in cursor_dir sorted by modification time (newest first)."""
        if not self.cursor_dir.exists():
            return []
        files = sorted(self.cursor_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files

    def read_file(self, path: Path | str) -> str:
        """Read content of a Markdown file. Resolves relative paths from project root."""
        p = Path(path)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        if not p.exists():
            raise FileNotFoundError(f"Cursor file not found: {p}")
        return p.read_text(encoding="utf-8", errors="replace")

    def read_latest(self, n: int = 3) -> list[dict]:
        """
        Read the n most recently modified files.
        Returns list of {path, content} dicts.
        """
        results = []
        for f in self.list_files()[:n]:
            try:
                results.append(
                    {"path": str(f.relative_to(_PROJECT_ROOT)), "content": self.read_file(f)}
                )
            except Exception as exc:
                logger.warning("CursorFileReader error %s: %s", f, exc)
        return results


class BusinessChatReader:
    """Reads anonymized messages from the business_messages PostgreSQL table."""

    def __init__(self, db: asyncpg.Pool):
        self.db = db

    async def read(
        self,
        chat_ids: list[int] | None = None,
        from_ts: datetime | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """
        Fetch anonymized business messages.
        Returns list of {chat_id, anon_sender, content, ts} dicts.
        """
        conditions = ["1=1"]
        args: list = []

        if chat_ids:
            args.append(chat_ids)
            conditions.append(f"m.chat_id = ANY(${len(args)}::int[])")

        if from_ts:
            args.append(from_ts)
            conditions.append(f"m.ts >= ${len(args)}")

        args.append(limit)
        where = " AND ".join(conditions)
        query = f"""
            SELECT m.chat_id, bc.name as chat_name, m.anon_sender, m.content, m.ts
            FROM business_messages m
            JOIN business_chats bc ON bc.id = m.chat_id
            WHERE {where}
            ORDER BY m.ts DESC
            LIMIT ${len(args)}
        """
        try:
            rows = await self.db.fetch(query, *args)
            return [
                {
                    "chat_id": r["chat_id"],
                    "chat_name": r["chat_name"],
                    "anon_sender": r["anon_sender"],
                    "content": r["content"],
                    "ts": r["ts"].isoformat() if r["ts"] else "",
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("BusinessChatReader error: %s", exc)
            return []

    async def mark_processed(self, chat_ids: list[int], before_ts: datetime) -> int:
        """Mark messages as processed (used after generating summary)."""
        try:
            result = await self.db.execute(
                """
                UPDATE business_messages
                SET processed = TRUE
                WHERE chat_id = ANY($1::int[]) AND ts <= $2 AND NOT processed
                """,
                chat_ids,
                before_ts,
            )
            return int(result.split()[-1])
        except Exception as exc:
            logger.error("mark_processed error: %s", exc)
            return 0
