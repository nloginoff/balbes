"""Resolve image generation tier → OpenRouter model id from config/providers.yaml (like vision_models)."""

from __future__ import annotations

from typing import Any

from shared.utils import get_providers_config

_VALID_TIERS = frozenset({"cheap", "medium", "premium"})


def image_gen_models_config() -> dict[str, Any]:
    cfg = get_providers_config()
    return dict(cfg.get("image_generation_models") or {})


def default_image_gen_tier() -> str:
    ig = image_gen_models_config()
    t = (ig.get("default_tier") or "cheap").strip().lower()
    return t if t in _VALID_TIERS else "cheap"


def list_image_gen_tiers() -> list[dict[str, Any]]:
    """Tiers with tier, id, display_name."""
    ig = image_gen_models_config()
    return list(ig.get("tiers") or [])


def resolve_image_gen_model_id(tier: str | None) -> str | None:
    """Return openrouter-prefixed model id for tier, or None if missing."""
    t = (tier or default_image_gen_tier()).strip().lower()
    if t not in _VALID_TIERS:
        t = default_image_gen_tier()
    for row in list_image_gen_tiers():
        if (row.get("tier") or "").strip().lower() == t:
            mid = (row.get("id") or "").strip()
            return mid or None
    return None


def image_gen_tier_display_name(tier: str) -> str:
    for row in list_image_gen_tiers():
        if (row.get("tier") or "").strip().lower() == tier.strip().lower():
            return str(row.get("display_name") or row.get("id") or tier)
    return tier


def image_gen_models_timeout_seconds() -> float | None:
    """Optional override from image_generation_models; None = use shared.image_generation timeout."""
    ig = image_gen_models_config()
    raw = ig.get("timeout_seconds")
    if raw is None:
        return None
    try:
        return max(30.0, float(raw))
    except (TypeError, ValueError):
        return None


def default_image_config_from_models() -> dict[str, Any]:
    """Default image_config from image_generation_models block if present."""
    ig = image_gen_models_config()
    ic = ig.get("image_config")
    if not isinstance(ic, dict):
        return {}
    return {k: v for k, v in ic.items() if v is not None}
