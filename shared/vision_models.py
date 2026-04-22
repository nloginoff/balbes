"""Resolve vision model from config/providers.yaml — flat list or legacy tiers."""

from __future__ import annotations

from typing import Any

from shared.utils import get_providers_config

_VALID_TIERS = frozenset({"cheap", "medium", "premium"})


def vision_models_config() -> dict[str, Any]:
    cfg = get_providers_config()
    return cfg.get("vision_models") or {}


def _normalize_id(mid: str) -> str:
    m = (mid or "").strip()
    if not m:
        return ""
    return m if m.startswith("openrouter/") else f"openrouter/{m}"


def same_vision_model_id(a: str | None, b: str | None) -> bool:
    """True if two ids refer to the same allowlisted model."""
    if not a or not b:
        return False
    return _normalize_id(a) == _normalize_id(b)


def list_vision_models() -> list[dict[str, Any]]:
    """All vision models: `models` if set, else legacy `tiers` (multiple rows per tier allowed)."""
    vm = vision_models_config()
    raw = vm.get("models")
    if isinstance(raw, list) and raw:
        return [dict(x) for x in raw if isinstance(x, dict)]
    return list(vm.get("tiers") or [])


def default_vision_tier() -> str:
    """Backward compat: default tier label for legacy tier-based API."""
    vm = vision_models_config()
    t = (vm.get("default_tier") or "cheap").strip().lower()
    return t if t in _VALID_TIERS else "cheap"


def default_vision_model_id() -> str:
    """Default OpenRouter-prefixed model id: explicit default_model, else first in list."""
    vm = vision_models_config()
    explicit = (vm.get("default_model") or "").strip()
    if explicit:
        return _normalize_id(explicit)
    rows = list_vision_models()
    if rows:
        m = (rows[0].get("id") or "").strip()
        if m:
            return _normalize_id(m)
    return "openrouter/google/gemini-2.5-flash"


def validate_vision_model_id(model_id: str) -> bool:
    if not (model_id or "").strip():
        return False
    want = _normalize_id(model_id)
    return any(_normalize_id((row.get("id") or "").strip()) == want for row in list_vision_models())


def resolve_vision_model_id(tier_or_id: str | None) -> str | None:
    """
    - None / empty -> default_vision_model_id()
    - cheap|medium|premium -> first row in list with that tier
    - full id (openrouter/... or provider/model) if in allowlist -> normalized id
    """
    if not (tier_or_id or "").strip():
        return default_vision_model_id() or None
    s = tier_or_id.strip()
    s_low = s.lower()
    if s_low in _VALID_TIERS:
        for row in list_vision_models():
            if (row.get("tier") or "").strip().lower() == s_low:
                mid = (row.get("id") or "").strip()
                if mid:
                    return _normalize_id(mid)
        return default_vision_model_id() or None
    if "/" in s:
        n = _normalize_id(s)
        if validate_vision_model_id(n):
            return n
        return None
    return None


def vision_tier_display_name(tier: str) -> str:
    for row in list_vision_models():
        if (row.get("tier") or "").strip().lower() == tier.strip().lower():
            return str(row.get("display_name") or row.get("id") or tier)
    return tier


def vision_model_id_display_name(model_id: str) -> str:
    want = _normalize_id(model_id)
    for row in list_vision_models():
        if _normalize_id((row.get("id") or "").strip()) == want:
            return str(row.get("display_name") or row.get("id") or model_id)
    return model_id


def vision_request_timeout_seconds() -> float:
    """HTTP read timeout for OpenRouter vision (multimodal) calls."""
    vm = vision_models_config()
    raw = vm.get("timeout_seconds", 300)
    try:
        return max(30.0, float(raw))
    except (TypeError, ValueError):
        return 300.0


def vision_fallback_candidates(primary_model_id: str) -> list[str]:
    """
    Ordered model ids: primary first, then all configured vision models, deduped.
    """
    primary = _normalize_id((primary_model_id or "").strip())
    ordered_ids: list[str] = []
    for row in list_vision_models():
        mid = (row.get("id") or "").strip()
        if mid:
            ordered_ids.append(_normalize_id(mid))
    out: list[str] = []
    if primary:
        out.append(primary)
    for mid in ordered_ids:
        if mid not in out:
            out.append(mid)
    return out


def list_vision_tiers() -> list[dict[str, Any]]:
    """Alias: same rows as list_vision_models (legacy name)."""
    return list_vision_models()


def format_vision_row_caption(row: dict[str, Any], max_len: int = 60) -> str:
    """Button / menu line: display_name + price_hint or tier price band."""
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
