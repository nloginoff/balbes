"""Unit tests for OpenRouter image response parsing (no network)."""

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.agent_tools.registry import ToolDispatcher
from shared.image_generation import (
    decode_data_url,
    extract_images_from_openrouter_message,
    strip_openrouter_prefix,
)


def test_strip_openrouter_prefix():
    assert strip_openrouter_prefix("openrouter/google/x") == "google/x"
    assert strip_openrouter_prefix("google/x") == "google/x"


def test_decode_data_url_png():
    raw = b"\x89PNG\r\n\x1a\n"
    b64 = base64.b64encode(raw).decode("ascii")
    url = f"data:image/png;base64,{b64}"
    out, mime = decode_data_url(url)
    assert out == raw
    assert mime == "image/png"


def test_extract_images_from_message():
    tiny = base64.b64encode(b"fakepng").decode("ascii")
    msg = {
        "content": "Here",
        "images": [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{tiny}"},
            }
        ],
    }
    items = extract_images_from_openrouter_message(msg)
    assert len(items) == 1
    assert items[0][0] == b"fakepng"
    assert items[0][1] == "image/png"


def test_extract_skips_bad_data_url():
    msg = {"images": [{"image_url": {"url": "data:image/png;base64,!!!"}}]}
    items = extract_images_from_openrouter_message(msg)
    assert items == []


@pytest.mark.asyncio
async def test_tool_dispatcher_generate_image_outbound(monkeypatch):
    tiny = base64.b64encode(b"x").decode("ascii")
    resp = MagicMock()
    resp.status_code = 200
    resp.json = lambda: {
        "usage": {"total_tokens": 42},
        "choices": [
            {
                "message": {
                    "content": "Here",
                    "images": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{tiny}"}}
                    ],
                }
            }
        ],
    }
    client = AsyncMock()
    client.post = AsyncMock(return_value=resp)

    monkeypatch.setattr(
        "shared.config.get_settings",
        lambda: SimpleNamespace(
            openrouter_api_key="sk-test",
            openrouter_service_user="svc",
            openrouter_http_referer="https://ex",
            openrouter_app_title="t",
            openrouter_categories=None,
        ),
    )

    td = ToolDispatcher(
        workspace=None, http_client=client, providers_config={}, activity_logger=None
    )
    out = await td._do_generate_image({"prompt": "a cat"}, {"user_id": "user-uuid"})
    assert "OpenRouter" in out
    oa = td.take_outbound_attachments()
    assert len(oa) == 1
    assert oa[0]["kind"] == "image"
    assert oa[0]["mime_type"] == "image/png"
    assert client.post.call_count == 1
