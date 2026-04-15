"""
Webhooks Gateway — inbound HTTP endpoints only (no dashboard).

- POST /webhook/telegram — Telegram Bot API updates (when TELEGRAM_BOT_MODE=webhook)
- POST /webhook/max — MAX platform webhooks
- POST /webhook/notify — monitoring alerts (Bearer key)

Add future inbound webhooks here, not on web-backend.
"""

import logging
import sys
from pathlib import Path

# Ensure `routes` resolves when started as uvicorn services.webhooks_gateway.main:app
_svc_dir = Path(__file__).resolve().parent
if str(_svc_dir) not in sys.path:
    sys.path.insert(0, str(_svc_dir))

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from routes import max as max_routes
from routes import notify as notify_routes
from routes import telegram as telegram_routes

from shared.config import get_settings
from shared.telegram_app.balbes_bot import BalbesTelegramBot

settings = get_settings()
logger = logging.getLogger("webhooks_gateway")

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Start Telegram PTB application in webhook mode when configured."""
    app.state.telegram_bot = None
    if settings.telegram_bot_mode == "webhook" and settings.telegram_bot_token:
        bot = BalbesTelegramBot()
        bot.initialize()
        await bot.start_webhook_mode()
        app.state.telegram_bot = bot
        logger.info("Telegram main bot attached to webhook gateway")
    elif settings.telegram_bot_mode == "webhook":
        logger.warning("TELEGRAM_BOT_MODE=webhook but TELEGRAM_BOT_TOKEN is empty")
    yield
    tb = getattr(app.state, "telegram_bot", None)
    if isinstance(tb, BalbesTelegramBot):
        await tb.stop_webhook_mode()


app = FastAPI(
    title="Balbes Webhooks Gateway",
    description="Inbound webhooks: Telegram, MAX, monitoring notify",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Webhooks gateway error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.get("/health")
async def health_check() -> dict:
    return {
        "service": "webhooks_gateway",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "telegram_bot_mode": settings.telegram_bot_mode,
        "telegram_webhook_ready": getattr(app.state, "telegram_bot", None) is not None,
    }


@app.get("/")
async def root() -> dict:
    return {
        "service": "webhooks_gateway",
        "docs": "/docs",
        "health": "/health",
        "routes": [
            "POST /webhook/telegram",
            "POST /webhook/max",
            "POST /webhook/notify",
        ],
    }


app.include_router(notify_routes.router)
app.include_router(telegram_routes.router)
app.include_router(max_routes.router)


if __name__ == "__main__":
    import uvicorn

    port = settings.webhooks_gateway_port
    logger.info("Starting webhooks gateway on port %s", port)
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )
