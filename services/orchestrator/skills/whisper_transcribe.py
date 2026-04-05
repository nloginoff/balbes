"""
Voice transcription using the official OpenAI Whisper implementation (openai-whisper / PyTorch).

Pipeline:
  1. Receive OGG/OPUS bytes from Telegram
  2. Convert to WAV via ffmpeg
  3. Transcribe with whisper.load_model + model.transcribe (beam search, quality-oriented defaults)
  4. Optional LLM correction via OpenRouter (short/medium text only)

Slower than faster-whisper; better reference decoding. For cloud STT (OpenRouter/Yandex Speech),
see future backend switch in orchestrator config.

The model is loaded once and reused (singleton).
"""

import asyncio
import contextlib
import logging
import tempfile
from pathlib import Path

from shared.config import get_settings

logger = logging.getLogger("orchestrator.skills.whisper")
settings = get_settings()

_whisper_model = None
_model_lock = asyncio.Lock()


def _fp16_for_decode() -> bool:
    if settings.whisper_fp16 is not None:
        return settings.whisper_fp16
    return settings.whisper_device.lower() == "cuda"


async def get_whisper_model():
    """Lazy-load and return the singleton Whisper model (openai-whisper)."""
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

        def _load():
            logger.info(
                "Loading OpenAI Whisper model %r on %s (fp16 decode: %s)...",
                settings.whisper_model,
                settings.whisper_device,
                _fp16_for_decode(),
            )
            return whisper.load_model(settings.whisper_model, device=settings.whisper_device)

        loop = asyncio.get_event_loop()
        _whisper_model = await loop.run_in_executor(None, _load)
        logger.info("Whisper model loaded successfully")
    return _whisper_model


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
) -> str:
    """
    Transcribe a voice message.

    Args:
        ogg_bytes: Raw OGG/OPUS audio bytes from Telegram
        language: Language code (default from settings.whisper_language); None = auto-detect
        duration_hint_sec: Telegram-reported duration (seconds), used to scale ffmpeg timeout

    Returns:
        Transcribed text string
    """
    lang = language if language is not None else settings.whisper_language
    wav_path: Path | None = None

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
        return text

    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install it: sudo apt install ffmpeg")
    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)
        raise
    finally:
        if wav_path:
            wav_path.unlink(missing_ok=True)


async def correct_transcription(text: str, http_client=None) -> str:
    """
    Fix common speech recognition errors using a cheap LLM.

    Args:
        text: Raw transcription text
        http_client: Optional httpx.AsyncClient

    Returns:
        Corrected text, or original if correction fails
    """
    if not text or not settings.openrouter_api_key:
        return text

    if len(text) > 8000:
        logger.info("Skipping LLM correction for long transcription (%s chars)", len(text))
        return text

    import httpx as _httpx

    own_client = http_client is None
    client = http_client or _httpx.AsyncClient(timeout=20.0)

    try:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openrouter/meta-llama/llama-3.1-8b-instruct:free",
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
                "max_tokens": 500,
            },
        )
        if response.status_code == 200:
            corrected = (
                response.json().get("choices", [{}])[0].get("message", {}).get("content") or text
            ).strip()
            return corrected if corrected else text
    except Exception as e:
        logger.warning(f"Transcription correction failed: {e}")
    finally:
        if own_client:
            await client.aclose()

    return text
