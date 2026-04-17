"""HTTP client for Memory Service identity resolution (canonical user id)."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def resolve_canonical_user_id(
    memory_service_url: str,
    provider: str,
    external_id: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = 10.0,
) -> str:
    """
    Return stable canonical user id for a provider-specific external id.

    provider: "telegram" | "max" (case-insensitive)
    external_id: Telegram user id as decimal string, or MAX user id as decimal string
    """
    base = memory_service_url.rstrip("/")
    params = {"provider": provider, "external_id": external_id}
    own_client = client is None
    c = client or httpx.AsyncClient(timeout=timeout)
    try:
        resp = await c.get(f"{base}/api/v1/identity/resolve", params=params)
        if resp.status_code != 200:
            logger.error(
                "identity resolve failed: HTTP %s %s",
                resp.status_code,
                resp.text[:300],
            )
            raise RuntimeError(f"identity resolve failed: HTTP {resp.status_code}")
        data = resp.json()
        uid = data.get("canonical_user_id")
        if not uid or not isinstance(uid, str):
            raise RuntimeError("identity resolve: missing canonical_user_id")
        return uid
    finally:
        if own_client:
            await c.aclose()


async def create_pairing_code(
    memory_service_url: str,
    canonical_user_id: str,
    intended_provider: str,
    *,
    identity_link_secret: str | None = None,
    client: httpx.AsyncClient | None = None,
    timeout: float = 15.0,
) -> tuple[str, int]:
    """Returns (code, expires_in_seconds)."""
    base = memory_service_url.rstrip("/")
    headers: dict[str, str] = {}
    if identity_link_secret:
        headers["X-Balbes-Identity-Link-Secret"] = identity_link_secret
    own_client = client is None
    c = client or httpx.AsyncClient(timeout=timeout)
    try:
        resp = await c.post(
            f"{base}/api/v1/identity/pairing/create",
            json={
                "canonical_user_id": canonical_user_id,
                "intended_provider": intended_provider,
            },
            headers=headers,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"pairing create failed: HTTP {resp.status_code} {resp.text[:400]}")
        data = resp.json()
        code = data.get("code")
        ttl = int(data.get("expires_in_seconds", 0))
        if not code:
            raise RuntimeError("pairing create: missing code")
        return str(code), ttl
    finally:
        if own_client:
            await c.aclose()


async def redeem_pairing_code(
    memory_service_url: str,
    code: str,
    provider: str,
    external_id: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = 15.0,
) -> dict:
    """Public redeem — code is the credential."""
    base = memory_service_url.rstrip("/")
    own_client = client is None
    c = client or httpx.AsyncClient(timeout=timeout)
    try:
        resp = await c.post(
            f"{base}/api/v1/identity/pairing/redeem",
            json={"code": code.strip(), "provider": provider, "external_id": external_id},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"pairing redeem failed: HTTP {resp.status_code} {resp.text[:400]}")
        return resp.json()
    finally:
        if own_client:
            await c.aclose()
