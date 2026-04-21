"""Resolve vision tier → OpenRouter model id from config/providers.yaml."""

from __future__ import annotations

from typing import Any

from shared.utils import get_providers_config

_VALID_TIERS = frozenset({"cheap", "medium", "premium"})


def vision_models_config() -> dict[str, Any]:
    cfg = get_providers_config()
    return cfg.get("vision_models") or {}


def default_vision_tier() -> str:
    vm = vision_models_config()
    t = (vm.get("default_tier") or "cheap").strip().lower()
    return t if t in _VALID_TIERS else "cheap"


def list_vision_tiers() -> list[dict[str, Any]]:
    """Tiers with tier, id, display_name."""
    vm = vision_models_config()
    return list(vm.get("tiers") or [])


def resolve_vision_model_id(tier: str | None) -> str | None:
    """Return openrouter-prefixed model id for tier, or None if missing."""
    t = (tier or default_vision_tier()).strip().lower()
    if t not in _VALID_TIERS:
        t = default_vision_tier()
    for row in list_vision_tiers():
        if (row.get("tier") or "").strip().lower() == t:
            mid = (row.get("id") or "").strip()
            return mid or None
    return None


def vision_tier_display_name(tier: str) -> str:
    for row in list_vision_tiers():
        if (row.get("tier") or "").strip().lower() == tier.strip().lower():
            return str(row.get("display_name") or row.get("id") or tier)
    return tier
