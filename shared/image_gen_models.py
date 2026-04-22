"""Resolve image generation model from config/providers.yaml — flat list or legacy tiers."""

from __future__ import annotations

from typing import Any

from shared.utils import get_providers_config

_VALID_TIERS = frozenset({"cheap", "medium", "premium"})


def image_gen_models_config() -> dict[str, Any]:
    cfg = get_providers_config()
    return dict(cfg.get("image_generation_models") or {})


def _normalize_id(mid: str) -> str:
    m = (mid or "").strip()
    if not m:
        return ""
    return m if m.startswith("openrouter/") else f"openrouter/{m}"


def same_image_gen_model_id(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return _normalize_id(a) == _normalize_id(b)


def list_image_gen_models() -> list[dict[str, Any]]:
    """All image gen models: `models` if set, else legacy `tiers`."""
    ig = image_gen_models_config()
    raw = ig.get("models")
    if isinstance(raw, list) and raw:
        return [dict(x) for x in raw if isinstance(x, dict)]
    return list(ig.get("tiers") or [])


def default_image_gen_tier() -> str:
    ig = image_gen_models_config()
    t = (ig.get("default_tier") or "cheap").strip().lower()
    return t if t in _VALID_TIERS else "cheap"


def default_image_gen_model_id() -> str:
    ig = image_gen_models_config()
    explicit = (ig.get("default_model") or "").strip()
    if explicit:
        return _normalize_id(explicit)
    rows = list_image_gen_models()
    if rows:
        m = (rows[0].get("id") or "").strip()
        if m:
            return _normalize_id(m)
    return "openrouter/google/gemini-2.5-flash-image"


def validate_image_gen_model_id(model_id: str) -> bool:
    if not (model_id or "").strip():
        return False
    want = _normalize_id(model_id)
    return any(
        _normalize_id((row.get("id") or "").strip()) == want for row in list_image_gen_models()
    )


def resolve_image_gen_model_id(tier_or_id: str | None) -> str | None:
    if not (tier_or_id or "").strip():
        return default_image_gen_model_id() or None
    s = tier_or_id.strip()
    s_low = s.lower()
    if s_low in _VALID_TIERS:
        for row in list_image_gen_models():
            if (row.get("tier") or "").strip().lower() == s_low:
                mid = (row.get("id") or "").strip()
                if mid:
                    return _normalize_id(mid)
        return default_image_gen_model_id() or None
    if "/" in s:
        n = _normalize_id(s)
        if validate_image_gen_model_id(n):
            return n
        return None
    return None


def image_gen_tier_display_name(tier: str) -> str:
    for row in list_image_gen_models():
        if (row.get("tier") or "").strip().lower() == tier.strip().lower():
            return str(row.get("display_name") or row.get("id") or tier)
    return tier


def image_gen_model_id_display_name(model_id: str) -> str:
    want = _normalize_id(model_id)
    for row in list_image_gen_models():
        if _normalize_id((row.get("id") or "").strip()) == want:
            return str(row.get("display_name") or row.get("id") or model_id)
    return model_id


def image_gen_models_timeout_seconds() -> float | None:
    ig = image_gen_models_config()
    raw = ig.get("timeout_seconds")
    if raw is None:
        return None
    try:
        return max(30.0, float(raw))
    except (TypeError, ValueError):
        return None


def default_image_config_from_models() -> dict[str, Any]:
    ig = image_gen_models_config()
    ic = ig.get("image_config")
    if not isinstance(ic, dict):
        return {}
    return {k: v for k, v in ic.items() if v is not None}


def list_image_gen_tiers() -> list[dict[str, Any]]:
    """Alias for list_image_gen_models (legacy name)."""
    return list_image_gen_models()


def format_image_gen_row_caption(row: dict[str, Any], max_len: int = 60) -> str:
    """Button line for /imagemodel: display_name + price_hint or tier band."""
    base = str(row.get("display_name") or row.get("id") or "?")
    ph = (row.get("price_hint") or "").strip()
    if ph:
        s = f"{base} ({ph})"
    else:
        t = (row.get("tier") or "").strip().lower()
        if t in _VALID_TIERS:
            hint = {"cheap": "низк. цена", "medium": "ср. цена", "premium": "выс. цена"}.get(t, t)
            s = f"{base} ({hint})"
        else:
            s = base
    return s if len(s) <= max_len else s[: max_len - 1] + "…"
