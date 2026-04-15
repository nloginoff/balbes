"""
Inbound monitoring webhook: external servers POST alerts; delivery via shared/notify.

Moved from web-backend — same behavior, served by webhooks-gateway only.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from shared.config import get_settings
from shared.notify.auth import redact_auth_for_logs, validate_webhook_bearer_key
from shared.notify.delivery import deliver_notify
from shared.notify.payload import WebhookPayload
from shared.notify.rate_limit import SlidingWindowRateLimiter, client_ip

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notify"])

_rate_limiter = SlidingWindowRateLimiter(max_requests=60, window_seconds=60.0)


class NotifyErrorResponse(BaseModel):
    status: str = "error"
    code: str
    message: str


class NotifyOkResponse(BaseModel):
    status: str = "ok"
    delivered_at: str
    delivery: dict


@router.post(
    "/api/webhooks/notify",
    response_model=NotifyOkResponse,
    responses={
        401: {"model": NotifyErrorResponse},
        403: {"model": NotifyErrorResponse},
        429: {"model": NotifyErrorResponse},
        503: {"model": NotifyErrorResponse},
    },
)
@router.post(
    "/webhook/notify",
    response_model=NotifyOkResponse,
    responses={
        401: {"model": NotifyErrorResponse},
        403: {"model": NotifyErrorResponse},
        429: {"model": NotifyErrorResponse},
        503: {"model": NotifyErrorResponse},
    },
)
async def receive_monitoring_notification(
    request: Request,
    payload: WebhookPayload,
    authorization: str | None = Header(None),
) -> NotifyOkResponse:
    """
    Receive JSON alert from external monitoring (e.g. RU server).

    Authorization: Bearer <WEBHOOK_NOTIFY_API_KEY>
    """
    settings = get_settings()
    _rate_limiter.check(client_ip(request), settings.notify_rate_limit_per_minute)

    validate_webhook_bearer_key(authorization, settings.webhook_notify_api_key)

    if payload.details and "stack_trace" in payload.details:
        logger.error(
            "Notify stack_trace (server log only): %s",
            str(payload.details.get("stack_trace"))[:2000],
        )

    logger.info(
        "Webhook notify: service=%s event=%s severity=%s %s",
        payload.service,
        payload.event_type,
        payload.severity,
        redact_auth_for_logs(authorization),
    )

    result = await deliver_notify(settings, payload)

    if result.errors and not (result.telegram_message_ids or result.max_message_id):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"errors": result.errors, "delivery": result.as_dict()},
        )

    return NotifyOkResponse(
        status="ok",
        delivered_at=datetime.now(timezone.utc).isoformat(),
        delivery=result.as_dict(),
    )
