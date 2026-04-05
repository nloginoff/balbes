"""
Shared voice pipeline: download Telegram voice/audio → STT → optional LLM correction.

Uses orchestrator skill `whisper_transcribe` (project root on PYTHONPATH).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

logger = logging.getLogger("telegram_app.voice")


async def transcribe_telegram_voice(
    message: Any,
    context: Any,
    *,
    http_client: httpx.AsyncClient,
    chat_model_id: str | None,
    voice_debug: bool = False,
    debug_reply: Callable[[Any, bool, str], Awaitable[None]] | None = None,
) -> str:
    """
    Download voice/audio, run transcribe_voice + correct_transcription.
    Returns corrected text (may be empty on failure).
    """
    from services.orchestrator.skills.whisper_transcribe import (
        correct_transcription,
        transcribe_voice,
    )

    voice = message.voice or message.audio
    if not voice:
        return ""

    duration_sec = getattr(voice, "duration", None)

    async def _dbg(line: str) -> None:
        if debug_reply:
            await debug_reply(message, voice_debug, line)

    await _dbg("старт: скачивание файла из Telegram…")
    t_dl = time.monotonic()
    file = await context.bot.get_file(voice.file_id)
    ogg_bytes = bytes(await file.download_as_bytearray())
    dl_s = time.monotonic() - t_dl
    logger.info("Voice: downloaded %s bytes in %.1fs", len(ogg_bytes), dl_s)
    await _dbg(f"скачано {len(ogg_bytes)} байт за {dl_s:.1f} с")

    await _dbg("STT: распознавание (короткие — локальный Whisper; длинные — API)…")
    t_tr = time.monotonic()
    tr_result = await transcribe_voice(
        ogg_bytes,
        duration_hint_sec=duration_sec,
        http_client=http_client,
    )
    raw_text = tr_result.text or ""
    tr_s = time.monotonic() - t_tr
    logger.info(
        "Voice: transcribe done %s chars in %.1fs (%s)",
        len(raw_text),
        tr_s,
        tr_result.stt_label_ru,
    )
    await _dbg(
        f"voice: {tr_result.stt_label_ru} — готово, {len(raw_text)} символов за {tr_s:.1f} с"
    )

    if not raw_text.strip():
        return ""

    await _dbg("LLM: постобработка расшифровки…")
    t_co = time.monotonic()
    corrected = await correct_transcription(
        raw_text,
        http_client=http_client,
        chat_model_id=chat_model_id,
    )
    co_s = time.monotonic() - t_co
    logger.info("Voice: LLM correction in %.1fs", co_s)
    await _dbg(f"LLM: готово за {co_s:.1f} с")

    return corrected.strip()


async def business_bot_handle_voice(
    message: Any,
    context: Any,
    *,
    http_client: httpx.AsyncClient | None,
    chat_model_id: str | None,
    route_text_callback: Callable[[int, str, Any, Any], Awaitable[None]],
    show_preview: bool = True,
) -> None:
    """
    Voice handler for blogger business bot: transcribe then route like text.
    `route_text_callback(owner_id, text, message, context)` — same as _route_owner_natural_language.
    """
    from shared.telegram_app.text import reply_voice_transcription

    user = message.from_user
    if not user:
        return
    owner_id = user.id

    from telegram.constants import ChatAction

    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.RECORD_VOICE)

    http = http_client or httpx.AsyncClient(timeout=300.0)
    own_http = http_client is None
    try:
        corrected = await transcribe_telegram_voice(
            message,
            context,
            http_client=http,
            chat_model_id=chat_model_id,
            voice_debug=False,
            debug_reply=None,
        )
        if not corrected:
            await message.reply_text("🎤 Не удалось распознать голосовое сообщение")
            return
        if show_preview:
            await reply_voice_transcription(message, corrected)
        await route_text_callback(owner_id, corrected, message, context)
    except ImportError as e:
        logger.warning("voice import failed: %s", e)
        await message.reply_text(
            "Голосовые недоступны: проверьте установку openai-whisper и ffmpeg."
        )
    except Exception as exc:
        logger.exception("business_bot_handle_voice: %s", exc)
        await message.reply_text(f"Ошибка расшифровки: {exc!s:.400}")
    finally:
        if own_http:
            await http.aclose()
