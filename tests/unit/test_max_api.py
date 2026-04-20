"""MAX platform-api client helpers."""

from unittest.mock import AsyncMock, patch

import pytest

from shared.max_api import normalize_max_access_token, send_max_message


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
