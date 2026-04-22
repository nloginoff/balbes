"""Unit tests for OpenRouter image response parsing (no network)."""

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.agent_tools.registry import ToolDispatcher
from shared.image_gen_models import (
    default_image_gen_tier,
    modalities_for_image_gen_model_id,
    resolve_image_gen_model_id,
)
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


def test_resolve_image_gen_model_id_from_fake_yaml(monkeypatch):
    fake = {
        "image_generation_models": {
            "default_tier": "cheap",
            "tiers": [
                {
                    "tier": "cheap",
                    "id": "openrouter/google/cheap-m",
                    "display_name": "C",
                },
                {
                    "tier": "premium",
                    "id": "openrouter/google/prem-m",
                    "display_name": "P",
                },
            ],
        }
    }
    monkeypatch.setattr("shared.image_gen_models.get_providers_config", lambda: fake)
    assert default_image_gen_tier() == "cheap"
    assert resolve_image_gen_model_id("premium") == "openrouter/google/prem-m"
    assert resolve_image_gen_model_id(None) == "openrouter/google/cheap-m"


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


@pytest.mark.asyncio
async def test_tool_dispatcher_generate_image_uses_tier_from_context(monkeypatch):
    tiny = base64.b64encode(b"x").decode("ascii")
    resp = MagicMock()
    resp.status_code = 200
    resp.json = lambda: {
        "usage": {"total_tokens": 1},
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

    fake_cfg = {
        "image_generation_models": {
            "default_tier": "cheap",
            "tiers": [
                {
                    "tier": "premium",
                    "id": "openrouter/mymodel/premium-x",
                    "display_name": "P",
                },
            ],
        }
    }
    monkeypatch.setattr("shared.image_gen_models.get_providers_config", lambda: fake_cfg)
    monkeypatch.setattr("shared.image_generation.get_providers_config", lambda: fake_cfg)
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
    await td._do_generate_image(
        {"prompt": "a cat"},
        {"user_id": "user-uuid", "image_generation_tier": "premium"},
    )
    assert client.post.call_count == 1
    _args, kwargs = client.post.call_args
    assert kwargs["json"]["model"] == "mymodel/premium-x"


@pytest.mark.asyncio
async def test_tool_dispatcher_generate_image_ignores_chat_model_in_args(monkeypatch):
    """LLM often passes the current chat model; those ids are not image-output models on OpenRouter."""
    tiny = base64.b64encode(b"x").decode("ascii")
    resp = MagicMock()
    resp.status_code = 200
    resp.json = lambda: {
        "choices": [
            {
                "message": {
                    "images": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{tiny}"}}
                    ],
                }
            }
        ],
    }
    client = AsyncMock()
    client.post = AsyncMock(return_value=resp)

    fake_cfg = {
        "image_generation_models": {
            "default_tier": "cheap",
            "default_model": "openrouter/google/gemini-2.5-flash-image",
            "models": [
                {
                    "id": "openrouter/google/gemini-2.5-flash-image",
                    "display_name": "Img",
                    "tier": "cheap",
                },
            ],
        }
    }
    monkeypatch.setattr("shared.image_gen_models.get_providers_config", lambda: fake_cfg)
    monkeypatch.setattr("shared.image_generation.get_providers_config", lambda: fake_cfg)
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
    await td._do_generate_image(
        {"prompt": "cat", "model": "google/gemini-3-flash-preview"},
        {"user_id": "u"},
    )
    _args, kwargs = client.post.call_args
    assert kwargs["json"]["model"] == "google/gemini-2.5-flash-image"
    assert kwargs["json"]["modalities"] == ["image", "text"]


def test_modalities_for_image_gen_model_id_default(monkeypatch):
    fake = {
        "image_generation_models": {
            "models": [
                {
                    "id": "openrouter/google/gemini-2.5-flash-image",
                    "display_name": "G",
                    "tier": "medium",
                },
            ],
        }
    }
    monkeypatch.setattr("shared.image_gen_models.get_providers_config", lambda: fake)
    assert modalities_for_image_gen_model_id("openrouter/google/gemini-2.5-flash-image") == [
        "image",
        "text",
    ]


def test_modalities_for_image_gen_model_id_image_only(monkeypatch):
    fake = {
        "image_generation_models": {
            "models": [
                {
                    "id": "openrouter/sourceful/riverflow-v2-pro",
                    "display_name": "R",
                    "tier": "cheap",
                    "modalities": ["image"],
                },
            ],
        }
    }
    monkeypatch.setattr("shared.image_gen_models.get_providers_config", lambda: fake)
    assert modalities_for_image_gen_model_id("openrouter/sourceful/riverflow-v2-pro") == ["image"]


@pytest.mark.asyncio
async def test_tool_dispatcher_generate_image_uses_image_only_modalities_from_yaml(monkeypatch):
    tiny = base64.b64encode(b"x").decode("ascii")
    resp = MagicMock()
    resp.status_code = 200
    resp.json = lambda: {
        "choices": [
            {
                "message": {
                    "images": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{tiny}"}}
                    ],
                }
            }
        ],
    }
    client = AsyncMock()
    client.post = AsyncMock(return_value=resp)
    fake_cfg = {
        "image_generation_models": {
            "default_tier": "cheap",
            "models": [
                {
                    "id": "openrouter/sourceful/riverflow-v2-pro",
                    "display_name": "R",
                    "tier": "cheap",
                    "modalities": ["image"],
                },
            ],
        }
    }
    monkeypatch.setattr("shared.image_gen_models.get_providers_config", lambda: fake_cfg)
    monkeypatch.setattr("shared.image_generation.get_providers_config", lambda: fake_cfg)
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
    await td._do_generate_image(
        {"prompt": "cat"},
        {"user_id": "u", "image_generation_model_id": "openrouter/sourceful/riverflow-v2-pro"},
    )
    _args, kwargs = client.post.call_args
    assert kwargs["json"]["model"] == "sourceful/riverflow-v2-pro"
    assert kwargs["json"]["modalities"] == ["image"]
