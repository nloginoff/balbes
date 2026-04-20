"""Outbound delivery for monitoring notifications (Telegram + optional MAX)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from shared.config import Settings
from shared.max_api import send_max_message_text
from shared.notify.payload import NotificationFormatter, WebhookPayload

logger = logging.getLogger(__name__)

TELEGRAM_TEXT_LIMIT = 4096


def _split_telegram_text(text: str) -> list[str]:
    if len(text) <= TELEGRAM_TEXT_LIMIT:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        chunks.append(remaining[:TELEGRAM_TEXT_LIMIT])
        remaining = remaining[TELEGRAM_TEXT_LIMIT:]
    return chunks


async def _telegram_send_html(
    *,
    token: str,
    chat_id: int,
    html: str,
) -> list[str]:
    """Send one or more Telegram messages; return message_id strings."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    message_ids: list[str] = []
    async with httpx.AsyncClient(timeout=45.0) as client:
        for part in _split_telegram_text(html):
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    resp = await client.post(
                        url,
                        json={
                            "chat_id": chat_id,
                            "text": part,
                            "parse_mode": "HTML",
                        },
                    )
                    if resp.status_code == 429:
                        data = resp.json() if resp.content else {}
                        retry_after = 2.0
                        try:
                            retry_after = float(
                                data.get("parameters", {}).get("retry_after", 2),
                            )
                        except (TypeError, ValueError):
                            pass
                        await asyncio.sleep(min(retry_after, 15.0))
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    if not data.get("ok"):
                        raise RuntimeError(data.get("description", "Telegram API error"))
                    mid = data.get("result", {}).get("message_id")
                    if mid is not None:
                        message_ids.append(str(mid))
                    last_exc = None
                    break
                except Exception as e:
                    last_exc = e
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (attempt + 1))
            if last_exc is not None:
                raise last_exc
    return message_ids


async def _max_send_text(
    *,
    api_url: str,
    token: str,
    text: str,
    chat_id: str | None = None,
    user_id: int | None = None,
) -> str | None:
    """Send plain text to MAX — exactly one of chat_id or user_id (per platform API)."""
    return await send_max_message_text(
        api_url=api_url,
        token=token,
        text=text,
        chat_id=chat_id,
        user_id=user_id,
        timeout=45.0,
    )


@dataclass
class NotifyDeliveryResult:
    """Per-channel delivery outcome."""

    telegram_message_ids: list[str] = field(default_factory=list)
    max_message_id: str | None = None
    skipped_channels: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "telegram_message_ids": self.telegram_message_ids,
            "max_message_id": self.max_message_id,
            "skipped_channels": self.skipped_channels,
            "errors": self.errors,
        }


def _resolve_telegram_chat_id(settings: Settings) -> int | None:
    if settings.notify_telegram_chat_id is not None:
        return int(settings.notify_telegram_chat_id)
    if settings.telegram_user_id is not None:
        return int(settings.telegram_user_id)
    return None


async def deliver_notify(settings: Settings, payload: WebhookPayload) -> NotifyDeliveryResult:
    """
    Deliver formatted notify to channels listed in notify_delivery_channels_list.

    Telegram uses HTML formatting. MAX uses plain text (when token + chat_id set).
    """
    channels = settings.notify_delivery_channels_list
    if not channels:
        channels = ["telegram"]

    result = NotifyDeliveryResult()

    html = NotificationFormatter.format_telegram_html(payload)
    plain = NotificationFormatter.format_plain(payload)

    if "telegram" in channels:
        token = settings.telegram_bot_token
        chat_id = _resolve_telegram_chat_id(settings)
        if not token or chat_id is None:
            msg = "Telegram channel requested but TELEGRAM_BOT_TOKEN or chat target missing"
            logger.warning(msg)
            result.skipped_channels.append("telegram")
            result.errors.append(msg)
        else:
            try:
                result.telegram_message_ids = await _telegram_send_html(
                    token=token,
                    chat_id=chat_id,
                    html=html,
                )
            except Exception as e:
                logger.exception("Telegram notify delivery failed: %s", e)
                result.errors.append(f"telegram: {e}")

    if "max" in channels:
        token = settings.max_bot_token
        m_uid = settings.notify_max_user_id
        m_chat = settings.notify_max_chat_id
        if not token:
            result.skipped_channels.append("max")
            result.errors.append("MAX notify skipped: MAX_BOT_TOKEN not set")
            logger.warning("MAX notify skipped: MAX_BOT_TOKEN not set")
        elif m_uid is not None:
            try:
                mid = await _max_send_text(
                    api_url=settings.max_api_url,
                    token=token,
                    text=plain,
                    user_id=m_uid,
                )
                result.max_message_id = mid
            except Exception as e:
                logger.exception("MAX notify delivery failed (user_id): %s", e)
                result.errors.append(f"max: {e}")
        elif m_chat:
            try:
                mid = await _max_send_text(
                    api_url=settings.max_api_url,
                    token=token,
                    text=plain,
                    chat_id=m_chat,
                )
                result.max_message_id = mid
            except Exception as e:
                logger.exception("MAX notify delivery failed (chat_id): %s", e)
                result.errors.append(f"max: {e}")
        else:
            result.skipped_channels.append("max")
            msg = (
                "MAX notify skipped: set NOTIFY_MAX_USER_ID (DM) or NOTIFY_MAX_CHAT_ID (group/chat)"
            )
            logger.info(msg)
            result.errors.append(msg)

    return result
