"""Parse MAX webhook JSON (dev.max.ru Update objects)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def extract_max_reply_targets(message: dict[str, Any]) -> tuple[int | None, int | None]:
    """
    Return (chat_id, user_id) for POST /messages — exactly one should be used.

    Prefer ``recipient.chat_id`` (dialogs/groups). Some clients nest the id under
    ``recipient.chat.chat_id``.

    For query ``user_id=`` the peer must be a **human** user. In real DM payloads the
    human writes to the bot: ``sender.user_id`` is the human, while ``recipient.user_id``
    is often the **bot** — using ``recipient.user_id`` would POST to the wrong id.
    """
    recipient = message.get("recipient")
    sender = message.get("sender")

    if isinstance(recipient, dict):
        raw_cid = recipient.get("chat_id")
        if raw_cid is None:
            chat_obj = recipient.get("chat")
            if isinstance(chat_obj, dict):
                raw_cid = chat_obj.get("chat_id")
        if raw_cid is not None:
            cid = _to_int(raw_cid)
            if cid is not None:
                return (cid, None)
            logger.warning("MAX webhook: invalid recipient.chat_id %r", raw_cid)

        ruid_raw = recipient.get("user_id")
        if ruid_raw is not None:
            try:
                ruid = int(ruid_raw)
            except (TypeError, ValueError):
                logger.warning("MAX webhook: invalid recipient.user_id %r", ruid_raw)
            else:
                sender_uid: int | None = None
                sender_is_bot = False
                if isinstance(sender, dict):
                    sender_is_bot = bool(sender.get("is_bot"))
                    su = sender.get("user_id")
                    if su is not None:
                        try:
                            sender_uid = int(su)
                        except (TypeError, ValueError):
                            sender_uid = None
                if sender_uid is not None and not sender_is_bot and ruid != sender_uid:
                    return (None, sender_uid)
                return (None, ruid)

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


def parse_slash_command(text: str) -> tuple[str, str] | None:
    """
    If text starts with /command, return (command_lower, rest_line) without leading slash.
    Strips @botname suffix if present. Returns None if not a slash command.
    """
    s = (text or "").strip()
    if not s.startswith("/"):
        return None
    first = s.split(maxsplit=1)
    cmd_part = first[0]
    rest = first[1] if len(first) > 1 else ""
    if "@" in cmd_part:
        cmd_part = cmd_part.split("@", 1)[0]
    cmd = cmd_part[1:].strip().lower()
    if not cmd:
        return None
    return (cmd, rest.strip())


def extract_message_callback(data: dict[str, Any]) -> dict[str, Any] | None:
    """
    For update_type == message_callback, return dict with callback_id, payload, user_id, message.
    See https://dev.max.ru/docs-api (callback + message siblings).
    """
    if data.get("update_type") != "message_callback":
        return None
    cb = data.get("callback")
    if not isinstance(cb, dict):
        return None
    msg = data.get("message")
    if not isinstance(msg, dict):
        return None
    user = cb.get("user")
    uid = None
    if isinstance(user, dict) and user.get("user_id") is not None:
        try:
            uid = int(user["user_id"])
        except (TypeError, ValueError):
            uid = None
    return {
        "callback_id": str(cb.get("callback_id") or ""),
        "payload": str(cb.get("payload") or ""),
        "user_id": uid,
        "message": msg,
    }
