"""
Convert model / orchestrator plain text to Telegram HTML (parse_mode=HTML).

Pipeline: fenced ``` code ``` blocks become <pre>; prose is html-escaped, then
**bold** and `inline code` (single backticks) become safe tags. Arbitrary <>&
from the model cannot break Telegram entity parsing.

Outgoing chunks use ``raw_chunks_for_telegram_html``: HTML is often longer than the
raw model text (entities, tags), so we split raw text until each HTML chunk fits
the 4096-character Telegram limit.

See https://core.telegram.org/bots/api#html-style
"""

from __future__ import annotations

import html
import logging
import re

from shared.telegram_app.text import split_message

logger = logging.getLogger(__name__)

# Telegram Bot API: text after entity processing, max length (UTF-8 / Unicode codepoints).
TELEGRAM_HTML_MSG_LIMIT = 4096


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


def _split_raw_near_middle(segment: str) -> int:
    """Return cut index so segment[:cut] and segment[cut:] are both non-empty when len>=2."""
    n = len(segment)
    if n < 2:
        return n // 2 or 1
    mid = n // 2
    span = max(n // 4, 40)
    lo = max(1, mid - span)
    hi = min(n - 1, mid + span)
    for sep in ("\n\n", "\n"):
        i = segment.rfind(sep, lo, hi + 1)
        if i != -1:
            j = i + len(sep)
            if 0 < j < n:
                return j
    sp = segment.rfind(" ", lo, hi + 1)
    if sp != -1:
        j = sp + 1
        if 0 < j < n:
            return j
    return mid


def _raw_pieces_for_one_coarse_chunk(piece: str, out: list[str]) -> None:
    """
    Split one raw segment until model_text_to_telegram_html fits TELEGRAM_HTML_MSG_LIMIT.

    Raw chunks were limited by length only; HTML expands (&, <, >, tags), so the
    converted text can exceed 4096 and make Telegram reject parse_mode=HTML —
    then callers fell back to plain and users saw no formatting.
    """
    if not piece:
        return
    body = model_text_to_telegram_html(piece)
    if len(body) <= TELEGRAM_HTML_MSG_LIMIT:
        out.append(piece)
        return
    if len(piece) <= 1:
        out.append(piece)
        return
    cut = _split_raw_near_middle(piece)
    if cut <= 0 or cut >= len(piece):
        cut = len(piece) // 2
    _raw_pieces_for_one_coarse_chunk(piece[:cut], out)
    _raw_pieces_for_one_coarse_chunk(piece[cut:], out)


def raw_chunks_for_telegram_html(
    raw: str,
    *,
    coarse_limit: int = TELEGRAM_HTML_MSG_LIMIT,
) -> list[str]:
    """
    Split raw model text so that each chunk, after model_text_to_telegram_html,
    is at most TELEGRAM_HTML_MSG_LIMIT characters (Telegram sendMessage limit).
    """
    if not raw:
        return []
    out: list[str] = []
    for piece in split_message(raw, limit=coarse_limit):
        _raw_pieces_for_one_coarse_chunk(piece, out)
    return out


def chunk_raw_text_for_telegram(raw: str, limit: int = TELEGRAM_HTML_MSG_LIMIT) -> list[str]:
    """Split raw model text so each HTML-formatted chunk fits Telegram."""
    return raw_chunks_for_telegram_html(raw, coarse_limit=limit)


async def send_reply_html_with_plain_fallback(
    send_coro,
    raw_text: str,
    *,
    coarse_limit: int = TELEGRAM_HTML_MSG_LIMIT,
) -> None:
    """
    For each chunk: send as HTML; on any failure, send the same chunk as plain text.

    send_coro: async (text: str, *, parse_mode: str | None) -> Any
    """
    for chunk in raw_chunks_for_telegram_html(raw_text, coarse_limit=coarse_limit):
        body = model_text_to_telegram_html(chunk)
        try:
            await send_coro(body, parse_mode="HTML")
        except Exception as e:
            logger.debug("Telegram HTML send failed, using plain chunk: %s", e)
            await send_coro(chunk, parse_mode=None)
