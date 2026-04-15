"""MAX messenger inbound webhook (verify signature; full routing TBD)."""

import logging

from fastapi import APIRouter, HTTPException, Request, status

from shared.config import get_settings
from shared.max_inbound import verify_max_webhook_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["max"])


@router.post("/max")
async def max_webhook(request: Request) -> dict[str, bool]:
    """
    MAX platform POSTs inbound events here.

    Verifies X-Signature HMAC when MAX_WEBHOOK_SECRET is set.
    Processing logic will be extended (unified messenger, blogger summaries, etc.).
    """
    settings = get_settings()
    body = await request.body()
    sig = request.headers.get("X-Signature") or request.headers.get("x-signature")

    if settings.max_webhook_secret and (
        not sig or not verify_max_webhook_signature(body, sig, settings.max_webhook_secret)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid MAX signature")

    # Placeholder: acknowledge receipt; parse JSON when schema is finalized
    try:
        if body:
            logger.debug("MAX webhook raw body length=%s", len(body))
    except Exception:
        pass

    return {"ok": True}
