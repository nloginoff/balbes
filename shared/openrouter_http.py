"""OpenRouter HTTP attribution headers (app name, referer) for dashboard analytics."""

from __future__ import annotations

from shared.config import Settings

_DEFAULT_REFERER = "https://github.com/nloginoff/balbes"
_DEFAULT_TITLE = "Balbes Multi Agent"


def openrouter_json_headers(settings: Settings, *, api_key: str | None = None) -> dict[str, str]:
    """
    Headers for OpenRouter JSON APIs (chat, embeddings, etc.).

    See https://openrouter.ai/docs/app-attribution — HTTP-Referer and X-OpenRouter-Title.
    """
    key = (api_key or settings.openrouter_api_key or "").strip()
    if not key:
        raise ValueError("OpenRouter API key is required")

    referer = (settings.openrouter_http_referer or "").strip() or _DEFAULT_REFERER
    title = (settings.openrouter_app_title or "").strip() or _DEFAULT_TITLE

    headers: dict[str, str] = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": referer,
        "X-OpenRouter-Title": title,
        "X-Title": title,
    }
    cats = (settings.openrouter_categories or "").strip()
    if cats:
        headers["X-OpenRouter-Categories"] = cats
    return headers
