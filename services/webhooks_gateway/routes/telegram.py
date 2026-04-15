"""Telegram Bot API webhook: POST body is Update JSON."""

import logging

from fastapi import APIRouter, Header, HTTPException, Request, status

from shared.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["telegram"])


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(
        None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
) -> dict[str, bool]:
    """
    Telegram sends updates here when setWebhook is configured.

    Optional: set TELEGRAM_WEBHOOK_SECRET and pass the same via setWebhook(secret_token=...).
    """
    settings = get_settings()
    if settings.telegram_bot_mode != "webhook":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram webhook disabled: set TELEGRAM_BOT_MODE=webhook",
        )

    if settings.telegram_webhook_secret and (
        not x_telegram_bot_api_secret_token
        or x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")

    bot = getattr(request.app.state, "telegram_bot", None)
    if not bot:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot not initialized on this gateway",
        )

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON"
        ) from None

    if not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expected JSON object")

    try:
        await bot.process_webhook_update(data)
    except Exception as e:
        logger.exception("telegram webhook process_update failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process update",
        ) from e

    return {"ok": True}
