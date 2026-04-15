"""Unit tests for monitoring webhook auth, payload formatting, rate limiter."""

import pytest
from fastapi import HTTPException

from shared.notify.auth import validate_webhook_bearer_key
from shared.notify.payload import NotificationFormatter, WebhookPayload
from shared.notify.rate_limit import SlidingWindowRateLimiter


def test_validate_webhook_bearer_key_ok() -> None:
    validate_webhook_bearer_key("Bearer secret-key-123", "secret-key-123")


def test_validate_webhook_bearer_key_wrong() -> None:
    with pytest.raises(HTTPException) as ei:
        validate_webhook_bearer_key("Bearer other", "secret-key-123")
    assert ei.value.status_code == 403


def test_validate_webhook_bearer_key_no_config() -> None:
    with pytest.raises(HTTPException) as ei:
        validate_webhook_bearer_key("Bearer x", None)
    assert ei.value.status_code == 503


def test_notification_formatter_html_escapes() -> None:
    p = WebhookPayload(
        event_type="error",
        service="svc",
        severity="critical",
        message="Hello <script>",
        timestamp="2026-04-15T12:00:00Z",
        details={"x": "<b>bold</b>"},
    )
    html = NotificationFormatter.format_telegram_html(p)
    assert "<script>" not in html or "&lt;" in html
    assert "Hello" in html


def test_sliding_window_rate_limiter() -> None:
    lim = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
    lim.check("ip1")
    lim.check("ip1")
    with pytest.raises(HTTPException) as ei:
        lim.check("ip1")
    assert ei.value.status_code == 429


def test_sliding_window_override_max() -> None:
    lim = SlidingWindowRateLimiter(max_requests=1, window_seconds=60.0)
    lim.check("a", max_requests=5)
    lim.check("a", max_requests=5)
    lim.check("a", max_requests=5)
