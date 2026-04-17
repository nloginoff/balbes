"""MAX messenger inbound webhook: verify signature, route user text to orchestrator."""

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from shared.config import get_settings
from shared.max_api import send_max_message_text
from shared.max_inbound import verify_max_webhook_auth
from shared.max_webhook import (
    extract_max_reply_targets,
    extract_message_text,
    should_process_message_created,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["max"])


async def _max_run_orchestrator_and_reply(
    *,
    text: str,
    sender_user_id: int,
    reply_chat_id: int | None,
    reply_user_id: int | None,
) -> None:
    """Call orchestrator /api/v1/tasks, then send assistant text via MAX API."""
    settings = get_settings()
    token = settings.max_bot_token
    if not token:
        logger.warning("MAX: skip reply — MAX_BOT_TOKEN not set")
        return

    base = settings.orchestrator_url.rstrip("/")
    url = f"{base}/api/v1/tasks"
    user_key = f"max:{sender_user_id}"
    timeout = float(settings.task_timeout_seconds) + 120.0
    params: dict[str, Any] = {
        "user_id": user_key,
        "description": text,
        "source": "max",
    }

    reply_text: str
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, params=params)
            if resp.status_code != 200:
                reply_text = f"Ошибка оркестратора: HTTP {resp.status_code}"
                try:
                    detail = resp.json().get("detail", resp.text[:500])
                    reply_text = f"{reply_text}\n{detail}"
                except Exception:
                    reply_text = f"{reply_text}\n{resp.text[:500]}"
            else:
                data = resp.json()
                if data.get("status") == "success":
                    inner = data.get("result") or {}
                    reply_text = str(inner.get("output", "")).strip() or "(пустой ответ)"
                else:
                    reply_text = str(data.get("error", "Неизвестная ошибка"))[:3500]
    except Exception as e:
        logger.exception("MAX orchestrator request failed: %s", e)
        reply_text = f"Сервис временно недоступен: {e!s}"[:3500]

    try:
        await send_max_message_text(
            api_url=settings.max_api_url,
            token=token,
            text=reply_text,
            chat_id=reply_chat_id,
            user_id=reply_user_id,
            timeout=120.0,
        )
    except Exception as e:
        logger.exception("MAX outbound reply failed: %s", e)


@router.post("/max")
async def max_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, bool]:
    """
    MAX platform POSTs inbound events here.

    Verifies X-Signature HMAC when MAX_WEBHOOK_SECRET is set.
    On message_created with user text: background task → orchestrator → POST /messages.
    """
    settings = get_settings()
    body = await request.body()
    api_secret_hdr = request.headers.get("X-Max-Bot-Api-Secret") or request.headers.get(
        "x-max-bot-api-secret"
    )
    sig = request.headers.get("X-Signature") or request.headers.get("x-signature")

    if settings.max_webhook_secret and not verify_max_webhook_auth(
        body=body,
        x_max_bot_api_secret=api_secret_hdr,
        x_signature=sig,
        secret=settings.max_webhook_secret,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid MAX webhook auth (X-Max-Bot-Api-Secret or X-Signature)",
        )

    if not body:
        return {"ok": True}

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON",
        ) from None

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expected JSON object",
        )

    ok, msg = should_process_message_created(data)
    if not ok or msg is None:
        return {"ok": True}

    sender = msg.get("sender")
    sender_user_id: int | None = None
    if isinstance(sender, dict) and sender.get("user_id") is not None:
        try:
            sender_user_id = int(sender["user_id"])
        except (TypeError, ValueError):
            sender_user_id = None

    if sender_user_id is None:
        logger.debug("MAX webhook: no sender user_id, skip")
        return {"ok": True}

    allowed = settings.max_allowed_user_ids
    if allowed and sender_user_id not in allowed:
        logger.info("MAX webhook: user %s not in MAX_ALLOWED_USER_IDS", sender_user_id)
        return {"ok": True}

    reply_chat_id, reply_user_id = extract_max_reply_targets(msg)
    if reply_chat_id is None and reply_user_id is None:
        logger.debug("MAX webhook: no reply target (chat_id/user_id)")
        return {"ok": True}

    text = extract_message_text(msg) or ""
    if not text:
        return {"ok": True}

    if not settings.max_bot_token:
        logger.warning("MAX webhook: message received but MAX_BOT_TOKEN unset — cannot reply")
        return {"ok": True}

    background_tasks.add_task(
        _max_run_orchestrator_and_reply,
        text=text,
        sender_user_id=sender_user_id,
        reply_chat_id=reply_chat_id,
        reply_user_id=reply_user_id,
    )
    return {"ok": True}
