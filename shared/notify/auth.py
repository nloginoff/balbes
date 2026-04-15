"""Validate Bearer API key for inbound monitoring webhooks."""

import hashlib
import hmac
from typing import Any

from fastapi import HTTPException, status


def validate_webhook_bearer_key(authorization: str | None, expected_key: str | None) -> None:
    """
    Require Authorization: Bearer <key>, compare in constant time.

    Raises:
        HTTPException: 401/403 if missing or wrong; 503 if expected_key not configured.
    """
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook notify is not configured (WEBHOOK_NOTIFY_API_KEY unset)",
        )
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    try:
        parts = authorization.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise ValueError("bad scheme")
        token = parts[1].strip()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed Authorization header",
        ) from None

    # Constant-time compare via SHA-256 digests (handles unequal key lengths safely)
    digest_a = hashlib.sha256(token.encode("utf-8")).digest()
    digest_b = hashlib.sha256(expected_key.encode("utf-8")).digest()
    if not hmac.compare_digest(digest_a, digest_b):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )


def redact_auth_for_logs(authorization: str | None) -> dict[str, Any]:
    """Safe extra fields for structured logging (never log the raw key)."""
    if not authorization:
        return {"auth": "none"}
    try:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return {"auth": "bearer", "token_prefix": parts[1].strip()[:4] + "…"}
    except Exception:
        pass
    return {"auth": "present"}
