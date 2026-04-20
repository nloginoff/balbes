"""
Mirror orchestrator replies to linked Telegram/MAX when presence is active.

Primary delivery stays in the inbound handler; this module handles secondaries only
or primary+secondaries via deliver_agent_text_with_mirror.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import httpx

from shared.config import Settings
from shared.identity_client import (
    channel_presence_active,
    get_active_chat_scoped,
    list_identity_peers,
)
from shared.max_api import send_max_message_text
from shared.telegram_app.format_outbound import model_text_to_telegram_html
from shared.telegram_app.text import split_long_text

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def mirror_target_providers(settings: Settings) -> frozenset[str]:
    """Providers allowed as mirror destinations (from AGENT_REPLY_MIRROR_PROVIDERS)."""
    raw = (settings.agent_reply_mirror_providers or "").strip()
    if not raw:
        return frozenset()
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def text_plain_for_max(markdownish: str) -> str:
    """Best-effort strip for MAX (plain); cap at API limit."""
    t = markdownish
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    return t.strip()[:4000]


async def mirror_agent_text_to_secondaries(
    *,
    settings: Settings,
    client: httpx.AsyncClient,
    memory_url: str,
    canonical_user_id: str,
    source_channel: str,
    memory_chat_id: str,
    text: str,
    telegram_bot: Any | None,
) -> None:
    """
    Send `text` to linked messengers other than source_channel, if mirror enabled,
    target channel presence is active within TTL, and the target's **scoped** active
    Memory chat matches `memory_chat_id` (same conversation on both sides).
    """
    if not settings.agent_reply_mirror_enabled:
        return
    if not (memory_chat_id and str(memory_chat_id).strip()):
        return
    allowed = mirror_target_providers(settings)
    if not allowed:
        return
    ttl = settings.agent_reply_mirror_presence_ttl_seconds
    try:
        data = await list_identity_peers(memory_url, canonical_user_id, client=client)
    except Exception as e:
        logger.warning("mirror: list peers failed: %s", e)
        return
    peers = data.get("peers") or []
    src = source_channel.lower().strip()
    token = settings.max_bot_token
    api = settings.max_api_url.rstrip("/")
    tg_token = settings.telegram_bot_token

    for peer in peers:
        prov = (peer.get("provider") or "").lower().strip()
        ext = (peer.get("external_id") or "").strip()
        if not prov or not ext or prov == src:
            continue
        if prov not in allowed:
            continue
        try:
            active = await channel_presence_active(
                memory_url,
                canonical_user_id,
                prov,
                ttl_seconds=ttl,
                client=client,
            )
        except Exception as e:
            logger.debug("mirror: presence check %s: %s", prov, e)
            continue
        if not active:
            continue
        try:
            target_active = await get_active_chat_scoped(
                memory_url,
                canonical_user_id,
                prov,
                create_if_missing=False,
                client=client,
            )
        except Exception as e:
            logger.debug("mirror: target active chat %s: %s", prov, e)
            continue
        if target_active != memory_chat_id:
            continue
        if prov == "max" and token:
            try:
                plain = text_plain_for_max(text)
                await send_max_message_text(
                    api_url=api,
                    token=token,
                    text=plain,
                    user_id=int(ext),
                    timeout=120.0,
                )
            except Exception as e:
                logger.warning("mirror: MAX send failed: %s", e)
        elif prov == "telegram" and tg_token:
            chat_id = int(ext)
            url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            for chunk in split_long_text(text):
                body = model_text_to_telegram_html(chunk)
                try:
                    if telegram_bot is not None:
                        try:
                            await telegram_bot.send_message(chat_id, body, parse_mode="HTML")
                        except Exception:
                            await telegram_bot.send_message(chat_id, chunk)
                    else:
                        r = await client.post(
                            url,
                            json={
                                "chat_id": chat_id,
                                "text": body,
                                "parse_mode": "HTML",
                            },
                            timeout=45.0,
                        )
                        if r.status_code >= 400:
                            await client.post(
                                url,
                                json={"chat_id": chat_id, "text": chunk},
                                timeout=45.0,
                            )
                except Exception as e2:
                    logger.warning("mirror: Telegram send failed: %s", e2)
                    break


async def deliver_agent_text_with_mirror(
    *,
    settings: Settings,
    client: httpx.AsyncClient,
    memory_url: str,
    canonical_user_id: str,
    source_channel: str,
    memory_chat_id: str,
    text: str,
    send_primary: Callable[[], Awaitable[None]],
    telegram_bot: Any | None,
) -> None:
    """Deliver primary, then mirror to eligible secondaries.

    Presence must be updated only on **inbound** user messages (handlers), not here,
    otherwise bot replies would keep the source channel perpetually \"active\".
    """
    await send_primary()
    await mirror_agent_text_to_secondaries(
        settings=settings,
        client=client,
        memory_url=memory_url,
        canonical_user_id=canonical_user_id,
        source_channel=source_channel,
        memory_chat_id=memory_chat_id,
        text=text,
        telegram_bot=telegram_bot,
    )
