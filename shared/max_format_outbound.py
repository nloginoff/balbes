"""
Convert model / orchestrator text to MAX Messenger markdown (format=markdown).

Strategy: reuse the Telegram HTML pipeline ([`model_text_to_telegram_html`][shared.telegram_app.format_outbound])
then map a safe subset of tags to MAX markdown per https://dev.max.ru/docs-api (Markdown row).

Limits: POST ``text`` up to 4000 characters (``len``, code units not documented for MAX).
Chunking mirrors coarse split from Telegram so fenced ``` blocks are not torn apart.

Spoilers: Telegram ``<tg-spoiler>`` has no documented MAX equivalent — inner text is emitted plain.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from shared.telegram_app.format_outbound import (
    _move_cut_before_fence,
    _split_inside_any_fence,
    model_text_to_telegram_html,
    split_raw_coarse_for_telegram,
)

# Same as shared.max_api.MAX_TEXT_LIMIT — keep in sync.
MAX_MARKDOWN_MSG_LIMIT = 4000


def model_text_to_max_markdown(text: str) -> str:
    """Full pipeline: model markdown-lite / fences → Telegram HTML → MAX markdown."""
    if not text:
        return ""
    html = model_text_to_telegram_html(text)
    return telegram_html_to_max_markdown(html)


def telegram_html_to_max_markdown(html: str) -> str:
    """Map Telegram-style HTML from our converter into MAX markdown syntax."""
    if not html:
        return ""
    # Blockquotes may contain nested inline tags — convert inner fragment, then prefix lines.
    out: list[str] = []
    pos = 0
    for m in re.finditer(r"<blockquote>([\s\S]*?)</blockquote>", html, re.IGNORECASE):
        if m.start() > pos:
            out.append(_html_fragment_to_max_md(html[pos : m.start()]))
        inner_md = telegram_html_to_max_markdown(m.group(1)).strip()
        for line in inner_md.split("\n"):
            out.append("> " + line + "\n")
        pos = m.end()
    if pos < len(html):
        out.append(_html_fragment_to_max_md(html[pos:]))
    return "".join(out).strip()


def _html_fragment_to_max_md(fragment: str) -> str:
    if not fragment.strip():
        return ""
    conv = _TelegramHtmlToMaxMarkdown()
    conv.feed(fragment)
    conv.close()
    return conv.flush_result()


def max_markdown_to_plain(text: str) -> str:
    """Strip markdown so a failed formatted send can fall back to readable plain text."""
    if not text:
        return ""
    t = text
    t = re.sub(r"<tg-spoiler>|</tg-spoiler>", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", t)
    t = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", t)
    t = re.sub(r"~~([^~]+)~~", r"\1", t)
    t = re.sub(r"\+\+([^+]+)\+\+", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"^>\s?", "", t, flags=re.MULTILINE)
    t = re.sub(r"^```[^\n]*\n|```$", "", t, flags=re.MULTILINE)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()[:MAX_MARKDOWN_MSG_LIMIT]


class _TelegramHtmlToMaxMarkdown(HTMLParser):
    """Stateful conversion; assumes well-formed HTML from our Telegram converter."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._pre = 0
        self._a_href: str | None = None
        self._a_parts: list[str] = []
        self._stack: list[str] = []

    def flush_result(self) -> str:
        s = "".join(self._chunks)
        s = re.sub(r"\n{4,}", "\n\n\n", s)
        return s.strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        ad = {k.lower(): v or "" for k, v in attrs}
        if self._pre > 0:
            return
        if t == "br":
            self._chunks.append("\n")
            return
        if t == "pre":
            self._pre = 1
            self._chunks.append("```\n")
            return
        if t == "tg-spoiler":
            self._stack.append("tg-spoiler")
            return
        if t == "a":
            self._a_href = ad.get("href", "")
            self._a_parts = []
            self._stack.append("a")
            return
        self._stack.append(t)
        if t in ("b", "strong"):
            self._chunks.append("**")
        elif t in ("i", "em"):
            self._chunks.append("*")
        elif t == "u":
            self._chunks.append("++")
        elif t == "s":
            self._chunks.append("~~")
        elif t == "code":
            self._chunks.append("`")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "pre" and self._pre:
            self._pre = 0
            self._chunks.append("\n```")
            return
        if t == "tg-spoiler" and self._stack and self._stack[-1] == "tg-spoiler":
            self._stack.pop()
            return
        if t == "a" and self._stack and self._stack[-1] == "a":
            self._stack.pop()
            label = "".join(self._a_parts)
            href = self._a_href or ""
            esc = label.replace("\\", "\\\\").replace("]", "\\]")
            self._chunks.append(f"[{esc}]({href})")
            self._a_href = None
            self._a_parts = []
            return
        if not self._stack:
            return
        top = self._stack.pop()
        if top != t:
            return
        if t in ("b", "strong"):
            self._chunks.append("**")
        elif t in ("i", "em"):
            self._chunks.append("*")
        elif t == "u":
            self._chunks.append("++")
        elif t == "s":
            self._chunks.append("~~")
        elif t == "code":
            self._chunks.append("`")

    def handle_data(self, data: str) -> None:
        if self._pre:
            self._chunks.append(data)
            return
        if self._stack and self._stack[-1] == "a":
            self._a_parts.append(data)
            return
        self._chunks.append(data)


def _split_raw_near_middle_max(segment: str) -> int:
    n = len(segment)
    if n < 2:
        return n // 2 or 1
    mid = n // 2
    span = max(n // 4, 40)
    lo = max(1, mid - span)
    hi = min(n - 1, mid + span)
    split_at = mid
    for sep in ("\n\n", "\n"):
        i = segment.rfind(sep, lo, hi + 1)
        if i != -1:
            j = i + len(sep)
            if 0 < j < n:
                split_at = j
                break
    else:
        sp = segment.rfind(" ", lo, hi + 1)
        if sp != -1:
            j = sp + 1
            if 0 < j < n:
                split_at = j
    if _split_inside_any_fence(segment, split_at):
        split_at = _move_cut_before_fence(segment, split_at)
    if split_at <= 0 or split_at >= len(segment):
        split_at = mid
    if _split_inside_any_fence(segment, split_at):
        split_at = _move_cut_before_fence(segment, split_at)
    return split_at


def _raw_pieces_for_max_chunk(piece: str, out: list[str]) -> None:
    if not piece:
        return
    body = model_text_to_max_markdown(piece)
    if len(body) <= MAX_MARKDOWN_MSG_LIMIT:
        out.append(piece)
        return
    if len(piece) <= 1:
        out.append(piece)
        return
    cut = _split_raw_near_middle_max(piece)
    if cut <= 0 or cut >= len(piece):
        cut = len(piece) // 2
    _raw_pieces_for_max_chunk(piece[:cut], out)
    _raw_pieces_for_max_chunk(piece[cut:], out)


def raw_chunks_for_max_markdown(raw: str, coarse_limit: int = MAX_MARKDOWN_MSG_LIMIT) -> list[str]:
    """
    Split raw model text so each chunk, after ``model_text_to_max_markdown``,
    is at most MAX_MARKDOWN_MSG_LIMIT characters.
    """
    if not raw:
        return []
    out: list[str] = []
    for coarse in split_raw_coarse_for_telegram(raw, limit=coarse_limit):
        _raw_pieces_for_max_chunk(coarse, out)
    return out
