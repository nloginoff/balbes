"""Verify MAX platform inbound webhook (official API + legacy HMAC)."""

import hashlib
import hmac


def verify_max_webhook_secret_header(header_value: str | None, secret: str) -> bool:
    """Official MAX: subscription `secret` is sent as plain value in X-Max-Bot-Api-Secret."""
    if not header_value or not secret:
        return False
    return hmac.compare_digest(header_value.strip(), secret.strip())


def verify_max_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    """Legacy/alternate: X-Signature = HMAC-SHA256(secret, body) as hex digest."""
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.strip().lower(), expected.lower())


def verify_max_webhook_auth(
    *,
    body: bytes,
    x_max_bot_api_secret: str | None,
    x_signature: str | None,
    secret: str,
) -> bool:
    """
    If `secret` is configured, accept either:
    - X-Max-Bot-Api-Secret (see POST /subscriptions on platform-api.max.ru), or
    - X-Signature (HMAC-SHA256 hex over body).
    """
    if not secret:
        return True
    return bool(
        x_max_bot_api_secret and verify_max_webhook_secret_header(x_max_bot_api_secret, secret)
    ) or bool(x_signature and verify_max_webhook_signature(body, x_signature, secret))
