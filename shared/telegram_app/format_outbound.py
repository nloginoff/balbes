"""
Convert model / orchestrator plain text to Telegram HTML (parse_mode=HTML).

Pipeline (prose segments):
1) Optional simple Telegram HTML pairs from the model (<b>, <i>, <pre>, <a>, …) → placeholders
2) Markdown-like: `code`, [text](url), ||spoiler||, **bold**, __bold__, *italic*, _italic_
3) Block quote lines starting with "> "
4) html.escape the remainder
5) Substitute placeholders with escaped inner text inside allowed tags

Fenced ``` blocks become <pre> at the outer level (unchanged).

Outgoing chunks use ``raw_chunks_for_telegram_html``: HTML can be longer than raw text
(entities, tags), so we split until each chunk fits the 4096-character Telegram limit.

See https://core.telegram.org/bots/api#html-style
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

from shared.telegram_app.text import split_message

logger = logging.getLogger(__name__)

# Telegram Bot API: text after entity processing, max length (Unicode codepoints).
TELEGRAM_HTML_MSG_LIMIT = 4096

# Placeholders must survive html.escape (ASCII controls are unchanged).


def _ph(i: int) -> str:
    return f"\x01PH{i:05d}\x01"


def _safe_href(url: str) -> str | None:
    u = url.strip()
    if u.startswith(("http://", "https://")):
        return u
    if u.startswith("tg://") or u.startswith("mailto:"):
        return u
    return None


def _leftmost_html_extract(segment: str, stores: list[tuple[Any, ...]]) -> str:
    """Replace leftmost allowed simple HTML fragment with a placeholder."""
    patterns: list[tuple[str, re.Pattern[str]]] = [
        ("pre", re.compile(r"<pre>([\s\S]*?)</pre>", re.IGNORECASE)),
        (
            "a",
            re.compile(
                r'<a\s+href="([^"]+)"\s*>([^<]*)</a>',
                re.IGNORECASE,
            ),
        ),
        (
            "tg_spoiler",
            re.compile(r"<tg-spoiler>([^<]*)</tg-spoiler>", re.IGNORECASE),
        ),
        (
            "spoiler_alt",
            re.compile(r"<spoiler>([^<]*)</spoiler>", re.IGNORECASE),
        ),
        (
            "blockquote",
            re.compile(r"<blockquote>([\s\S]*?)</blockquote>", re.IGNORECASE),
        ),
        (
            "simple",
            re.compile(
                r"<(b|strong|i|em|u|s|code)\s*>([^<]*)</\1\s*>",
                re.IGNORECASE,
            ),
        ),
    ]

    best: tuple[int, int, str, re.Match[str]] | None = None
    for kind, cre in patterns:
        m = cre.search(segment)
        if not m:
            continue
        if best is None or m.start() < best[0]:
            best = (m.start(), m.end(), kind, m)

    if best is None:
        return segment

    start, end, kind, m = best
    idx = len(stores)
    if kind == "pre":
        stores.append(("pre", m.group(1)))
    elif kind == "a":
        stores.append(("a", m.group(1), m.group(2)))
    elif kind in ("tg_spoiler", "spoiler_alt"):
        stores.append(("tg_spoiler", m.group(1)))
    elif kind == "blockquote":
        stores.append(("blockquote", m.group(1)))
    else:
        tag = m.group(1).lower()
        stores.append(("simple", tag, m.group(2)))

    return segment[:start] + _ph(idx) + segment[end:]


def _markdown_blockquotes(segment: str, stores: list[tuple[Any, ...]]) -> str:
    """Lines starting with '> ' or '>' → blockquote placeholder."""
    lines = segment.split("\n")
    out: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        text = "\n".join(buf)
        idx = len(stores)
        stores.append(("blockquote", text))
        buf = []
        out.append(_ph(idx))

    for line in lines:
        if line.strip() == "":
            flush()
            out.append("")
            continue
        if line.startswith("> "):
            buf.append(line[2:])
        elif line.startswith(">"):
            buf.append(line[1:].lstrip())
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out)


def _prose_to_telegram_html(segment: str) -> str:
    """Escape and apply markdown-lite + simple HTML pass-through (no ``` fences)."""
    if not segment:
        return ""

    stores: list[tuple[Any, ...]] = []

    def push(item: tuple[Any, ...]) -> str:
        stores.append(item)
        return _ph(len(stores) - 1)

    t = segment
    t = _markdown_blockquotes(t, stores)
    # Model-supplied HTML (same tags Telegram accepts)
    prev = None
    while prev != t:
        prev = t
        t = _leftmost_html_extract(t, stores)

    # Markdown headings ### Title → bold line (no # in output)
    def _heading_repl(m: re.Match[str]) -> str:
        return push(("bold", m.group(1).strip()))

    t = re.sub(r"^#{1,6}\s+(.+)$", _heading_repl, t, flags=re.MULTILINE)

    # Inline `code` first (protect * and _ inside)
    def _code_repl(m: re.Match[str]) -> str:
        return push(("code", m.group(1)))

    t = re.sub(r"`([^`]+)`", _code_repl, t)

    # Markdown [text](url)
    def _link_repl(m: re.Match[str]) -> str:
        label, url = m.group(1), m.group(2).strip()
        if _safe_href(url):
            return push(("mdlink", label, url))
        return m.group(0)

    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link_repl, t)

    # Telegram-style ||spoiler||
    def _spoil_repl(m: re.Match[str]) -> str:
        return push(("spoiler", m.group(1)))

    t = re.sub(r"\|\|([^|]+)\|\|", _spoil_repl, t)

    # Bold ** and __
    def _bold_star(m: re.Match[str]) -> str:
        return push(("bold", m.group(1)))

    t = re.sub(r"\*\*([^*]+?)\*\*", _bold_star, t)

    def _bold_us(m: re.Match[str]) -> str:
        return push(("bold", m.group(1)))

    t = re.sub(r"__([^_]+?)__", _bold_us, t)

    # Italic *word* (not **)
    def _ital_star(m: re.Match[str]) -> str:
        return push(("italic", m.group(1)))

    t = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", _ital_star, t)

    # Italic _word_ (not __)
    def _ital_us(m: re.Match[str]) -> str:
        return push(("italic", m.group(1)))

    t = re.sub(r"(?<!_)_([^_\n]+?)_(?!_)", _ital_us, t)

    t = html.escape(t, quote=False)

    # Substitute in order
    for i, item in enumerate(stores):
        key = _ph(i)
        if item[0] == "blockquote":
            inner = html.escape(item[1], quote=False)
            repl = f"<blockquote>{inner}</blockquote>"
        elif item[0] == "pre":
            repl = f"<pre>{html.escape(item[1], quote=False)}</pre>"
        elif item[0] == "a":
            url, label = item[1], item[2]
            href = _safe_href(url)
            if href:
                repl = (
                    f'<a href="{html.escape(href, quote=True)}">'
                    f"{html.escape(label, quote=False)}</a>"
                )
            else:
                repl = html.escape(f'<a href="{url}">{label}</a>', quote=False)
        elif item[0] == "tg_spoiler":
            repl = f"<tg-spoiler>{html.escape(item[1], quote=False)}</tg-spoiler>"
        elif item[0] == "simple":
            tag, inner = item[1], item[2]
            esc = html.escape(inner, quote=False)
            if tag in ("b", "strong"):
                repl = f"<b>{esc}</b>"
            elif tag in ("i", "em"):
                repl = f"<i>{esc}</i>"
            elif tag == "u":
                repl = f"<u>{esc}</u>"
            elif tag == "s":
                repl = f"<s>{esc}</s>"
            elif tag == "code":
                repl = f"<code>{esc}</code>"
            else:
                repl = esc
        elif item[0] == "code":
            repl = f"<code>{html.escape(item[1], quote=False)}</code>"
        elif item[0] == "mdlink":
            label, url = item[1], item[2]
            href = _safe_href(url)
            if href:
                repl = (
                    f'<a href="{html.escape(href, quote=True)}">'
                    f"{html.escape(label, quote=False)}</a>"
                )
            else:
                repl = html.escape(f"[{label}]({url})", quote=False)
        elif item[0] == "spoiler":
            repl = f"<tg-spoiler>{html.escape(item[1], quote=False)}</tg-spoiler>"
        elif item[0] == "bold":
            repl = f"<b>{html.escape(item[1], quote=False)}</b>"
        elif item[0] == "italic":
            repl = f"<i>{html.escape(item[1], quote=False)}</i>"
        else:
            repl = ""

        t = t.replace(key, repl)

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
