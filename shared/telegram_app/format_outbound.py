"""
Convert model / orchestrator plain text to Telegram HTML (parse_mode=HTML).

Pipeline: fenced ``` code ``` blocks become <pre>; prose is html-escaped, then
**bold** and `inline code` (single backticks) become safe tags. Arbitrary <>&
from the model cannot break Telegram entity parsing.

See https://core.telegram.org/bots/api#html-style
"""

from __future__ import annotations

import html
import re

from shared.telegram_app.text import split_message


# Placeholders must survive html.escape (ASCII controls are unchanged).
def _ph_inline(i: int) -> str:
    return f"\x01INL{i}\x01"


def _prose_to_telegram_html(segment: str) -> str:
    """Escape and apply **bold** and `inline code` on a prose segment (no ``` fences)."""
    if not segment:
        return ""
    codes: list[str] = []

    def _inline_repl(m: re.Match[str]) -> str:
        codes.append(m.group(1))
        return _ph_inline(len(codes) - 1)

    # Inline `code` (non-greedy, no nested backticks)
    t = re.sub(r"`([^`]+)`", _inline_repl, segment)
    t = html.escape(t, quote=False)
    # Restore inline code as escaped content inside <code>
    for i, content in enumerate(codes):
        t = t.replace(_ph_inline(i), f"<code>{html.escape(content, quote=False)}</code>")
    # **bold** (after escape; * unchanged)
    t = re.sub(r"\*\*([^*]+?)\*\*", r"<b>\1</b>", t)
    return t


_FENCE_RE = re.compile(
    r"```(?:[a-zA-Z0-9_-]*)\s*\n?([\s\S]*?)```",
    re.MULTILINE,
)


def model_text_to_telegram_html(text: str) -> str:
    """
    Full message: alternate prose (markdown-lite) and fenced code blocks.
    """
    if not text:
        return ""
    out: list[str] = []
    pos = 0
    for m in _FENCE_RE.finditer(text):
        before = text[pos : m.start()]
        if before:
            out.append(_prose_to_telegram_html(before))
        code_body = m.group(1)
        # Strip one trailing newline common in fenced blocks; keep internal newlines
        code_body = code_body.rstrip("\n")
        out.append(f"<pre>{html.escape(code_body, quote=False)}</pre>")
        pos = m.end()
    tail = text[pos:]
    if tail:
        out.append(_prose_to_telegram_html(tail))
    return "".join(out)


def chunk_raw_text_for_telegram(raw: str, limit: int = 4096) -> list[str]:
    """Split raw model text before HTML conversion (same limits as Telegram)."""
    return split_message(raw, limit=limit)


async def send_reply_html_with_plain_fallback(
    send_coro,
    raw_text: str,
    *,
    limit: int = 4096,
) -> None:
    """
    For each chunk: send as HTML; on any failure, send the same chunk as plain text.

    send_coro: async (text: str, *, parse_mode: str | None) -> Any
    """
    for chunk in chunk_raw_text_for_telegram(raw_text, limit=limit):
        body = model_text_to_telegram_html(chunk)
        try:
            await send_coro(body, parse_mode="HTML")
        except Exception:
            await send_coro(chunk, parse_mode=None)
