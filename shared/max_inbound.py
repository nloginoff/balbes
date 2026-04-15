"""Verify MAX platform inbound webhook HMAC signature (dev.max.ru style)."""

import hashlib
import hmac


def verify_max_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    """Return True if signature matches HMAC-SHA256(secret, body) as hex digest."""
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.strip().lower(), expected.lower())
