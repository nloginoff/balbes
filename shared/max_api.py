"""MAX Messenger platform-api HTTP helpers (outbound messages)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_TEXT_LIMIT = 4000


def split_max_text(text: str) -> list[str]:
    if len(text) <= MAX_TEXT_LIMIT:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        chunks.append(remaining[:MAX_TEXT_LIMIT])
        remaining = remaining[MAX_TEXT_LIMIT:]
    return chunks


async def send_max_message_text(
    *,
    api_url: str,
    token: str,
    text: str,
    chat_id: int | str | None = None,
    user_id: int | None = None,
    timeout: float = 120.0,
) -> str | None:
    """
    POST /messages per https://dev.max.ru/docs-api/methods/POST/messages

    Exactly one of chat_id or user_id must be set (query param).
    """
    if bool(chat_id) == bool(user_id):
        raise ValueError("send_max_message_text: set exactly one of chat_id or user_id")

    base = api_url.rstrip("/")
    url = f"{base}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    params: dict[str, Any] = {}
    if chat_id is not None:
        params["chat_id"] = int(chat_id) if str(chat_id).isdigit() else chat_id
    if user_id is not None:
        params["user_id"] = user_id

    last_mid: str | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for part in split_max_text(text):
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    resp = await client.post(
                        url,
                        headers=headers,
                        params=params,
                        json={"text": part},
                    )
                    if resp.status_code == 429:
                        await asyncio.sleep(2.0)
                        continue
                    if resp.status_code >= 400:
                        logger.warning(
                            "MAX send_message failed: %s %s",
                            resp.status_code,
                            resp.text[:500],
                        )
                        resp.raise_for_status()
                    try:
                        data = resp.json()
                    except Exception:
                        return last_mid
                    if isinstance(data, dict):
                        m = data.get("message") or data
                        if isinstance(m, dict):
                            mid = m.get("message_id") or m.get("mid") or data.get("message_id")
                            if mid is not None:
                                last_mid = str(mid)
                    last_exc = None
                    break
                except Exception as e:
                    last_exc = e
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (attempt + 1))
            if last_exc is not None:
                raise last_exc
    return last_mid
