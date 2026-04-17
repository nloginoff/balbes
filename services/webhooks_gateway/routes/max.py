"""MAX messenger inbound webhook: verify signature, slash commands, callbacks, orchestrator."""

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from routes.max_chat import (
    run_max_callback,
    run_max_slash_command,
    should_handle_slash_command,
)

from shared.config import get_settings
from shared.max_api import (
    max_answer_callback,
    max_send_chat_action,
    send_max_message,
    send_max_message_text,
)
from shared.max_bot_ui import MaxUiReply
from shared.max_inbound import verify_max_webhook_auth
from shared.max_webhook import (
    extract_max_reply_targets,
    extract_message_callback,
    extract_message_text,
    parse_slash_command,
    should_process_message_created,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["max"])


async def _max_send_ui_reply(
    *,
    reply: MaxUiReply,
    reply_chat_id: int | None,
    reply_user_id: int | None,
) -> None:
    settings = get_settings()
    token = settings.max_bot_token
    if not token:
        logger.warning("MAX: skip UI reply — MAX_BOT_TOKEN not set")
        return
    try:
        await send_max_message(
            api_url=settings.max_api_url,
            token=token,
            text=reply.text,
            chat_id=reply_chat_id,
            user_id=reply_user_id,
            attachments=reply.attachments,
            text_format=reply.text_format,
            timeout=120.0,
        )
    except Exception as e:
        logger.exception("MAX UI reply failed: %s", e)


async def _max_typing_if_chat(reply_chat_id: int | None) -> None:
    settings = get_settings()
    token = settings.max_bot_token
    if not token or reply_chat_id is None:
        return
    await max_send_chat_action(
        api_url=settings.max_api_url,
        token=token,
        chat_id=reply_chat_id,
        action="typing_on",
        timeout=15.0,
    )


async def _max_run_slash_command_task(
    *,
    command: str,
    rest: str,
    sender_user_id: int,
    reply_chat_id: int | None,
    reply_user_id: int | None,
) -> None:
    await _max_typing_if_chat(reply_chat_id)
    settings = get_settings()
    user_key = f"max:{sender_user_id}"
    mem = settings.memory_service_url.rstrip("/")
    orch = settings.orchestrator_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            reply = await run_max_slash_command(
                command=command,
                rest=rest,
                user_key=user_key,
                memory_url=mem,
                orchestrator_url=orch,
                client=client,
            )
        await _max_send_ui_reply(
            reply=reply,
            reply_chat_id=reply_chat_id,
            reply_user_id=reply_user_id,
        )
    except Exception as e:
        logger.exception("MAX slash command failed: %s", e)
        await _max_send_ui_reply(
            reply=MaxUiReply(text=f"❌ Ошибка команды: `{e!s}`"),
            reply_chat_id=reply_chat_id,
            reply_user_id=reply_user_id,
        )


async def _max_run_callback_task(
    *,
    callback_id: str,
    payload: str,
    sender_user_id: int,
    reply_chat_id: int | None,
    reply_user_id: int | None,
) -> None:
    settings = get_settings()
    token = settings.max_bot_token or ""
    if callback_id and token:
        await max_answer_callback(
            api_url=settings.max_api_url,
            token=token,
            callback_id=callback_id,
            notification="OK",
            timeout=20.0,
        )
    await _max_typing_if_chat(reply_chat_id)
    user_key = f"max:{sender_user_id}"
    mem = settings.memory_service_url.rstrip("/")
    orch = settings.orchestrator_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            reply = await run_max_callback(
                payload=payload,
                user_key=user_key,
                memory_url=mem,
                orchestrator_url=orch,
                client=client,
            )
        await _max_send_ui_reply(
            reply=reply,
            reply_chat_id=reply_chat_id,
            reply_user_id=reply_user_id,
        )
    except Exception as e:
        logger.exception("MAX callback failed: %s", e)
        await _max_send_ui_reply(
            reply=MaxUiReply(text=f"❌ Ошибка кнопки: `{e!s}`"),
            reply_chat_id=reply_chat_id,
            reply_user_id=reply_user_id,
        )


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

    await _max_typing_if_chat(reply_chat_id)

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
        httpx_timeout = httpx.Timeout(
            connect=30.0,
            read=timeout,
            write=120.0,
            pool=30.0,
        )
        async with httpx.AsyncClient(timeout=httpx_timeout) as client:
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

    Handles: message_callback (inline buttons), message_created (slash commands + LLM).
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

    update_type = data.get("update_type")

    # ── Inline button (callback) ─────────────────────────────────────────
    cb_info = extract_message_callback(data)
    if cb_info and update_type == "message_callback":
        sender_user_id = cb_info.get("user_id")
        if sender_user_id is None:
            logger.info("MAX webhook: callback without user_id")
            return {"ok": True}

        allowed = settings.max_allowed_user_ids
        if allowed and int(sender_user_id) not in allowed:
            logger.warning(
                "MAX webhook: skip callback — user_id=%s not in MAX_ALLOWED_USER_IDS",
                sender_user_id,
            )
            return {"ok": True}

        msg = cb_info.get("message")
        if not isinstance(msg, dict):
            return {"ok": True}

        reply_chat_id, reply_user_id = extract_max_reply_targets(msg)
        if reply_chat_id is None and reply_user_id is None:
            logger.warning("MAX webhook: callback — no reply target")
            return {"ok": True}

        if not settings.max_bot_token:
            logger.warning("MAX webhook: callback but MAX_BOT_TOKEN unset")
            return {"ok": True}

        payload = cb_info.get("payload") or ""
        cid = cb_info.get("callback_id") or ""
        logger.info(
            "MAX webhook: schedule callback user_id=%s payload_len=%s",
            sender_user_id,
            len(str(payload)),
        )
        background_tasks.add_task(
            _max_run_callback_task,
            callback_id=str(cid),
            payload=str(payload),
            sender_user_id=int(sender_user_id),
            reply_chat_id=reply_chat_id,
            reply_user_id=reply_user_id,
        )
        return {"ok": True}

    # ── New message ──────────────────────────────────────────────────────
    ok, msg = should_process_message_created(data)
    if not ok or msg is None:
        logger.info(
            "MAX webhook: skip (not message_created or no user text); update_type=%r",
            update_type,
        )
        return {"ok": True}

    sender = msg.get("sender")
    sender_user_id: int | None = None
    if isinstance(sender, dict) and sender.get("user_id") is not None:
        try:
            sender_user_id = int(sender["user_id"])
        except (TypeError, ValueError):
            sender_user_id = None

    if sender_user_id is None:
        logger.info("MAX webhook: skip — no sender.user_id in message")
        return {"ok": True}

    allowed = settings.max_allowed_user_ids
    if allowed and sender_user_id not in allowed:
        logger.warning(
            "MAX webhook: skip — sender user_id=%s not in MAX_ALLOWED_USER_IDS=%s",
            sender_user_id,
            allowed,
        )
        return {"ok": True}

    reply_chat_id, reply_user_id = extract_max_reply_targets(msg)
    if reply_chat_id is None and reply_user_id is None:
        logger.warning(
            "MAX webhook: skip — cannot resolve reply target (recipient/sender); recipient=%s",
            msg.get("recipient"),
        )
        return {"ok": True}

    text = extract_message_text(msg) or ""
    if not text:
        logger.info("MAX webhook: skip — empty body.text")
        return {"ok": True}

    if not settings.max_bot_token:
        logger.warning("MAX webhook: message received but MAX_BOT_TOKEN unset — cannot reply")
        return {"ok": True}

    parsed = parse_slash_command(text)
    if parsed:
        cmd, rest = parsed
        if should_handle_slash_command(cmd):
            logger.info(
                "MAX webhook: slash /%s user_id=%s chat_id=%s",
                cmd,
                sender_user_id,
                reply_chat_id,
            )
            background_tasks.add_task(
                _max_run_slash_command_task,
                command=cmd,
                rest=rest,
                sender_user_id=sender_user_id,
                reply_chat_id=reply_chat_id,
                reply_user_id=reply_user_id,
            )
            return {"ok": True}

    logger.info(
        "MAX webhook: schedule LLM user_id=%s chat_id=%s reply_user_id=%s text_len=%s",
        sender_user_id,
        reply_chat_id,
        reply_user_id,
        len(text),
    )
    background_tasks.add_task(
        _max_run_orchestrator_and_reply,
        text=text,
        sender_user_id=sender_user_id,
        reply_chat_id=reply_chat_id,
        reply_user_id=reply_user_id,
    )
    return {"ok": True}
