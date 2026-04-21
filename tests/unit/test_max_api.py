"""MAX platform-api client helpers."""

from unittest.mock import AsyncMock, patch

import pytest

from shared.max_api import (
    normalize_max_access_token,
    send_max_message,
    send_max_message_markdown_from_model,
)


def test_normalize_max_access_token_strips_bearer() -> None:
    assert normalize_max_access_token("  abc123  ") == "abc123"
    assert normalize_max_access_token("Bearer secret") == "secret"
    assert normalize_max_access_token("bearer secret") == "secret"


def test_normalize_max_access_token_empty() -> None:
    assert normalize_max_access_token("") == ""


@pytest.mark.asyncio
async def test_send_max_message_accepts_chat_id_zero() -> None:
    """chat_id=0 must not be treated as missing (bool(0) is false)."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"message": {"message_id": 1}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("shared.max_api.httpx.AsyncClient", return_value=mock_client):
        await send_max_message(
            api_url="https://platform-api.max.ru",
            token="tok",
            text="hi",
            chat_id=0,
            user_id=None,
        )
    mock_client.post.assert_called()
    call_kw = mock_client.post.call_args
    assert call_kw[1]["params"]["chat_id"] == 0
    assert "user_id" not in call_kw[1]["params"]


@pytest.mark.asyncio
async def test_send_max_message_prefers_chat_id_when_both_given() -> None:
    """Defensive: if both query params slip in, only chat_id is sent."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"message": {"message_id": 1}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("shared.max_api.httpx.AsyncClient", return_value=mock_client):
        await send_max_message(
            api_url="https://platform-api.max.ru",
            token="tok",
            text="hi",
            chat_id=-5,
            user_id=999,
        )
    params = mock_client.post.call_args[1]["params"]
    assert params.get("chat_id") == -5
    assert "user_id" not in params


@pytest.mark.asyncio
async def test_send_max_message_keeps_format_on_continuation_chunks() -> None:
    """Multi-part text must send ``format`` on every chunk (not only the first)."""
    long_text = "a" * (4000 + 1)
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"message": {"message_id": 42}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("shared.max_api.httpx.AsyncClient", return_value=mock_client):
        await send_max_message(
            api_url="https://platform-api.max.ru",
            token="tok",
            text=long_text,
            chat_id=1,
            user_id=None,
            text_format="markdown",
        )
    assert mock_client.post.call_count == 2
    for call in mock_client.post.call_args_list:
        body = call.kwargs.get("json") or (call.args[2] if len(call.args) > 2 else {})
        assert body.get("format") == "markdown"


@pytest.mark.asyncio
async def test_send_max_message_markdown_from_model_falls_back_to_plain() -> None:
    """When formatted send raises, same chunk is retried without ``format``."""
    calls: list[dict] = []

    async def fake_send(*_a, **kw):
        rec = {"text": kw.get("text"), "text_format": kw.get("text_format")}
        calls.append(rec)
        if kw.get("text_format") == "markdown":
            raise RuntimeError("API rejected markdown")
        return "99"

    with patch("shared.max_api.send_max_message", new_callable=AsyncMock, side_effect=fake_send):
        mid = await send_max_message_markdown_from_model(
            api_url="https://platform-api.max.ru",
            token="tok",
            raw_model_text="hello **world**",
            chat_id=1,
            user_id=None,
        )
    assert mid == "99"
    assert len(calls) == 2
    assert calls[0].get("text_format") == "markdown"
    assert calls[1].get("text_format") is None
