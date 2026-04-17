"""
Unit tests for hybrid voice STT routing (no network, no whisper/ffmpeg).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


class _Settings:
    whisper_local_max_duration_seconds = 30
    whisper_remote_backend = "openrouter"
    whisper_openrouter_stt_timeout_seconds = 60.0
    whisper_yandex_stt_timeout_seconds = 60.0
    whisper_language = "ru"
    openrouter_api_key = "k"
    openrouter_service_user = "balbes-service"
    whisper_openrouter_stt_model = "test/audio-model"
    yandex_speech_api_key = None
    yandex_search_key = "yk"
    yandex_speech_folder_id = None
    yandex_folder_id = "b1gxxx"


def test_use_local_whisper_for_duration(monkeypatch):
    from skills import whisper_transcribe as wt

    def _gs():
        s = MagicMock()
        s.whisper_local_max_duration_seconds = 30
        return s

    monkeypatch.setattr(wt, "get_settings", _gs)

    assert wt.use_local_whisper_for_duration(None) is False
    assert wt.use_local_whisper_for_duration(30) is True
    assert wt.use_local_whisper_for_duration(31) is False
    assert wt.use_local_whisper_for_duration(5) is True


@pytest.mark.asyncio
async def test_transcribe_voice_remote_branch(monkeypatch):
    from skills import whisper_transcribe as wt

    monkeypatch.setattr(wt, "use_local_whisper_for_duration", lambda _d: False)

    async def _remote(ogg_bytes, language, http_client, *, openrouter_user_end_id=None):
        assert ogg_bytes == b"ogg"
        return "remote transcript", "OpenRouter STT"

    monkeypatch.setattr(wt, "_transcribe_remote_stt", _remote)

    client = MagicMock()
    r = await wt.transcribe_voice(b"ogg", duration_hint_sec=300, http_client=client)
    assert r.text == "remote transcript"
    assert r.stt_label_ru == "OpenRouter STT"


@pytest.mark.asyncio
async def test_transcribe_openrouter_parses_response(monkeypatch):
    from skills import whisper_remote_stt as remote

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "  hello from api  "}}]}

    client = AsyncMock()
    client.post = AsyncMock(return_value=_Resp())

    monkeypatch.setattr(remote, "get_settings", lambda: _Settings())

    text = await remote.transcribe_openrouter(b"\x00\x01", language="ru", http_client=client)
    assert text == "hello from api"
    assert client.post.called


@pytest.mark.asyncio
async def test_transcribe_yandex_parses_response(monkeypatch):
    from skills import whisper_remote_stt as remote

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"result": "привет"}

    client = AsyncMock()
    client.post = AsyncMock(return_value=_Resp())

    monkeypatch.setattr(remote, "get_settings", lambda: _Settings())

    text = await remote.transcribe_yandex(b"\xff", language="ru", http_client=client)
    assert text == "привет"


@pytest.mark.asyncio
async def test_transcribe_remote_fallback_order(monkeypatch):
    from skills import whisper_remote_stt as wrm
    from skills import whisper_transcribe as wt

    calls: list[str] = []

    async def fail_or(*a, **k):
        calls.append("or")
        raise RuntimeError("boom")

    async def ok_ya(*a, **k):
        calls.append("ya")
        return "yandex ok"

    monkeypatch.setattr(wrm, "transcribe_openrouter", fail_or)
    monkeypatch.setattr(wrm, "transcribe_yandex", ok_ya)

    class _S:
        whisper_remote_backend = "openrouter_then_yandex"

    monkeypatch.setattr(wt, "get_settings", lambda: _S())

    text, label = await wt._transcribe_remote_stt(b"data", "ru", AsyncMock())
    assert text == "yandex ok"
    assert "Yandex" in label and "fallback" in label
    assert calls == ["or", "ya"]
