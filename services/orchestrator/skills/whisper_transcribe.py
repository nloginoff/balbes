"""
Voice transcription using the official OpenAI Whisper implementation (openai-whisper / PyTorch).

Short voice (Telegram duration ≤ ``whisper_local_max_duration_seconds``): local ``whisper_local_model``
(default medium). Longer or unknown duration: cloud STT via OpenRouter multimodal audio and/or
Yandex SpeechKit (``whisper_remote_backend``).

Pipeline (local):
  1. Receive OGG/OPUS bytes from Telegram
  2. Convert to WAV via ffmpeg
  3. Transcribe with whisper.load_model + model.transcribe (beam search, quality-oriented defaults)
  4. Optional LLM correction via OpenRouter: chat's active model first, then fallback (cheap paid)

The local model is loaded once and reused (singleton).
"""

import asyncio
import contextlib
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from shared.config import get_settings
from shared.openrouter_http import openrouter_json_headers

logger = logging.getLogger("orchestrator.skills.whisper")
settings = get_settings()

_whisper_model = None
_model_lock = asyncio.Lock()


@dataclass(frozen=True)
class VoiceTranscribeResult:
    """Raw STT output and a Russian label for Telegram debug lines."""

    text: str
    stt_label_ru: str


def _fp16_for_decode() -> bool:
    if settings.whisper_fp16 is not None:
        return settings.whisper_fp16
    return settings.whisper_device.lower() == "cuda"


def use_local_whisper_for_duration(duration_hint_sec: int | None) -> bool:
    """
    Use local Whisper only when Telegram reported duration is known and within the threshold.
    Unknown duration is treated as long → cloud STT.
    """
    s = get_settings()
    if duration_hint_sec is None:
        return False
    return duration_hint_sec <= s.whisper_local_max_duration_seconds


async def get_whisper_model():
    """Lazy-load and return the singleton Whisper model (openai-whisper) for the local path."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    async with _model_lock:
        if _whisper_model is not None:
            return _whisper_model

        try:
            import whisper
        except ImportError:
            logger.error("openai-whisper not installed. Run: pip install openai-whisper")
            raise

        s = get_settings()
        model_id = s.whisper_local_model

        def _load():
            logger.info(
                "Loading OpenAI Whisper model %r on %s (fp16 decode: %s)...",
                model_id,
                s.whisper_device,
                _fp16_for_decode(),
            )
            return whisper.load_model(model_id, device=s.whisper_device)

        loop = asyncio.get_event_loop()
        _whisper_model = await loop.run_in_executor(None, _load)
        logger.info("Whisper model loaded successfully")
    return _whisper_model


async def _transcribe_remote_stt(
    ogg_bytes: bytes,
    language: str | None,
    http_client,
) -> tuple[str, str]:
    """Cloud STT; returns (text, Russian debug label)."""
    from skills.whisper_remote_stt import transcribe_openrouter, transcribe_yandex

    s = get_settings()
    mode = s.whisper_remote_backend

    if mode == "openrouter":
        text = await transcribe_openrouter(ogg_bytes, language=language, http_client=http_client)
        return text, "OpenRouter STT"
    if mode == "yandex":
        text = await transcribe_yandex(ogg_bytes, language=language, http_client=http_client)
        return text, "Yandex STT"

    try:
        text = await transcribe_openrouter(ogg_bytes, language=language, http_client=http_client)
        return text, "OpenRouter STT"
    except Exception as e:
        logger.warning("OpenRouter STT failed, falling back to Yandex: %s", e)
        text = await transcribe_yandex(ogg_bytes, language=language, http_client=http_client)
        return text, "Yandex STT (fallback после OpenRouter)"


def _ffmpeg_timeout_seconds(ogg_bytes: bytes, duration_hint_sec: int | None) -> float:
    """
    Long voice messages need more than a fixed short timeout: ffmpeg can run
    many seconds on large OPUS files or slow disks.
    """
    if duration_hint_sec is not None and duration_hint_sec > 0:
        return float(min(900, max(60.0, duration_hint_sec * 4.0)))
    size = len(ogg_bytes)
    return float(min(900, max(90.0, size / 1500.0)))


async def _ogg_to_wav(ogg_bytes: bytes, duration_hint_sec: int | None) -> Path:
    """Convert OGG/OPUS bytes to a WAV temp file using ffmpeg."""
    timeout_sec = _ffmpeg_timeout_seconds(ogg_bytes, duration_hint_sec)
    logger.debug(
        "ffmpeg ogg→wav: %s bytes, duration_hint=%s, timeout=%.0fs",
        len(ogg_bytes),
        duration_hint_sec,
        timeout_sec,
    )

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_file:
        ogg_file.write(ogg_bytes)
        ogg_path = Path(ogg_file.name)

    wav_path = ogg_path.with_suffix(".wav")

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i",
        str(ogg_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(wav_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except TimeoutError as e:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        raise RuntimeError(
            f"Конвертация аудио превысила {timeout_sec:.0f} с "
            "(очень длинное сообщение или перегрузка диска/CPU). Попробуйте короче или повторите позже."
        ) from e

    ogg_path.unlink(missing_ok=True)

    if not wav_path.exists():
        raise RuntimeError("ffmpeg failed to convert audio file")

    return wav_path


def _transcribe_sync(model, wav_path: str, language: str | None) -> tuple[str, str | None]:
    """Run Whisper transcribe in thread pool; returns (text, detected_language or None)."""
    fp16 = _fp16_for_decode()
    kwargs: dict = {
        "verbose": False,
        "fp16": fp16,
        "beam_size": settings.whisper_beam_size,
        "best_of": settings.whisper_best_of,
        "patience": settings.whisper_patience,
        "condition_on_previous_text": True,
    }
    if language:
        kwargs["language"] = language

    result = model.transcribe(wav_path, **kwargs)
    text = (result.get("text") or "").strip()
    info_lang = result.get("language")
    return text, info_lang


async def transcribe_voice(
    ogg_bytes: bytes,
    language: str | None = None,
    duration_hint_sec: int | None = None,
    *,
    http_client=None,
) -> VoiceTranscribeResult:
    """
    Transcribe a voice message (local Whisper for short audio, cloud STT otherwise).

    Args:
        ogg_bytes: Raw OGG/OPUS audio bytes from Telegram
        language: Language code (default from settings.whisper_language); None = auto-detect
        duration_hint_sec: Telegram-reported duration (seconds); routing + ffmpeg timeout
        http_client: ``httpx.AsyncClient`` for cloud STT (required when not using local path)

    Returns:
        VoiceTranscribeResult with text and a Russian label for debug UI
    """
    import httpx as _httpx

    s = get_settings()
    lang = language if language is not None else s.whisper_language
    wav_path: Path | None = None

    if not use_local_whisper_for_duration(duration_hint_sec):
        logger.info(
            "Voice routing: cloud STT (duration_hint=%s, local_max=%ss, mode=%s)",
            duration_hint_sec,
            s.whisper_local_max_duration_seconds,
            s.whisper_remote_backend,
        )
        own_client = http_client is None
        client = http_client or _httpx.AsyncClient(
            timeout=max(
                s.whisper_openrouter_stt_timeout_seconds,
                s.whisper_yandex_stt_timeout_seconds,
            )
        )
        try:
            text, label = await _transcribe_remote_stt(ogg_bytes, lang, client)
            logger.info("Cloud transcription done: %s chars, label=%s", len(text), label)
            return VoiceTranscribeResult(text=text, stt_label_ru=label)
        finally:
            if own_client:
                await client.aclose()

    try:
        model = await get_whisper_model()

        wav_path = await _ogg_to_wav(ogg_bytes, duration_hint_sec)
        logger.debug("Transcribing WAV: %s, language=%s", wav_path, lang)

        path_str = str(wav_path)
        loop = asyncio.get_event_loop()
        text, info_lang = await loop.run_in_executor(
            None,
            lambda: _transcribe_sync(model, path_str, lang),
        )

        logger.info(
            "Transcription done: %s chars, lang=%s",
            len(text),
            info_lang or lang or "auto",
        )
        local_label = f"локально ({s.whisper_local_model})"
        return VoiceTranscribeResult(text=text, stt_label_ru=local_label)

    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install it: sudo apt install ffmpeg")
    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)
        raise
    finally:
        if wav_path:
            wav_path.unlink(missing_ok=True)


def _correction_models_order(chat_model_id: str | None) -> list[str]:
    """Primary = chat model; then fallback (cheap paid). De-dupe."""
    out: list[str] = []
    if chat_model_id and chat_model_id.strip():
        out.append(chat_model_id.strip())
    fb = (settings.whisper_correction_fallback_model or "").strip()
    if fb and fb not in out:
        out.append(fb)
    return out


async def correct_transcription(
    text: str,
    http_client=None,
    *,
    chat_model_id: str | None = None,
) -> str:
    """
    Fix common speech recognition errors via OpenRouter.

    Tries the chat's active model first, then ``whisper_correction_fallback_model``
    (default: MiniMax M2.5 paid, not :free).

    Args:
        text: Raw transcription text
        http_client: Optional httpx.AsyncClient
        chat_model_id: Current chat model from memory (e.g. openrouter/...)

    Returns:
        Corrected text, or original if all attempts fail
    """
    if not text or not settings.openrouter_api_key:
        return text

    if len(text) > 8000:
        logger.info("Skipping LLM correction for long transcription (%s chars)", len(text))
        return text

    models = _correction_models_order(chat_model_id)
    if not models:
        logger.warning("No correction models configured; skipping LLM correction")
        return text

    import httpx as _httpx

    own_client = http_client is None
    client = http_client or _httpx.AsyncClient(timeout=settings.whisper_correction_timeout_seconds)

    timeout = settings.whisper_correction_timeout_seconds
    payload_base = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a transcription corrector. Fix spelling errors, "
                    "punctuation, and speech recognition mistakes in the text. "
                    "Return ONLY the corrected text, nothing else. "
                    "Preserve the original language."
                ),
            },
            {
                "role": "user",
                "content": f"Correct this transcription:\n{text}",
            },
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
    }

    last_error: str | None = None
    try:
        for attempt, model_id in enumerate(models):
            try:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=openrouter_json_headers(settings),
                    json={**payload_base, "model": model_id},
                    timeout=timeout,
                )
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "Transcription correction request failed (model=%s): %s",
                    model_id,
                    e,
                )
                continue

            if response.status_code == 200:
                corrected = (
                    response.json().get("choices", [{}])[0].get("message", {}).get("content")
                    or text
                ).strip()
                if corrected:
                    if attempt > 0:
                        logger.info(
                            "Transcription correction used fallback model %s (chat model failed)",
                            model_id,
                        )
                    else:
                        logger.info("Transcription correction used chat model %s", model_id)
                    return corrected
                last_error = "empty content"
            else:
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.warning(
                    "Transcription correction bad response (model=%s): %s",
                    model_id,
                    last_error,
                )

        if last_error:
            logger.warning(
                "Transcription correction gave up after %s models: %s", len(models), last_error
            )
    except Exception as e:
        logger.warning(f"Transcription correction failed: {e}")
    finally:
        if own_client:
            await client.aclose()

    return text
