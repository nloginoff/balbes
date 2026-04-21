"""MAX Messenger platform-api HTTP helpers (outbound messages)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_TEXT_LIMIT = 4000


def _query_chat_id_param(chat_id: int | str) -> int | str:
    """Normalize chat_id for query params (supports negative dialog ids)."""
    if isinstance(chat_id, int):
        return chat_id
    s = str(chat_id).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return chat_id


def normalize_max_access_token(token: str) -> str:
    """
    MAX platform-api expects `Authorization: <access_token>` (raw token), not `Bearer ...`.
    See https://dev.max.ru/docs-api/methods/POST/messages
    """
    t = (token or "").strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return t


def split_max_text(text: str) -> list[str]:
    if len(text) <= MAX_TEXT_LIMIT:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        chunks.append(remaining[:MAX_TEXT_LIMIT])
        remaining = remaining[MAX_TEXT_LIMIT:]
    return chunks


async def max_send_chat_action(
    *,
    api_url: str,
    token: str,
    chat_id: int | str,
    action: str = "typing_on",
    timeout: float = 15.0,
) -> bool:
    """
    POST /chats/{chatId}/actions — typing indicator, etc.
    See https://dev.max.ru/docs-api/methods/POST/chats/-chatId-/actions
    """
    base = api_url.rstrip("/")
    cid = _query_chat_id_param(chat_id)
    url = f"{base}/chats/{cid}/actions"
    access = normalize_max_access_token(token)
    if not access:
        return False
    headers = {"Authorization": access, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json={"action": action})
            if resp.status_code >= 400:
                logger.debug("MAX chat action failed: %s %s", resp.status_code, resp.text[:200])
            return resp.status_code < 400
    except Exception as e:
        logger.debug("MAX chat action error: %s", e)
        return False


async def max_answer_callback(
    *,
    api_url: str,
    token: str,
    callback_id: str,
    notification: str | None = None,
    timeout: float = 30.0,
) -> bool:
    """
    POST /answers?callback_id=...
    See https://dev.max.ru/docs-api/methods/POST/answers
    """
    if not (callback_id or "").strip():
        return False
    base = api_url.rstrip("/")
    url = f"{base}/answers"
    access = normalize_max_access_token(token)
    if not access:
        return False
    headers = {"Authorization": access, "Content-Type": "application/json"}
    body: dict[str, Any] = {}
    if notification:
        body["notification"] = notification[:4000]
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers=headers,
                params={"callback_id": callback_id},
                json=body if body else {},
            )
            return resp.status_code < 400
    except Exception as e:
        logger.warning("MAX answer_callback failed: %s", e)
        return False


async def send_max_message(
    *,
    api_url: str,
    token: str,
    text: str,
    chat_id: int | str | None = None,
    user_id: int | None = None,
    attachments: list[dict[str, Any]] | None = None,
    text_format: str | None = None,
    timeout: float = 120.0,
) -> str | None:
    """
    POST /messages with optional inline_keyboard attachments and markdown/html.
    """
    # Do not use truthiness: chat_id can be 0 (valid dialog id in some APIs).
    if chat_id is not None and user_id is not None:
        logger.warning(
            "MAX send_max_message: both chat_id=%s and user_id=%s — using chat_id only",
            chat_id,
            user_id,
        )
        user_id = None
    if (chat_id is not None) == (user_id is not None):
        raise ValueError("send_max_message: set exactly one of chat_id or user_id")

    base = api_url.rstrip("/")
    url = f"{base}/messages"
    access = normalize_max_access_token(token)
    if not access:
        raise ValueError("MAX access token is empty")
    headers = {
        "Authorization": access,
        "Content-Type": "application/json",
    }
    params: dict[str, Any] = {}
    if chat_id is not None:
        params["chat_id"] = _query_chat_id_param(chat_id)
    if user_id is not None:
        params["user_id"] = user_id

    body: dict[str, Any] = {}
    if text:
        body["text"] = text
    if attachments is not None:
        body["attachments"] = attachments
    if text_format:
        body["format"] = text_format

    chunks = split_max_text(text) if text else ([""] if attachments else [""])
    last_mid: str | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for i, part in enumerate(chunks):
            chunk_body = {**body, "text": part}
            if i > 0:
                chunk_body.pop("attachments", None)
                # Keep ``format`` on continuation text chunks (markdown/html applies to each part).
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    resp = await client.post(
                        url,
                        headers=headers,
                        params=params,
                        json=chunk_body,
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


async def send_max_message_markdown_from_model(
    *,
    api_url: str,
    token: str,
    raw_model_text: str,
    chat_id: int | str | None = None,
    user_id: int | None = None,
    timeout: float = 120.0,
) -> str | None:
    """
    Convert orchestrator/model plain text to MAX markdown (see shared.max_format_outbound),
    POST each chunk with ``format: markdown``. If the API rejects the body (HTTP error), retry
    that chunk as plain text without ``format``.
    """
    from shared.max_format_outbound import (
        max_markdown_to_plain,
        model_text_to_max_markdown,
        raw_chunks_for_max_markdown,
    )

    pieces = raw_chunks_for_max_markdown(raw_model_text)
    if not pieces:
        return None

    last_mid: str | None = None
    for piece in pieces:
        md = model_text_to_max_markdown(piece)
        parts = split_max_text(md) if md else []
        for part in parts:
            if not part:
                continue
            try:
                last_mid = await send_max_message(
                    api_url=api_url,
                    token=token,
                    text=part,
                    chat_id=chat_id,
                    user_id=user_id,
                    attachments=None,
                    text_format="markdown",
                    timeout=timeout,
                )
            except Exception as e:
                logger.warning("MAX markdown send failed, trying plain: %s", e)
                plain = max_markdown_to_plain(part)
                last_mid = await send_max_message(
                    api_url=api_url,
                    token=token,
                    text=plain,
                    chat_id=chat_id,
                    user_id=user_id,
                    attachments=None,
                    text_format=None,
                    timeout=timeout,
                )
    return last_mid


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
    return await send_max_message(
        api_url=api_url,
        token=token,
        text=text,
        chat_id=chat_id,
        user_id=user_id,
        attachments=None,
        text_format=None,
        timeout=timeout,
    )
