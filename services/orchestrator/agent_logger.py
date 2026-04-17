"""
Agent Activity Logger — per-agent JSONL log files.

Logs every tool/skill call with timestamp, input summary, result summary,
duration and success flag. Files are stored as:

  data/logs/agents/{agent_id}/YYYY-MM-DD.jsonl

One JSON object per line. The agent can read these logs via the
read_agent_logs tool and show them in chat.
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("orchestrator.agent_logger")

_write_lock = threading.Lock()


def _now_local() -> datetime:
    """Return current time in the server's local timezone (auto-detected from OS)."""
    return datetime.now().astimezone()


def _project_root() -> Path:
    return Path(__file__).parent.parent.parent


class AgentActivityLogger:
    """
    Writes tool-call activity to daily JSONL files per agent.

    Thread-safe: uses a module-level lock so multiple agents writing on
    different threads don't interleave log lines.
    """

    def __init__(self, agent_id: str, log_root: Path | None = None):
        self.agent_id = agent_id
        self._log_root = log_root or (_project_root() / "data" / "logs" / "agents")

    def _log_dir(self) -> Path:
        d = self._log_root / self.agent_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _log_file(self, date: datetime) -> Path:
        return self._log_dir() / f"{date.strftime('%Y-%m-%d')}.jsonl"

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def log_tool_call(
        self,
        tool_name: str,
        input_summary: str,
        result_summary: str,
        duration_ms: float,
        success: bool,
        user_id: str = "",
        chat_id: str = "",
        source: str = "user",  # "user" | "heartbeat"
    ) -> None:
        now = _now_local()
        entry = {
            "ts": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "agent": self.agent_id,
            "tool": tool_name,
            "input": input_summary,
            "result": result_summary,
            "duration_ms": round(duration_ms),
            "ok": success,
            "user": user_id,
            "chat": chat_id,
            "src": source,
        }
        line = json.dumps(entry, ensure_ascii=False)
        path = self._log_file(now)
        try:
            with _write_lock:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Failed to write activity log: {e}")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read_logs(
        self,
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        tool_filter: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Return log entries filtered by date / date range / tool name.

        date:        exact day  "today" | "yesterday" | "YYYY-MM-DD"
        start_date:  range start "YYYY-MM-DD"
        end_date:    range end   "YYYY-MM-DD" (inclusive)
        tool_filter: only entries for this tool name
        limit:       max entries returned (most recent first)

        Raises ValueError if a date string is not today/yesterday/YYYY-MM-DD.
        """
        today = _now_local().date()

        # Resolve keyword dates
        def _parse(s: str):
            s = (s or "").strip().lower()
            if not s:
                raise ValueError("пустая дата")
            if s == "today":
                return today
            if s == "yesterday":
                from datetime import timedelta

                return today - timedelta(days=1)
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except ValueError as e:
                raise ValueError(
                    f"ожидается YYYY-MM-DD, today или yesterday; получено: {s!r}"
                ) from e

        if date:
            d = _parse(date)
            files = [self._log_file(datetime(d.year, d.month, d.day))]
        elif start_date or end_date:
            from datetime import timedelta

            sd = _parse(start_date) if start_date else today - timedelta(days=7)
            ed = _parse(end_date) if end_date else today
            files = []
            cur = sd
            while cur <= ed:
                files.append(self._log_file(datetime(cur.year, cur.month, cur.day)))
                cur += timedelta(days=1)
        else:
            # Default: today
            files = [self._log_file(datetime(today.year, today.month, today.day))]

        entries: list[dict] = []
        for path in files:
            if not path.exists():
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            if tool_filter and obj.get("tool") != tool_filter:
                                continue
                            entries.append(obj)
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                logger.warning(f"[{self.agent_id}] Failed to read log {path}: {e}")

        # Most recent first, then apply limit
        entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
        return entries[:limit]

    def list_log_dates(self) -> list[str]:
        """Return list of dates that have log files (YYYY-MM-DD), newest first."""
        d = self._log_dir()
        dates = sorted(
            [p.stem for p in d.glob("????-??-??.jsonl")],
            reverse=True,
        )
        return dates

    # ------------------------------------------------------------------
    # Format for chat
    # ------------------------------------------------------------------

    def format_for_chat(self, entries: list[dict[str, Any]], title: str = "") -> str:
        """
        Convert log entries to a compact human-readable text for Telegram.
        """
        if not entries:
            return "Нет записей за указанный период."

        lines = []
        if title:
            lines.append(f"📋 {title}\n")

        for e in entries:
            ts = e.get("ts", "?")[:19]  # "YYYY-MM-DD HH:MM:SS"
            tool = e.get("tool", "?")
            inp = e.get("input", "")
            res = e.get("result", "")
            ok = "✅" if e.get("ok", True) else "❌"
            dur = e.get("duration_ms", 0)
            src = " [hb]" if e.get("src") == "heartbeat" else ""

            # Truncate long strings
            if len(inp) > 80:
                inp = inp[:77] + "..."
            if len(res) > 100:
                res = res[:97] + "..."

            lines.append(f"{ok} `{ts}`{src} **{tool}**\n   ↳ {inp}\n   → {res} ({dur}ms)")

        total = len(entries)
        lines.append(f"\n_Всего записей: {total}_")
        return "\n\n".join(lines)
