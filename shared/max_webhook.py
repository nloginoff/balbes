"""Parse MAX webhook JSON (dev.max.ru Update objects)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_max_reply_targets(message: dict[str, Any]) -> tuple[int | None, int | None]:
    """
    Return (chat_id, user_id) for POST /messages — exactly one should be used.

    Group/channel: recipient.chat_id. DM: reply to sender user_id.
    """
    recipient = message.get("recipient")
    if isinstance(recipient, dict):
        cid = recipient.get("chat_id")
        if cid is not None:
            try:
                return (int(cid), None)
            except (TypeError, ValueError):
                logger.warning("MAX webhook: invalid recipient.chat_id %r", cid)

    sender = message.get("sender")
    if isinstance(sender, dict):
        if sender.get("is_bot"):
            return (None, None)
        uid = sender.get("user_id")
        if uid is not None:
            try:
                return (None, int(uid))
            except (TypeError, ValueError):
                logger.warning("MAX webhook: invalid sender.user_id %r", uid)

    return (None, None)


def extract_message_text(message: dict[str, Any]) -> str | None:
    """Plain text from message.body.text (or empty)."""
    body = message.get("body")
    if not isinstance(body, dict):
        return None
    text = body.get("text")
    if text is None:
        return None
    s = str(text).strip()
    return s if s else None


def should_process_message_created(data: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
    """
    If this is a user text message we should handle, return (True, message).

    Skips non-message_created, missing text, and sender bots.
    """
    if data.get("update_type") != "message_created":
        return False, None

    msg = data.get("message")
    if not isinstance(msg, dict):
        return False, None

    sender = msg.get("sender")
    if isinstance(sender, dict) and sender.get("is_bot"):
        return False, None

    text = extract_message_text(msg)
    if not text:
        return False, None

    return True, msg
