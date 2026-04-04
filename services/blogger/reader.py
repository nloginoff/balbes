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
    """Reads agent chat history from the memory service."""

    def __init__(self, memory_url: str, http: httpx.AsyncClient):
        self.memory_url = memory_url.rstrip("/")
        self.http = http

    async def read(
        self,
        agents: list[str],
        from_ts: datetime | None = None,
        limit: int = 100,
        user_id: str = "0",
    ) -> list[dict]:
        """
        Fetch recent chat messages for the specified agents.
        Returns list of {role, content, agent_id, timestamp} dicts.
        """
        results: list[dict] = []
        for agent_id in agents:
            try:
                params: dict = {"limit": limit}
                resp = await self.http.get(
                    f"{self.memory_url}/api/v1/history/{user_id}",
                    params=params,
                    timeout=15.0,
                )
                if resp.status_code == 200:
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
                                "agent_id": agent_id,
                                "role": m.get("role", ""),
                                "content": m.get("content", ""),
                                "timestamp": ts_str,
                            }
                        )
                else:
                    logger.warning("Memory API %s → %s", agent_id, resp.status_code)
            except Exception as exc:
                logger.warning("ChatReader error for %s: %s", agent_id, exc)
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
