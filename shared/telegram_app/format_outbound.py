"""
Convert model / orchestrator plain text to Telegram HTML (parse_mode=HTML).

Pipeline (prose segments):
1) Optional simple Telegram HTML pairs from the model (<b>, <i>, <pre>, <a>, …) → placeholders
2) Markdown-like: `code`, [text](url), ||spoiler||, ~~strike~~, ***bold italic***, **bold**, __bold__, *italic*, _italic_
3) Block quote: line starts with ">…", or "MD:/HTML: >…", optional "[n] " prefix
4) html.escape the remainder
5) Recursively expand placeholders into Telegram HTML (nested tags and markdown combos)

Fenced ``` blocks become <pre> at the outer level (unchanged).

Outgoing chunks use ``raw_chunks_for_telegram_html``: coarse split prefers ``\\n\\n``, ``\\n``,
spaces, and avoids cutting inside fenced ``` blocks so markdown pairs are not torn across
chunks (which previously led to plain fallback and “only bold/code works”). Then split until
each HTML chunk fits Telegram’s 4096 **UTF-16 code units** limit (not Python ``len()``).

See https://core.telegram.org/bots/api#html-style
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

from telegram.constants import ParseMode
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

# Fenced ``` ... ``` must not be cut in the middle (breaks conversion and often yields BadRequest).
_FENCE_SPAN_RE = re.compile(r"```(?:[a-zA-Z0-9_-]*)\s*\n?[\s\S]*?```", re.MULTILINE)

# Telegram Bot API: sendMessage `text` max length (UTF-16 code units, same basis as entity offsets).
TELEGRAM_HTML_MSG_LIMIT = 4096


def telegram_message_text_units(s: str) -> int:
    """
    Length of ``s`` as Telegram counts it for ``text`` (UTF-16 code units).

    Supplementary-plane characters (e.g. most emoji, ``ord(c) > 0xFFFF``) count as 2;
    BMP characters count as 1. Plain ``len(s)`` can be below 4096 while this exceeds the limit.
    """
    return sum(2 if ord(c) > 0xFFFF else 1 for c in s)


def _split_inside_any_fence(text: str, cut: int) -> bool:
    if cut <= 0 or cut >= len(text):
        return False
    return any(m.start() < cut < m.end() for m in _FENCE_SPAN_RE.finditer(text))


def _move_cut_before_fence(text: str, cut: int) -> int:
    """If cut falls inside a ``` block, move cut to the block start (keep fence in next chunk)."""
    for m in _FENCE_SPAN_RE.finditer(text):
        if m.start() < cut < m.end():
            return max(1, m.start())
    return cut


def split_raw_coarse_for_telegram(text: str, limit: int = TELEGRAM_HTML_MSG_LIMIT) -> list[str]:
    """
    Split raw model text into chunks at most `limit` chars, preferring paragraph/line/space
    boundaries so markdown (`*`, `` ` ``, `||`) is less often torn apart (which caused plain
    fallback chunks without formatting).
    """
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        lim = min(limit, len(rest))
        split_at = lim
        search_hi = lim
        search_lo = max(0, lim - 3500)
        idx = rest.rfind("\n\n", 0, search_hi)
        if idx >= 0:
            split_at = idx + 2
        else:
            idx = rest.rfind("\n", 0, search_hi)
            if idx >= 0:
                split_at = idx + 1
            else:
                idx = rest.rfind(". ", search_lo, search_hi)
                if idx >= 0:
                    split_at = idx + 2
                else:
                    idx = rest.rfind(" ", search_lo, search_hi)
                    if idx >= 0:
                        split_at = idx + 1
        if split_at >= len(rest):
            split_at = lim
        if _split_inside_any_fence(rest, split_at):
            split_at = _move_cut_before_fence(rest, split_at)
        if split_at <= 0 or split_at >= len(rest):
            split_at = lim
        if _split_inside_any_fence(rest, split_at):
            split_at = _move_cut_before_fence(rest, split_at)
        chunks.append(rest[:split_at])
        rest = rest[split_at:].lstrip("\n")
    return chunks


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
            "a_sq",
            re.compile(
                r"<a\s+href='([^']+)'\s*>([^<]*)</a>",
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
    elif kind in ("a", "a_sq"):
        stores.append(("a", m.group(1), m.group(2)))
    elif kind in ("tg_spoiler", "spoiler_alt"):
        stores.append(("tg_spoiler", m.group(1)))
    elif kind == "blockquote":
        stores.append(("blockquote", m.group(1)))
    else:
        tag = m.group(1).lower()
        stores.append(("simple", tag, m.group(2)))

    return segment[:start] + _ph(idx) + segment[end:]


# Blockquote: plain "> …" or labeled "MD: > …" / "HTML: > …" (optional "[n] " prefix).
_BQ_LABELED = re.compile(
    r"^\s*(?:\[\d+\]\s+)?(?:MD|HTML):\s*>\s*(.*)$",
    re.IGNORECASE,
)
_BQ_PLAIN = re.compile(r"^\s*>\s?(.*)$")


def _blockquote_line_payload(line: str) -> str | None:
    """If line opens a blockquote, return inner text after marker; else None."""
    m = _BQ_LABELED.match(line)
    if m:
        return m.group(1)
    m = _BQ_PLAIN.match(line)
    if m:
        return m.group(1)
    return None


def _markdown_blockquotes(segment: str, stores: list[tuple[Any, ...]]) -> str:
    """Lines starting with '>…' or 'MD:/HTML: >…' → blockquote placeholder."""
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
        payload = _blockquote_line_payload(line)
        if payload is not None:
            buf.append(payload)
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

    # Strikethrough ~~text~~ (Discord/GitHub style)
    def _strike_repl(m: re.Match[str]) -> str:
        return push(("strike", m.group(1)))

    t = re.sub(r"~~([^~]+?)~~", _strike_repl, t)

    # Bold + italic ***text*** (must run before ** and single *)
    def _bi_repl(m: re.Match[str]) -> str:
        return push(("bi", m.group(1)))

    t = re.sub(r"\*\*\*([^*]+?)\*\*\*", _bi_repl, t)

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

    def _has_ph(inner: str) -> bool:
        return any(_ph(j) in inner for j in range(len(stores)))

    def render_store(i: int) -> str:
        """Build HTML for stores[i]; resolve nested placeholders recursively."""
        item = stores[i]
        if item[0] == "blockquote":
            inner = item[1]
            inner_h = expand_ph(inner) if _has_ph(inner) else html.escape(inner, quote=False)
            return f"<blockquote>{inner_h}</blockquote>"
        if item[0] == "pre":
            return f"<pre>{html.escape(item[1], quote=False)}</pre>"
        if item[0] == "a":
            url, label = item[1], item[2]
            label_h = expand_ph(label) if _has_ph(label) else html.escape(label, quote=False)
            href = _safe_href(url)
            if href:
                return f'<a href="{html.escape(href, quote=True)}">{label_h}</a>'
            return html.escape(f'<a href="{url}">{label}</a>', quote=False)
        if item[0] == "tg_spoiler":
            inner = item[1]
            inner_h = expand_ph(inner) if _has_ph(inner) else html.escape(inner, quote=False)
            return f"<tg-spoiler>{inner_h}</tg-spoiler>"
        if item[0] == "simple":
            tag, inner_raw = item[1], item[2]
            inner_h = (
                expand_ph(inner_raw) if _has_ph(inner_raw) else html.escape(inner_raw, quote=False)
            )
            if tag in ("b", "strong"):
                return f"<b>{inner_h}</b>"
            if tag in ("i", "em"):
                return f"<i>{inner_h}</i>"
            if tag == "u":
                return f"<u>{inner_h}</u>"
            if tag == "s":
                return f"<s>{inner_h}</s>"
            if tag == "code":
                return f"<code>{inner_h}</code>"
            return inner_h
        if item[0] == "code":
            return f"<code>{html.escape(item[1], quote=False)}</code>"
        if item[0] == "mdlink":
            label, url = item[1], item[2]
            href = _safe_href(url)
            if href:
                return (
                    f'<a href="{html.escape(href, quote=True)}">'
                    f"{html.escape(label, quote=False)}</a>"
                )
            return html.escape(f"[{label}]({url})", quote=False)
        if item[0] == "spoiler":
            inner = item[1]
            inner_h = expand_ph(inner) if _has_ph(inner) else html.escape(inner, quote=False)
            return f"<tg-spoiler>{inner_h}</tg-spoiler>"
        if item[0] == "bi":
            inner = item[1]
            inner_h = expand_ph(inner) if _has_ph(inner) else html.escape(inner, quote=False)
            return f"<b><i>{inner_h}</i></b>"
        if item[0] == "bold":
            inner = item[1]
            inner_h = expand_ph(inner) if _has_ph(inner) else html.escape(inner, quote=False)
            return f"<b>{inner_h}</b>"
        if item[0] == "italic":
            inner = item[1]
            inner_h = expand_ph(inner) if _has_ph(inner) else html.escape(inner, quote=False)
            return f"<i>{inner_h}</i>"
        if item[0] == "strike":
            inner = item[1]
            inner_h = expand_ph(inner) if _has_ph(inner) else html.escape(inner, quote=False)
            return f"<s>{inner_h}</s>"
        return ""

    def expand_ph(fragment: str) -> str:
        """Replace leftmost placeholder repeatedly until none remain."""
        out = fragment
        for _ in range(len(stores) * 3 + 32):
            best_j = -1
            best_pos = len(out) + 1
            for j in range(len(stores)):
                k = _ph(j)
                p = out.find(k)
                if p >= 0 and p < best_pos:
                    best_pos = p
                    best_j = j
            if best_j < 0:
                break
            out = out.replace(_ph(best_j), render_store(best_j), 1)
        return out

    t = expand_ph(t)
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
    converted text can exceed 4096 UTF-16 units and make Telegram reject parse_mode=HTML —
    then callers fell back to plain and users saw no formatting.
    """
    if not piece:
        return
    body = model_text_to_telegram_html(piece)
    if telegram_message_text_units(body) <= TELEGRAM_HTML_MSG_LIMIT:
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
    is at most TELEGRAM_HTML_MSG_LIMIT UTF-16 units (Telegram sendMessage limit).
    """
    if not raw:
        return []
    out: list[str] = []
    for piece in split_raw_coarse_for_telegram(raw, limit=coarse_limit):
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
    For each chunk: send as HTML; on BadRequest (entity parse), retry chunk as plain text.

    send_coro: async (text: str, *, parse_mode: str | None) -> Any
    """
    for chunk in raw_chunks_for_telegram_html(raw_text, coarse_limit=coarse_limit):
        body = model_text_to_telegram_html(chunk)
        try:
            await send_coro(body, parse_mode=ParseMode.HTML)
        except BadRequest as e:
            logger.warning(
                "Telegram rejected HTML entities, sending plain chunk: %s (body_prefix=%r)",
                e,
                body[:320],
            )
            logger.debug("Full HTML body on BadRequest: %s", body)
            await send_coro(chunk, parse_mode=None)
