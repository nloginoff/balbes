"""Shared Telegram text helpers (message length limits, voice preview)."""

from __future__ import annotations

import logging

logger = logging.getLogger("telegram_app.text")

TELEGRAM_MSG_LIMIT = 4096
# Reserve room for «🎤 Услышал (NN/NN):» when splitting transcription chunks
VOICE_HEARD_BODY_LIMIT = 3950

_MD2_ESCAPE_RE = str.maketrans({c: f"\\{c}" for c in r"\_*[]()~`>#+-=|{}.!"})


def escape_md2(text: str) -> str:
    """Escape special characters for MarkdownV2."""
    return str(text).translate(_MD2_ESCAPE_RE)


def split_message(text: str, limit: int = TELEGRAM_MSG_LIMIT) -> list[str]:
    """Split text into chunks of at most `limit` characters, preferring line breaks."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


def split_long_text(text: str, limit: int = TELEGRAM_MSG_LIMIT) -> list[str]:
    """Alias for long plain-text replies (same algorithm as split_message)."""
    return split_message(text, limit=limit)


async def reply_voice_transcription(message, corrected: str) -> None:
    """Send transcribed text; split into several messages if longer than Telegram allows."""
    overhead = len("🎤 _Услышал:_ «»")
    if len(corrected) + overhead <= 4090:
        await message.reply_text(
            f"🎤 _Услышал:_ «{corrected}»",
            parse_mode="Markdown",
        )
        return
    chunks = split_message(corrected, limit=VOICE_HEARD_BODY_LIMIT)
    n = len(chunks)
    for i, chunk in enumerate(chunks):
        header = f"🎤 Услышал ({i + 1}/{n}):\n\n" if n > 1 else "🎤 Услышал:\n\n"
        await message.reply_text(header + chunk)
