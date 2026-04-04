"""
Blogger service entry point.

Starts:
  - FastAPI app (post management API)
  - Business bot (group monitoring + owner DM check-in)
  - APScheduler (evening check-in at 20:00, post publisher hourly)
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import httpx
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.config import get_settings
from shared.utils import get_providers_config

from .agent import BloggerAgent
from .api import posts as posts_api
from .business_bot import BusinessBot
from .post_queue import PostQueue
from .publisher import TelegramPublisher
from .reader import BusinessChatReader

logger = logging.getLogger("blogger.main")

# =========================================================================
# Service-level singletons (populated in lifespan)
# =========================================================================
_db: asyncpg.Pool | None = None
_queue: PostQueue | None = None
_agent: BloggerAgent | None = None
_publisher: TelegramPublisher | None = None
_business_bot: BusinessBot | None = None
_scheduler: AsyncIOScheduler | None = None
_http: httpx.AsyncClient | None = None


def _get_blogger_config() -> dict:
    """Load blogger section from providers.yaml."""
    try:
        cfg = get_providers_config()
        return cfg.get("blogger", {})
    except Exception:
        return {}


# =========================================================================
# Scheduled jobs
# =========================================================================


async def _job_evening_checkin() -> None:
    """Evening check-in job — runs at 20:00."""
    if _agent:
        logger.info("Running evening check-in...")
        try:
            await _agent.run_evening_checkin()
        except Exception as exc:
            logger.error("Evening check-in error: %s", exc)


async def _job_publish_queue() -> None:
    """Hourly publisher — publishes up to daily_quota posts."""
    if not _queue or not _publisher:
        return

    try:
        posts = await _queue.get_publishable()
        if not posts:
            return

        settings = get_settings()
        cfg = _get_blogger_config()
        channel_cfg = cfg.get("channels", {})

        for post in posts:
            import json

            content = post.get("content") or {}
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except Exception:
                    content = {}

            post_type = post.get("post_type", "agent")
            channel_id_db = post.get("channel_db_id")

            if post_type == "user":
                # Personal channel
                ch_id = (
                    post.get("tg_channel_id")
                    or getattr(settings, "blogger_channel_personal", None)
                    or channel_cfg.get("personal", {}).get("id")
                )
                if not ch_id:
                    logger.warning("No personal channel configured, skipping post %s", post["id"])
                    continue
                text = content.get("ru", "")
                if await _publisher.publish_to_channel(ch_id, text):
                    await _queue.mark_published(post["id"], channel_id_db or 0)
                    logger.info("Published personal post %s", post["id"])
            else:
                # RU + EN channels
                ru_id = (
                    post.get("tg_channel_id")
                    or getattr(settings, "blogger_channel_ru", None)
                    or channel_cfg.get("ru", {}).get("id")
                )
                en_id = getattr(settings, "blogger_channel_en", None) or channel_cfg.get(
                    "en", {}
                ).get("id")
                ru_text = content.get("ru", "")
                en_text = content.get("en", "")
                published = False
                if ru_id and ru_text:
                    published = await _publisher.publish_to_channel(ru_id, ru_text)
                if en_id and en_text:
                    await _publisher.publish_to_channel(en_id, en_text)
                if published:
                    await _queue.mark_published(post["id"], channel_id_db or 0)
                    logger.info("Published agent post %s (RU+EN)", post["id"])

    except Exception as exc:
        logger.error("Publisher job error: %s", exc)


# =========================================================================
# Lifespan
# =========================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db, _queue, _agent, _publisher, _business_bot, _scheduler, _http

    settings = get_settings()
    cfg = _get_blogger_config()

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # HTTP client
    _http = httpx.AsyncClient(timeout=120.0)

    # PostgreSQL pool
    _db = await asyncpg.create_pool(settings.postgres_dsn, min_size=2, max_size=10)
    logger.info("PostgreSQL pool connected")

    # Post queue
    daily_quota = int(cfg.get("post_quota_per_day", 3))
    _queue = PostQueue(_db, daily_quota=daily_quota)

    # Publisher
    main_token = settings.telegram_bot_token or ""
    biz_token = settings.business_bot_token
    _publisher = TelegramPublisher(main_token, biz_token, _http)

    # Agent
    openrouter_key = settings.openrouter_api_key or ""
    owner_id = int(settings.telegram_user_id or 0)
    memory_url = settings.memory_service_url

    # Load model from data/agents/blogger/config.yaml
    _agent_cfg_path = (
        Path(__file__).parent.parent.parent / "data" / "agents" / "blogger" / "config.yaml"
    )
    _agent_cfg: dict = {}
    if _agent_cfg_path.exists():
        import yaml

        with _agent_cfg_path.open(encoding="utf-8") as _f:
            _agent_cfg = yaml.safe_load(_f) or {}
    agent_model = _agent_cfg.get("default_model") or None
    agent_cheap_model = _agent_cfg.get("cheap_model") or None
    logger.info("Blogger model: %s | cheap: %s", agent_model, agent_cheap_model)

    _agent = BloggerAgent(
        openrouter_api_key=openrouter_key,
        db=_db,
        post_queue=_queue,
        publisher=_publisher,
        memory_url=memory_url,
        owner_tg_id=owner_id,
        owner_private_chat_id=owner_id,
        model=agent_model,
        cheap_model=agent_cheap_model,
    )
    _agent.set_memory_url(memory_url)
    _agent.set_biz_reader(BusinessChatReader(_db))

    # Business bot
    if biz_token:
        _business_bot = BusinessBot(
            token=biz_token,
            owner_tg_id=owner_id,
            db=_db,
            agent=_agent,
        )
        _agent.business_bot = _business_bot
        logger.info("Business bot configured")
    else:
        logger.warning("BUSINESS_BOT_TOKEN not set — business bot disabled")

    # Init API router
    posts_api.init(_queue, _agent, _publisher, _business_bot)

    # Scheduler
    evening_hour = int(cfg.get("evening_checkin_hour", 20))
    _scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    _scheduler.add_job(
        _job_evening_checkin,
        "cron",
        hour=evening_hour,
        minute=0,
        id="evening_checkin",
    )
    _scheduler.add_job(
        _job_publish_queue,
        "interval",
        hours=1,
        id="post_publisher",
    )
    _scheduler.start()
    logger.info("Scheduler started (evening=%d:00, publisher=hourly)", evening_hour)

    # Start business bot polling in background (if configured)
    bot_task = None
    if _business_bot:
        bot_app = _business_bot.build()
        bot_task = asyncio.create_task(_run_business_bot(bot_app))

    yield

    # Shutdown
    if _scheduler:
        _scheduler.shutdown(wait=False)
    if bot_task:
        bot_task.cancel()
        try:
            await asyncio.wait_for(bot_task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
    if _agent:
        await _agent.close()
    if _db:
        await _db.close()
    if _http:
        await _http.aclose()
    logger.info("Blogger service stopped")


async def _run_business_bot(bot_app) -> None:
    """Run business bot polling loop."""
    try:
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Business bot polling started")
        # Keep running until cancelled
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.error("Business bot error: %s", exc)
    finally:
        try:
            await bot_app.updater.stop()
            await bot_app.stop()
            await bot_app.shutdown()
        except Exception:
            pass


# =========================================================================
# FastAPI app
# =========================================================================

app = FastAPI(
    title="Balbes Blogger Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(posts_api.router)
app.include_router(posts_api.business_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "blogger",
        "db": _db is not None,
        "business_bot": _business_bot is not None,
        "scheduler": _scheduler is not None and _scheduler.running,
    }


# =========================================================================
# Entry point
# =========================================================================

if __name__ == "__main__":
    settings = get_settings()
    port = settings.blogger_service_port
    uvicorn.run(
        "services.blogger.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
