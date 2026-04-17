"""
Cloud STT backends for long voice messages: OpenRouter multimodal (input_audio) and Yandex SpeechKit REST.
"""

from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import urlencode

from shared.config import get_settings
from shared.openrouter_http import openrouter_json_headers

logger = logging.getLogger("orchestrator.skills.whisper_remote")


def _openrouter_base_url() -> str:
    return "https://openrouter.ai/api/v1/chat/completions"


async def transcribe_openrouter(
    ogg_bytes: bytes,
    *,
    language: str | None,
    http_client,
) -> str:
    """
    Transcribe via OpenRouter chat/completions with input_audio (base64 + format).

    Uses ``whisper_openrouter_stt_model`` and ``whisper_openrouter_stt_timeout_seconds``.
    """
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY не задан — облачная транскрипция через OpenRouter недоступна"
        )

    model = (settings.whisper_openrouter_stt_model or "").strip()
    if not model:
        raise RuntimeError("WHISPER_OPENROUTER_STT_MODEL не задан")

    lang_hint = (language or settings.whisper_language or "ru").strip()
    user_text = (
        "Transcribe this voice message verbatim. Preserve the original language "
        f"(likely {lang_hint}). Return only the transcript, no preamble."
    )

    b64 = base64.b64encode(ogg_bytes).decode("ascii")
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": b64,
                            "format": "ogg",
                        },
                    },
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 4096,
    }

    timeout = settings.whisper_openrouter_stt_timeout_seconds
    logger.info(
        "OpenRouter STT: model=%s bytes=%s timeout=%ss",
        model,
        len(ogg_bytes),
        timeout,
    )

    response = await http_client.post(
        _openrouter_base_url(),
        headers=openrouter_json_headers(settings),
        json=payload,
        timeout=timeout,
    )

    if response.status_code != 200:
        raise RuntimeError(f"OpenRouter STT HTTP {response.status_code}: {response.text[:500]}")

    data = response.json()
    text = ((data.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("OpenRouter STT вернул пустой текст")
    return text


async def transcribe_yandex(
    ogg_bytes: bytes,
    *,
    language: str | None,
    http_client,
) -> str:
    """
    Yandex SpeechKit synchronous REST: POST raw OggOpus body.

    See https://cloud.yandex.com/en/docs/speechkit/stt/api/request-api
    """
    settings = get_settings()
    api_key = settings.yandex_speech_api_key or settings.yandex_search_key
    folder_id = settings.yandex_speech_folder_id or settings.yandex_folder_id

    if not api_key:
        raise RuntimeError(
            "YANDEX_SPEECH_API_KEY (или YANDEX_SEARCH_KEY) не задан — Yandex STT недоступен"
        )
    if not folder_id:
        raise RuntimeError("YANDEX_SPEECH_FOLDER_ID или YANDEX_FOLDER_ID не задан")

    # ru-RU, en-US, etc.
    lang = language or settings.whisper_language or "ru"
    if len(lang) == 2:
        lang_map = {"ru": "ru-RU", "en": "en-US", "de": "de-DE", "fr": "fr-FR"}
        lang = lang_map.get(lang.lower(), f"{lang.lower()}-{lang.upper()}")

    q = urlencode(
        {
            "folderId": folder_id,
            "lang": lang,
            "format": "oggopus",
            "topic": "general",
        }
    )
    url = f"https://stt.api.cloud.yandex.net/speech/v1/stt:recognize?{q}"

    logger.info("Yandex STT: bytes=%s lang=%s", len(ogg_bytes), lang)

    response = await http_client.post(
        url,
        headers={
            "Authorization": f"Api-Key {api_key}",
            "Content-Type": "application/octet-stream",
        },
        content=ogg_bytes,
        timeout=settings.whisper_yandex_stt_timeout_seconds,
    )

    if response.status_code != 200:
        raise RuntimeError(f"Yandex STT HTTP {response.status_code}: {response.text[:500]}")

    data = response.json()
    if "error" in data:
        err = data.get("error") or data
        raise RuntimeError(f"Yandex STT error: {err}")

    result = (data.get("result") or "").strip()
    if not result:
        raise RuntimeError("Yandex STT вернул пустой результат")
    return result
