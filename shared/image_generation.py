"""OpenRouter image generation: read defaults from config/providers.yaml, parse API responses."""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

from shared.utils import get_providers_config

logger = logging.getLogger(__name__)

_DATA_URL_RE = re.compile(
    r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$",
    re.DOTALL,
)


def image_generation_config() -> dict[str, Any]:
    cfg = get_providers_config()
    return dict(cfg.get("image_generation") or {})


def default_image_model_id() -> str:
    ig = image_generation_config()
    mid = (ig.get("default_model") or "").strip()
    return mid or "openrouter/google/gemini-2.5-flash-image"


def image_generation_timeout_seconds() -> float:
    ig = image_generation_config()
    raw = ig.get("timeout_seconds", 180)
    try:
        return max(30.0, float(raw))
    except (TypeError, ValueError):
        return 180.0


def default_image_config_dict() -> dict[str, Any]:
    """Default OpenRouter `image_config` from YAML (aspect_ratio, image_size, …)."""
    ig = image_generation_config()
    ic = ig.get("image_config")
    if not isinstance(ic, dict):
        return {}
    return {k: v for k, v in ic.items() if v is not None}


def strip_openrouter_prefix(model_id: str) -> str:
    """Strip `openrouter/` for OpenRouter API `model` field."""
    m = (model_id or "").strip()
    if m.startswith("openrouter/"):
        return m[len("openrouter/") :]
    return m


def decode_data_url(data_url: str) -> tuple[bytes, str]:
    """Parse data:image/...;base64,... into raw bytes and mime type (no parameters)."""
    s = (data_url or "").strip()
    m = _DATA_URL_RE.match(s)
    if not m:
        raise ValueError("Некорректный data URL изображения")
    mime = (m.group("mime") or "image/png").split(";")[0].strip().lower()
    raw = base64.b64decode(m.group("data"), validate=True)
    return raw, mime


def extract_images_from_openrouter_message(message: dict[str, Any]) -> list[tuple[bytes, str]]:
    """
    Extract (raw bytes, mime) from `choices[0].message` (images[].image_url.url data URLs).
    HTTP(S) URLs are not resolved here.
    """
    out: list[tuple[bytes, str]] = []
    for img in message.get("images") or []:
        if not isinstance(img, dict):
            continue
        iu = img.get("image_url") or img.get("imageUrl")
        if not isinstance(iu, dict):
            continue
        url = (iu.get("url") or "").strip()
        if not url.startswith("data:"):
            continue
        try:
            raw, mime = decode_data_url(url)
            out.append((raw, mime))
        except Exception as e:
            logger.warning("skip bad image data url: %s", e)
    return out


def assistant_text_from_message(message: dict[str, Any]) -> str:
    c = message.get("content")
    if isinstance(c, str):
        return c.strip()
    return ""
