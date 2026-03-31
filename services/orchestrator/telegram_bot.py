"""
Telegram Bot for Balbes Multi-Agent System.

Commands:
  /start          — welcome message
  /help           — command reference
  /status         — orchestrator health check
  /agents         — list agents, switch active agent for current chat
  /chats          — list chats (with ID, agent, model), switch active chat
  /newchat [name] — create a new chat and switch to it
  /rename <name>  — rename current chat
  /model          — show model selection keyboard for current chat
  /model <id>     — set model for current chat directly
  /clear          — clear current chat history
  /remember <txt> — save text to long-term memory (Qdrant)
  /recall <query> — search long-term memory

Voice messages are automatically transcribed via Whisper and corrected via LLM.
"""

import asyncio
import contextlib
import logging
from pathlib import Path

import httpx
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    User,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from shared.config import get_settings

settings = get_settings()
logger = logging.getLogger("orchestrator.telegram")

CALLBACK_CHAT_PREFIX = "chat:"
CALLBACK_MODEL_PREFIX = "model:"
CALLBACK_AGENT_PREFIX = "agent:"
CALLBACK_NEW_CHAT = "new_chat"
CALLBACK_MODEL_UNAVAIL_YES = "model_unavail:yes:"
CALLBACK_MODEL_UNAVAIL_NO = "model_unavail:no"


_MD2_ESCAPE_RE = str.maketrans({c: f"\\{c}" for c in r"\_*[]()~`>#+-=|{}.!"})


def _escape_md2(text: str) -> str:
    """Escape special characters for MarkdownV2."""
    return str(text).translate(_MD2_ESCAPE_RE)


def _load_providers_yaml() -> dict:
    """Load providers.yaml once. Returns empty dict on failure."""
    try:
        import yaml

        cfg_path = Path(__file__).parent.parent.parent / "config" / "providers.yaml"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to load providers.yaml: {e}")
    return {}


def _load_active_models() -> list[dict]:
    """Load active_models list from providers.yaml."""
    return _load_providers_yaml().get("active_models", [])


def _load_agents() -> list[dict]:
    """Load agents list from providers.yaml."""
    return _load_providers_yaml().get("agents", [])


def _make_model_keyboard(exclude_id: str | None = None) -> InlineKeyboardMarkup:
    models = _load_active_models()
    buttons = []
    for m in models:
        if m.get("id") == exclude_id:
            continue
        buttons.append(
            [
                InlineKeyboardButton(
                    m.get("display_name", m["id"]),
                    callback_data=f"{CALLBACK_MODEL_PREFIX}{m['id']}",
                )
            ]
        )
    if not buttons:
        buttons = [[InlineKeyboardButton("No models configured", callback_data="noop")]]
    return InlineKeyboardMarkup(buttons)


def _make_agent_keyboard(current_id: str | None = None) -> InlineKeyboardMarkup:
    agents = _load_agents()
    buttons = []
    for a in agents:
        emoji = a.get("emoji", "🤖")
        name = a.get("display_name", a["id"])
        mark = "✅ " if a.get("id") == current_id else ""
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{mark}{emoji} {name}",
                    callback_data=f"{CALLBACK_AGENT_PREFIX}{a['id']}",
                )
            ]
        )
    if not buttons:
        buttons = [[InlineKeyboardButton("No agents configured", callback_data="noop")]]
    return InlineKeyboardMarkup(buttons)


def _load_heartbeat_config() -> dict:
    """Load heartbeat config from providers.yaml."""
    cfg = _load_providers_yaml().get("heartbeat", {})

    # target_user_id: YAML may contain a literal "${TELEGRAM_USER_ID}" placeholder
    # (YAML doesn't do env substitution). Always prefer settings.telegram_user_id
    # which is loaded from the TELEGRAM_USER_ID env var.
    raw_uid = cfg.get("target_user_id", "")
    resolved_uid = (
        settings.telegram_user_id if (not raw_uid or str(raw_uid).startswith("$")) else raw_uid
    )

    return {
        "enabled": cfg.get("enabled", False),
        "every_minutes": cfg.get("every_minutes", 30),
        "model": cfg.get("model") or None,
        "fallback_models": cfg.get("fallback_models") or [],
        "active_hours_start": cfg.get("active_hours_start", "08:00"),
        "active_hours_end": cfg.get("active_hours_end", "23:00"),
        "target_user_id": resolved_uid,
    }


def _is_within_active_hours(start: str, end: str) -> bool:
    """Return True if current local time is within [start, end)."""
    from datetime import datetime as _dt
    from datetime import time

    now = _dt.now().time()
    try:
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        t_start = time(sh, sm)
        t_end = time(eh, em)
        if t_start <= t_end:
            return t_start <= now < t_end
        # Crosses midnight
        return now >= t_start or now < t_end
    except Exception:
        return True  # default: allow


HEARTBEAT_OK = "HEARTBEAT_OK"
HEARTBEAT_PROMPT = (
    "SYSTEM HEARTBEAT RUN.\n"
    "Read HEARTBEAT.md from your workspace if it exists and follow it strictly.\n"
    "Do not repeat tasks from previous conversations unless they are still relevant.\n"
    "If nothing needs user attention right now, reply exactly: HEARTBEAT_OK\n"
    "If you have something important to tell the user, write the message (without HEARTBEAT_OK)."
)


class BalbesTelegramBot:
    """
    Telegram Bot for Balbes System with multi-chat and model management.
    """

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.app: Application | None = None
        self.http_client: httpx.AsyncClient | None = None
        self.orchestrator_url = f"http://localhost:{settings.orchestrator_port}"
        self.memory_url = settings.memory_service_url

        # Per-chat async locks to prevent concurrent message processing
        self._chat_locks: dict[str, asyncio.Lock] = {}

        # Active processing tasks: user_id → asyncio.Task (for /stop)
        self._active_tasks: dict[str, asyncio.Task] = {}

        # Heartbeat background task
        self._heartbeat_task: asyncio.Task | None = None

        # Background task monitors: key = f"{user_id}:{agent_id}" → asyncio.Task
        # Each monitor polls the orchestrator for progress and sends updates to Telegram.
        self._bg_monitors: dict[str, asyncio.Task] = {}
        # Maps monitor key → Telegram chat_id (int) so the monitor knows where to write
        self._bg_monitor_chat: dict[str, int] = {}

    def initialize(self) -> None:
        """Initialize Telegram bot application."""
        logger.info("Initializing Telegram bot...")

        async def _post_init(app: Application) -> None:
            await self._set_commands(app)
            await self.start_heartbeat()

        self.app = (
            Application.builder()
            .token(self.token)
            .concurrent_updates(True)  # parallel — required for /stop to interrupt processing
            .post_init(_post_init)
            .build()
        )
        self._setup_handlers()
        allowed = settings.telegram_allowed_users
        if allowed:
            logger.info(f"Telegram bot initialized — allowed users: {allowed}")
        else:
            logger.warning(
                "Telegram bot initialized — TELEGRAM_ALLOWED_USERS is empty, "
                "bot is open to everyone!"
            )

    def start_polling(self) -> None:
        if not self.app:
            raise RuntimeError("Bot not initialized")
        logger.info("Starting bot polling...")
        self.app.run_polling(drop_pending_updates=True)

    # -------------------------------------------------------------------------
    # Heartbeat
    # -------------------------------------------------------------------------

    async def start_heartbeat(self) -> None:
        """Start background heartbeat loop (call after bot is running)."""
        cfg = _load_heartbeat_config()
        if not cfg["enabled"]:
            logger.info("Heartbeat disabled (set heartbeat.enabled: true in providers.yaml)")
            return
        if not cfg["target_user_id"]:
            logger.warning(
                "Heartbeat disabled: TELEGRAM_USER_ID not set in .env.prod — "
                "add your numeric Telegram ID (get it from @userinfobot)"
            )
            return
        interval_sec = cfg["every_minutes"] * 60
        logger.info(
            f"Heartbeat started: every {cfg['every_minutes']}m → user {cfg['target_user_id']}"
        )
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval_sec, cfg))

    async def stop_heartbeat(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

    async def _heartbeat_loop(self, interval_sec: int, cfg: dict) -> None:
        """Background loop: sleep, then fire heartbeat check."""
        # First run after one full interval (don't fire immediately on startup)
        await asyncio.sleep(interval_sec)
        while True:
            try:
                await self._run_heartbeat(cfg)
            except Exception as e:
                logger.warning(f"Heartbeat run failed: {e}")
            await asyncio.sleep(interval_sec)

    async def _run_heartbeat(self, cfg: dict) -> None:
        """Execute one heartbeat turn and deliver result if non-OK."""
        # Check active hours
        if not _is_within_active_hours(cfg["active_hours_start"], cfg["active_hours_end"]):
            logger.debug("Heartbeat: outside active hours, skipping")
            return

        user_id = str(cfg["target_user_id"])
        logger.info(f"Heartbeat: starting run for user {user_id}")

        # Build ordered list of models to try: primary + fallbacks from config
        primary = cfg.get("model")
        fallbacks: list[str] = cfg.get("fallback_models") or []
        models_to_try: list[str | None] = ([primary] if primary else [None]) + fallbacks

        result: dict | None = None
        last_error: str = "unknown error"

        for attempt, model_id in enumerate(models_to_try):
            try:
                params: dict = {
                    "user_id": user_id,
                    "description": HEARTBEAT_PROMPT,
                    "agent_id": "orchestrator",
                    "source": "heartbeat",
                }
                if model_id:
                    params["model_id"] = model_id

                response = await self._get_http().post(
                    f"{self.orchestrator_url}/api/v1/tasks",
                    params=params,
                    timeout=90.0,
                )
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(f"Heartbeat: request failed (model={model_id}): {last_error}")
                continue

            if response.status_code != 200:
                last_error = f"HTTP {response.status_code}"
                logger.warning(f"Heartbeat: {last_error} (model={model_id})")
                continue

            candidate = response.json()
            if candidate.get("status") != "success":
                err = candidate.get("error", "")
                last_error = err or "task failed"
                logger.warning(f"Heartbeat: task failed (model={model_id}) — {last_error}")
                # Retry only on model unavailability / rate limit
                retriable = any(
                    kw in last_error.lower()
                    for kw in ("429", "unavailable", "недоступна", "rate limit", "403", "forbidden")
                )
                if retriable:
                    if attempt < len(models_to_try) - 1:
                        await asyncio.sleep(1.5)  # brief pause before trying next model
                    continue
                # Non-retriable failure (e.g. internal error) → stop without error message
                return

            # Success — but check if the LLM returned an internal error text
            payload_out = candidate.get("result", {})
            out_text = str(payload_out.get("output") or payload_out.get("result") or "").strip()
            _INTERNAL_ERRORS = [
                "Не смог обработать запрос",
                "Error: 'filename' parameter is required",
            ]
            if any(out_text.startswith(e) for e in _INTERNAL_ERRORS):
                last_error = f"internal model error: {out_text[:80]}"
                logger.warning(
                    f"Heartbeat: suppressed internal error from model={model_id}: {out_text[:80]}"
                )
                if attempt < len(models_to_try) - 1:
                    await asyncio.sleep(1.5)
                    continue
                return  # all models failed internally — don't notify user

            result = candidate
            if attempt > 0:
                logger.info(
                    f"Heartbeat: succeeded with {'fallback ' if attempt > 0 else ''}model {model_id} (attempt {attempt + 1})"
                )
            break

        if result is None:
            # All models exhausted — notify user
            logger.warning(
                f"Heartbeat: all {len(models_to_try)} models failed. Last error: {last_error}"
            )
            if self.app:
                try:
                    await self.app.bot.send_message(
                        chat_id=int(user_id),
                        text=(
                            "⚠️ *Heartbeat не смог выполниться*\n"
                            f"Все доступные модели ({len(models_to_try)}) вернули ошибку.\n"
                            f"Последняя ошибка: `{last_error[:200]}`"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.warning(f"Heartbeat: failed to send error notification: {e}")
            return

        payload = result.get("result", {})
        text = str(payload.get("output") or payload.get("result") or "").strip()

        # Suppress error messages — LLM unavailability or internal errors must not reach the user
        _SUPPRESS_PREFIXES = [
            "❌",
            "Не смог обработать запрос",
            "Error: 'filename'",
        ]
        if any(text.startswith(p) for p in _SUPPRESS_PREFIXES):
            logger.warning(f"Heartbeat: suppressed output — {text[:120]}")
            return

        # Suppress HEARTBEAT_OK responses
        stripped = text.strip()
        if stripped.startswith(HEARTBEAT_OK) or stripped.endswith(HEARTBEAT_OK):
            remaining = stripped.replace(HEARTBEAT_OK, "").strip()
            if len(remaining) <= 300:
                logger.info("Heartbeat: OK, nothing to send")
                return
            text = remaining

        if not text:
            return

        # Deliver to user
        if self.app:
            try:
                await self.app.bot.send_message(
                    chat_id=int(user_id),
                    text=f"💡 {text}",
                )
                logger.info(f"Heartbeat: ✅ delivered message to user {user_id}: {text[:80]}")
            except Exception as e:
                logger.warning(f"Heartbeat: failed to send message: {e}")

    async def _security_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Global authorization gate — runs before ALL other handlers (group=-1).

        Rejects any update whose sender is not in settings.telegram_allowed_users.
        If the whitelist is empty the bot is open (useful during local dev).
        Raises ApplicationHandlerStop to prevent further processing for blocked users.
        """
        allowed: list[int] = settings.telegram_allowed_users
        if not allowed:
            return  # no restriction configured

        user = update.effective_user
        if user is None or user.id not in allowed:
            uid = user.id if user else "unknown"
            logger.warning(f"Blocked unauthorized access from user_id={uid}")
            if update.callback_query:
                await update.callback_query.answer("⛔ Доступ запрещён", show_alert=True)
            elif update.effective_message:
                await update.effective_message.reply_text(
                    "⛔ Доступ запрещён. Этот бот не публичный."
                )
            raise ApplicationHandlerStop

    def _setup_handlers(self) -> None:
        if not self.app:
            return

        # Security gate: runs before every other handler (group=-1)
        self.app.add_handler(TypeHandler(Update, self._security_check), group=-1)

        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("stop", self.cmd_stop))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("clear", self.cmd_clear))
        self.app.add_handler(CommandHandler("agents", self.cmd_agents))
        self.app.add_handler(CommandHandler("chats", self.cmd_chats))
        self.app.add_handler(CommandHandler("newchat", self.cmd_newchat))
        self.app.add_handler(CommandHandler("rename", self.cmd_rename))
        self.app.add_handler(CommandHandler("model", self.cmd_model))
        self.app.add_handler(CommandHandler("remember", self.cmd_remember))
        self.app.add_handler(CommandHandler("recall", self.cmd_recall))
        self.app.add_handler(CommandHandler("heartbeat", self.cmd_heartbeat))
        self.app.add_handler(CommandHandler("debug", self.cmd_debug))
        self.app.add_handler(CommandHandler("mode", self.cmd_mode))
        self.app.add_handler(CommandHandler("tasks", self.cmd_tasks))

        # Inline keyboard callbacks
        self.app.add_handler(
            CallbackQueryHandler(self.cb_chat_selected, pattern=f"^{CALLBACK_CHAT_PREFIX}")
        )
        self.app.add_handler(
            CallbackQueryHandler(self.cb_model_selected, pattern=f"^{CALLBACK_MODEL_PREFIX}")
        )
        self.app.add_handler(
            CallbackQueryHandler(self.cb_agent_selected, pattern=f"^{CALLBACK_AGENT_PREFIX}")
        )
        self.app.add_handler(
            CallbackQueryHandler(self.cb_new_chat, pattern=f"^{CALLBACK_NEW_CHAT}$")
        )
        self.app.add_handler(CallbackQueryHandler(self.cb_model_unavail, pattern="^model_unavail:"))
        self.app.add_handler(CallbackQueryHandler(self.cb_mode_set, pattern="^mode_set:"))

        # Voice messages
        self.app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.handle_voice))

        # Regular text messages
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def _set_commands(self, app: Application) -> None:
        commands = [
            BotCommand("start", "Начать работу"),
            BotCommand("help", "Справка по командам"),
            BotCommand("stop", "⛔ Остановить текущее действие агента"),
            BotCommand("agents", "Список агентов / переключить агента"),
            BotCommand("chats", "Список чатов / переключить чат"),
            BotCommand("newchat", "Создать новый чат"),
            BotCommand("rename", "Переименовать текущий чат"),
            BotCommand("model", "Выбрать модель для чата"),
            BotCommand("clear", "Очистить историю чата"),
            BotCommand("remember", "Сохранить в долгосрочную память"),
            BotCommand("recall", "Найти в долгосрочной памяти"),
            BotCommand("heartbeat", "Запустить проверку прямо сейчас"),
            BotCommand("debug", "🔍 Включить/выключить трейс действий"),
            BotCommand("mode", "🤖 Режим: agent (exec) / 📝 ask (только чтение)"),
            BotCommand("tasks", "📋 Список задач агентов (реестр)"),
            BotCommand("status", "Статус системы"),
        ]
        await app.bot.set_my_commands(commands)

    def _get_http(self) -> httpx.AsyncClient:
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(timeout=60.0)
        return self.http_client

    def _get_lock(self, user_id: str, chat_id: str) -> asyncio.Lock:
        key = f"{user_id}:{chat_id}"
        if key not in self._chat_locks:
            self._chat_locks[key] = asyncio.Lock()
        return self._chat_locks[key]

    # -------------------------------------------------------------------------
    # Helpers: Memory Service API
    # -------------------------------------------------------------------------

    async def _get_active_chat(self, user_id: str) -> str | None:
        try:
            r = await self._get_http().get(f"{self.memory_url}/api/v1/chats/{user_id}/active")
            if r.status_code == 200:
                return r.json().get("chat_id")
        except Exception as e:
            logger.debug(f"get_active_chat error: {e}")
        return None

    async def _set_active_chat(self, user_id: str, chat_id: str) -> None:
        try:
            await self._get_http().put(
                f"{self.memory_url}/api/v1/chats/{user_id}/active",
                params={"chat_id": chat_id},
            )
        except Exception as e:
            logger.debug(f"set_active_chat error: {e}")

    async def _get_chats(self, user_id: str) -> list[dict]:
        try:
            r = await self._get_http().get(f"{self.memory_url}/api/v1/chats/{user_id}")
            if r.status_code == 200:
                return r.json().get("chats", [])
        except Exception as e:
            logger.debug(f"get_chats error: {e}")
        return []

    async def _create_chat(
        self, user_id: str, name: str, model_id: str | None = None
    ) -> str | None:
        try:
            r = await self._get_http().post(
                f"{self.memory_url}/api/v1/chats/{user_id}",
                json={"name": name, "model_id": model_id},
            )
            if r.status_code == 200:
                return r.json().get("chat_id")
        except Exception as e:
            logger.debug(f"create_chat error: {e}")
        return None

    async def _rename_chat(self, user_id: str, chat_id: str, name: str) -> bool:
        try:
            r = await self._get_http().put(
                f"{self.memory_url}/api/v1/chats/{user_id}/{chat_id}/name",
                json={"name": name},
            )
            return r.status_code == 200
        except Exception as e:
            logger.debug(f"rename_chat error: {e}")
        return False

    async def _get_chat_model(self, user_id: str, chat_id: str) -> str | None:
        try:
            r = await self._get_http().get(
                f"{self.memory_url}/api/v1/chats/{user_id}/{chat_id}/model"
            )
            if r.status_code == 200:
                return r.json().get("model_id")
        except Exception as e:
            logger.debug(f"get_chat_model error: {e}")
        return None

    async def _set_chat_model(self, user_id: str, chat_id: str, model_id: str) -> bool:
        try:
            r = await self._get_http().put(
                f"{self.memory_url}/api/v1/chats/{user_id}/{chat_id}/model",
                json={"model_id": model_id},
            )
            return r.status_code == 200
        except Exception as e:
            logger.debug(f"set_chat_model error: {e}")
        return False

    def _model_display_name(self, model_id: str | None) -> str:
        if not model_id:
            return "default"
        for m in _load_active_models():
            if m.get("id") == model_id:
                return m.get("display_name", model_id)
        return model_id.split("/")[-1] if "/" in model_id else model_id

    async def _get_chat_agent(self, user_id: str, chat_id: str) -> str:
        try:
            r = await self._get_http().get(
                f"{self.memory_url}/api/v1/chats/{user_id}/{chat_id}/agent"
            )
            if r.status_code == 200:
                return r.json().get("agent_id", "orchestrator")
        except Exception as e:
            logger.debug(f"get_chat_agent error: {e}")
        return "orchestrator"

    async def _set_chat_agent(self, user_id: str, chat_id: str, agent_id: str) -> bool:
        try:
            r = await self._get_http().put(
                f"{self.memory_url}/api/v1/chats/{user_id}/{chat_id}/agent",
                json={"agent_id": agent_id},
            )
            return r.status_code == 200
        except Exception as e:
            logger.debug(f"set_chat_agent error: {e}")
        return False

    def _agent_display_info(self, agent_id: str | None) -> tuple[str, str]:
        """Return (emoji, display_name) for an agent_id."""
        aid = agent_id or "orchestrator"
        for a in _load_agents():
            if a.get("id") == aid:
                return a.get("emoji", "🤖"), a.get("display_name", aid)
        return "🤖", aid

    async def _get_chat_settings(self, user_id: str, chat_id: str) -> dict:
        """Return {debug: bool, mode: str} for a chat."""
        try:
            r = await self._get_http().get(
                f"{self.memory_url}/api/v1/chats/{user_id}/{chat_id}/settings"
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.debug(f"get_chat_settings error: {e}")
        return {"debug": False, "mode": "ask"}

    async def _set_chat_settings(self, user_id: str, chat_id: str, **kwargs) -> bool:
        """Update per-chat settings (debug=, mode=)."""
        try:
            r = await self._get_http().put(
                f"{self.memory_url}/api/v1/chats/{user_id}/{chat_id}/settings",
                json={k: v for k, v in kwargs.items() if v is not None},
            )
            return r.status_code == 200
        except Exception as e:
            logger.debug(f"set_chat_settings error: {e}")
        return False

    @staticmethod
    def _format_debug_trace(
        debug_events: list[dict],
        elapsed_ms: float | None,
        agent_prefix: str | None = None,
        batch: int | None = None,
    ) -> str:
        """
        Format orchestrator debug events into a compact HTML trace.

        Uses HTML parse mode so arbitrary tool output / model names / paths
        never break Telegram entity parsing (as they would in Markdown mode).
        Shows the active agent name in brackets so delegation is visible:
          [orchestrator] LLM round 1 → model
          [orchestrator] 🔧 delegate_to_agent ← agent='coder'…
          [coder] LLM round 1 → model
          [coder] 🔧 execute_command ← cmd='git status'

        agent_prefix: when showing streaming bg-task updates, prefix with agent name.
        batch: if set, shown as "(часть N)" for streaming batches.
        """
        import html as _html

        if not debug_events:
            return ""

        if agent_prefix and batch is not None:
            header = f"⚙️ <b>[{_html.escape(agent_prefix)}] трейс (часть {batch}):</b>"
        elif agent_prefix:
            header = f"⚙️ <b>[{_html.escape(agent_prefix)}] трейс:</b>"
        else:
            header = "⚙️ <b>Трейс выполнения:</b>"

        lines = [header]
        for ev in debug_events:
            t = ev.get("type")
            raw_agent = ev.get("agent", "")
            agent_tag = f"<b>[{_html.escape(raw_agent)}]</b> " if raw_agent else ""

            if t == "llm":
                model = _html.escape(str(ev.get("model", "?")))
                rnd = ev.get("round", "?")
                lines.append(f"  🤔 {agent_tag}LLM раунд {rnd} → <code>{model}</code>")
            elif t == "tool_start":
                name = _html.escape(str(ev.get("name", "?")))
                summary = _html.escape(str(ev.get("summary", "")))
                lines.append(f"  🔧 {agent_tag}<code>{name}</code> ← {summary}")
            elif t == "tool_done":
                ok = ev.get("ok", True)
                summary = _html.escape(str(ev.get("summary", "")))
                ms = ev.get("ms", 0)
                icon = "✅" if ok else "❌"
                lines.append(f"     {icon} → {summary} <i>({ms}ms)</i>")

        if elapsed_ms is not None:
            lines.append(f"  ⏱ Итого: <i>{elapsed_ms:.0f}ms</i>")
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Commands
    # -------------------------------------------------------------------------

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user: User | None = update.effective_user
        if not user:
            return

        # Ensure default chat exists
        chat_id = await self._get_active_chat(str(user.id))
        if not chat_id:
            new_id = await self._create_chat(str(user.id), "Основной чат")
            if new_id:
                await self._set_active_chat(str(user.id), new_id)

        text = (
            f"👋 Привет, *{user.first_name}*!\n\n"
            "Я *Balbes* — твой интеллектуальный ассистент.\n\n"
            "Просто напиши мне задачу или вопрос. Я умею:\n"
            "— искать в интернете\n"
            "— читать страницы по ссылке\n"
            "— выполнять команды на сервере\n"
            "— помнить контекст разговора\n"
            "— понимать голосовые сообщения\n\n"
            "Используй /help для списка команд."
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = (
            "📋 *Команды:*\n\n"
            "/agents — список агентов, переключить агента\n"
            "/chats — список чатов \\(ID, агент, модель\\), переключиться\n"
            "/newchat \\[название\\] — создать новый чат\n"
            "/rename название — переименовать текущий чат\n"
            "/model — выбрать модель для текущего чата\n"
            "/clear — очистить историю текущего чата\n"
            "/remember текст — сохранить в долгосрочную память\n"
            "/recall запрос — найти в долгосрочной памяти\n"
            "/heartbeat — запустить проверку сейчас\n"
            "/status — статус системы\n"
            "/help — эта справка\n\n"
            "🎤 *Голосовые сообщения* принимаются автоматически\\.\n"
            "📎 Отправь ссылку — прочту страницу\\.\n"
        )
        await update.message.reply_text(text, parse_mode="MarkdownV2")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            response = await self._get_http().get(f"{self.orchestrator_url}/api/v1/status")
            if response.status_code == 200:
                data = response.json()
                workspace_files = ", ".join(data.get("workspace_files", [])) or "—"
                text = (
                    f"✅ *Статус:* {data.get('status', 'unknown').upper()}\n\n"
                    f"🔗 *Сервисы:*\n"
                    f"— Memory: `{data.get('services', {}).get('memory_service', '?')}`\n"
                    f"— Skills: `{data.get('services', {}).get('skills_registry', '?')}`\n\n"
                    f"📁 *Workspace:* {workspace_files}\n"
                    f"⏰ {data.get('timestamp', '')}"
                )
                await update.message.reply_text(text, parse_mode="Markdown")
            else:
                await update.message.reply_text(f"⚠️ Status: {response.status_code}")
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка: `{type(e).__name__}: {e or '(нет описания)'}`", parse_mode="Markdown"
            )

    async def cmd_chats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user: User | None = update.effective_user
        if not user:
            return

        chats = await self._get_chats(str(user.id))
        active_id = await self._get_active_chat(str(user.id))

        if not chats:
            await update.message.reply_text("У тебя пока нет чатов. Создай первый с /newchat")
            return

        lines = ["📋 *Твои чаты:*\n"]
        buttons = []
        for i, chat in enumerate(chats, 1):
            cid = chat["chat_id"]
            name = chat.get("name", "Без названия")
            model = self._model_display_name(chat.get("model_id"))
            agent_emoji, agent_name = self._agent_display_info(chat.get("agent_id"))
            short_id = cid[:8]
            is_active = cid == active_id

            mark = "✅ " if is_active else f"{i}\\."
            lines.append(
                f"{mark} *{_escape_md2(name)}*\n"
                f"   `{short_id}` \\| {agent_emoji} {_escape_md2(agent_name)} \\| 🔧 {_escape_md2(model)}"
            )

            btn_label = f"{'✅ ' if is_active else ''}{name} [{agent_emoji} {model}]"
            buttons.append(
                [InlineKeyboardButton(btn_label, callback_data=f"{CALLBACK_CHAT_PREFIX}{cid}")]
            )

        buttons.append([InlineKeyboardButton("➕ Новый чат", callback_data=CALLBACK_NEW_CHAT)])
        keyboard = InlineKeyboardMarkup(buttons)

        info_text = "\n\n".join(lines) + "\n\nНажми, чтобы переключиться:"
        await update.message.reply_text(
            info_text,
            reply_markup=keyboard,
            parse_mode="MarkdownV2",
        )

    async def cmd_newchat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user: User | None = update.effective_user
        if not user:
            return

        args = context.args
        name = " ".join(args) if args else "Новый чат"

        chat_id = await self._create_chat(str(user.id), name)
        if chat_id:
            await self._set_active_chat(str(user.id), chat_id)
            await update.message.reply_text(
                f"✅ Создан и активирован чат *{name}*", parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Не удалось создать чат")

    async def cmd_rename(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user: User | None = update.effective_user
        if not user:
            return

        args = context.args
        if not args:
            await update.message.reply_text("Использование: /rename Новое название")
            return

        name = " ".join(args)
        chat_id = await self._get_active_chat(str(user.id))
        if not chat_id:
            await update.message.reply_text("❌ Нет активного чата")
            return

        ok = await self._rename_chat(str(user.id), chat_id, name)
        if ok:
            await update.message.reply_text(f"✅ Чат переименован: *{name}*", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Не удалось переименовать")

    async def cmd_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user: User | None = update.effective_user
        if not user:
            return

        args = context.args

        chat_id = await self._get_active_chat(str(user.id))
        if not chat_id:
            await update.message.reply_text("❌ Нет активного чата. Используй /newchat")
            return

        if args:
            # Direct set: /model <id>
            model_id = args[0]
            ok = await self._set_chat_model(str(user.id), chat_id, model_id)
            if ok:
                name = self._model_display_name(model_id)
                await update.message.reply_text(
                    f"✅ Модель для текущего чата: *{name}*", parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Не удалось установить модель")
            return

        # Show keyboard
        current_model = await self._get_chat_model(str(user.id), chat_id)
        current_name = self._model_display_name(current_model)
        keyboard = _make_model_keyboard()
        await update.message.reply_text(
            f"🤖 *Выбери модель для текущего чата*\nСейчас: _{current_name}_",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

    async def cmd_agents(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user: User | None = update.effective_user
        if not user:
            return

        chat_id = await self._get_active_chat(str(user.id))
        current_agent_id = "orchestrator"
        if chat_id:
            current_agent_id = await self._get_chat_agent(str(user.id), chat_id)

        agent_emoji, agent_name = self._agent_display_info(current_agent_id)
        keyboard = _make_agent_keyboard(current_id=current_agent_id)

        agents = _load_agents()
        agent_lines = []
        for a in agents:
            mark = "✅ " if a.get("id") == current_agent_id else "   "
            e = a.get("emoji", "🤖")
            desc = a.get("description", "")
            agent_lines.append(f"{mark}{e} *{a.get('display_name', a['id'])}* — {desc}")

        text = (
            "🤖 *Агенты:*\n\n"
            + "\n".join(agent_lines)
            + f"\n\nТекущий: {agent_emoji} _{agent_name}_\nВыбери агента для этого чата:"
        )
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

    async def cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user: User | None = update.effective_user
        if not user:
            return

        chat_id = await self._get_active_chat(str(user.id))
        if not chat_id:
            await update.message.reply_text("❌ Нет активного чата")
            return

        try:
            r = await self._get_http().delete(
                f"{self.memory_url}/api/v1/history/{user.id}/{chat_id}"
            )
            if r.status_code in (200, 204):
                await update.message.reply_text("✅ История чата очищена")
            else:
                await update.message.reply_text(f"⚠️ Ошибка: {r.status_code}")
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка: `{type(e).__name__}: {e or '(нет описания)'}`", parse_mode="Markdown"
            )

    async def cmd_remember(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user: User | None = update.effective_user
        if not user:
            return

        args = context.args
        if not args:
            await update.message.reply_text(
                "Использование: /remember текст который нужно запомнить"
            )
            return

        text = " ".join(args)
        try:
            r = await self._get_http().post(
                f"{self.memory_url}/api/v1/memory",
                json={
                    "agent_id": str(user.id),
                    "content": text,
                    "memory_type": "user_memory",
                    "importance": 0.9,
                    "metadata": {"source": "telegram_command"},
                },
            )
            if r.status_code == 200:
                await update.message.reply_text(
                    f"💾 Сохранено в долгосрочную память:\n_{text[:200]}_",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(f"⚠️ Не удалось сохранить: {r.status_code}")
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка: `{type(e).__name__}: {e or '(нет описания)'}`", parse_mode="Markdown"
            )

    async def cmd_recall(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user: User | None = update.effective_user
        if not user:
            return

        args = context.args
        if not args:
            await update.message.reply_text("Использование: /recall запрос")
            return

        query = " ".join(args)
        try:
            r = await self._get_http().post(
                f"{self.memory_url}/api/v1/memory/search",
                json={
                    "agent_id": str(user.id),
                    "query": query,
                    "limit": 3,
                },
            )
            if r.status_code == 200:
                results = r.json().get("results", [])
                if not results:
                    await update.message.reply_text("🔍 Ничего не найдено в памяти")
                    return
                lines = [f"🔍 *Результаты поиска:* _{query}_\n"]
                for i, res in enumerate(results, 1):
                    score = res.get("score", 0)
                    content = res.get("content", "")[:200]
                    lines.append(f"{i}. [{score:.2f}] {content}")
                await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            else:
                await update.message.reply_text(f"⚠️ Ошибка поиска: {r.status_code}")
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка: `{type(e).__name__}: {e or '(нет описания)'}`", parse_mode="Markdown"
            )

    async def cmd_heartbeat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Manually trigger a heartbeat check right now."""
        user: User | None = update.effective_user
        if not user:
            return

        cfg = _load_heartbeat_config()
        if not cfg["enabled"]:
            await update.message.reply_text(
                "⏸ Heartbeat отключён.\n"
                "Включи в `config/providers.yaml` → `heartbeat.enabled: true`",
                parse_mode="Markdown",
            )
            return

        await update.message.reply_text("🔄 Запускаю heartbeat проверку...")
        try:
            await self._run_heartbeat(cfg)
            await update.message.reply_text("✅ Heartbeat выполнен")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка heartbeat: {e}")

    async def cmd_debug(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Toggle debug trace mode for the current chat."""
        user: User | None = update.effective_user
        if not user:
            return
        user_id = str(user.id)
        chat_id = await self._get_active_chat(user_id)
        if not chat_id:
            await update.message.reply_text("❌ Нет активного чата. Создай через /newchat")
            return

        current = await self._get_chat_settings(user_id, chat_id)
        new_debug = not current.get("debug", False)
        await self._set_chat_settings(user_id, chat_id, debug=new_debug)

        if new_debug:
            await update.message.reply_text(
                "🔍 *Debug включён*\n"
                "После каждого ответа я буду показывать что делал:\n"
                "LLM-запросы, инструменты, время выполнения.\n\n"
                "Отключить: /debug",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text("🔕 Debug выключен")

    async def cmd_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show current execution mode and offer to switch between agent/ask."""
        user: User | None = update.effective_user
        if not user:
            return
        user_id = str(user.id)
        chat_id = await self._get_active_chat(user_id)
        if not chat_id:
            await update.message.reply_text("❌ Нет активного чата. Создай через /newchat")
            return

        current = await self._get_chat_settings(user_id, chat_id)
        mode = current.get("mode", "ask")

        mode_text = {
            "agent": "🤖 *Agent* — агент может выполнять команды на сервере",
            "ask": "📝 *Ask* — агент только пишет и советует, без выполнения команд",
        }.get(mode, mode)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🤖 Agent", callback_data="mode_set:agent"),
                    InlineKeyboardButton("📝 Ask", callback_data="mode_set:ask"),
                ]
            ]
        )
        await update.message.reply_text(
            f"Текущий режим: {mode_text}\n\nВыбери режим:",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

    async def cb_mode_set(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle mode selection callback."""
        query = update.callback_query
        await query.answer()
        user = update.effective_user
        if not user:
            return

        new_mode = query.data.split(":", 1)[1]  # "mode_set:agent" → "agent"
        user_id = str(user.id)
        chat_id = await self._get_active_chat(user_id)
        if not chat_id:
            return

        await self._set_chat_settings(user_id, chat_id, mode=new_mode)

        labels = {"agent": "🤖 Agent — команды разрешены", "ask": "📝 Ask — только чтение"}
        label = labels.get(new_mode, new_mode)
        await query.edit_message_text(f"✅ Режим переключён: {label}")

    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Cancel the currently running agent task for this user."""
        user: User | None = update.effective_user
        if not user:
            return

        user_id = str(user.id)
        task = self._active_tasks.get(user_id)

        # Also cancel all background monitors for this user
        monitor_keys = [k for k in self._bg_monitors if k.startswith(f"{user_id}:")]
        for k in monitor_keys:
            mon = self._bg_monitors.pop(k, None)
            if mon and not mon.done():
                mon.cancel()

        if not task or task.done():
            if monitor_keys:
                await update.message.reply_text(
                    f"✋ Остановлены фоновые мониторы: {', '.join(k.split(':')[1] for k in monitor_keys)}"
                )
            else:
                await update.message.reply_text("✅ Нет активных задач для остановки")
            return

        # Cancel the bot-side asyncio task (interrupts the HTTP wait immediately)
        task.cancel()

        # Also signal the orchestrator to stop processing between tool rounds
        await self._cancel_orchestrator_task(user_id)

        await update.message.reply_text("✋ Остановлено")

    async def cmd_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show recent tasks from all agents."""
        user: User | None = update.effective_user
        if not user:
            return
        user_id = str(user.id)
        chat_id = await self._get_active_chat(user_id)

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.orchestrator_url}/api/v1/tasks",
                    params={"user_id": user_id, "limit": 20},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            await update.message.reply_text(f"❌ Не удалось получить список задач: {e}")
            return

        tasks = data.get("tasks", [])
        if not tasks:
            await update.message.reply_text("📋 Нет задач в реестре.")
            return

        STATUS_ICON = {
            "running": "⏳",
            "completed": "✅",
            "cancelled": "🚫",
            "error": "❌",
        }

        lines = [f"<b>📋 Задачи проекта</b> ({len(tasks)}):\n"]
        for t in tasks:
            icon = STATUS_ICON.get(t.get("status", ""), "❓")
            agent = t.get("agent_id", "?")
            status_label = t.get("status", "?")
            bg_label = " <i>[bg]</i>" if t.get("background") else ""
            dur = t.get("duration_ms")
            dur_str = f" <code>{dur}ms</code>" if dur else ""
            started = (t.get("started_at") or "")[:16].replace("T", " ")
            desc = (t.get("description") or "")[:90]
            desc_safe = desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(
                f"{icon} <b>[{agent}]</b>{bg_label} — {status_label}{dur_str}\n"
                f"   🕐 {started}\n"
                f"   📝 {desc_safe}\n"
            )

        # Start monitors for any running bg tasks visible in /tasks
        chat_settings = await self._get_chat_settings(user_id, chat_id or "default")
        debug_on = chat_settings.get("debug", False) if chat_id else False
        for t in tasks:
            if t.get("status") == "running" and t.get("background"):
                agent_id = t.get("agent_id", "")
                if agent_id:
                    key = f"{user_id}:{agent_id}"
                    mon = self._bg_monitors.get(key)
                    if not mon or mon.done():
                        self._start_bg_monitor(
                            update.effective_chat.id, user_id, agent_id, debug_on
                        )

        text = "\n".join(lines)
        await update.message.reply_text(text, parse_mode="HTML")

    async def _ensure_bg_monitors(self, user_id: str, tg_chat_id: int, debug: bool) -> None:
        """
        Scan for any running background tasks that don't have an active monitor
        and start one for each. Called after every orchestrator response as a
        safety net in case background_tasks_started wasn't populated.
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{self.orchestrator_url}/api/v1/tasks",
                    params={"user_id": user_id, "limit": 10},
                )
                if resp.status_code != 200:
                    return
                tasks = resp.json().get("tasks", [])
        except Exception as e:
            logger.debug(f"[ensure_bg_monitors] error: {e}")
            return

        for task in tasks:
            if task.get("status") == "running" and task.get("background"):
                agent_id = task.get("agent_id", "")
                if not agent_id:
                    continue
                key = f"{user_id}:{agent_id}"
                mon = self._bg_monitors.get(key)
                if not mon or mon.done():
                    logger.info(f"[ensure_bg_monitors] starting missed monitor for {key}")
                    self._start_bg_monitor(tg_chat_id, user_id, agent_id, debug)

    def _start_fg_monitor(
        self,
        tg_chat_id: int,
        user_id: str,
        agent_id: str,
    ) -> asyncio.Task:
        """
        Spawn a lightweight monitor for a FOREGROUND task.
        Polls /api/v1/tasks/fg/events every 5s and sends debug trace batches to Telegram.
        Returns the asyncio.Task so the caller can cancel it when the main POST returns.
        """

        async def _fg_monitor_loop() -> None:
            batch_num = 0
            poll_interval = 5
            while True:
                await asyncio.sleep(poll_interval)
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.get(
                            f"{self.orchestrator_url}/api/v1/tasks/fg/events",
                            params={"user_id": user_id, "agent_id": agent_id},
                        )
                        if resp.status_code != 200:
                            continue
                        data = resp.json()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.debug(f"[fgmon] poll error: {e}")
                    continue

                events = data.get("events", [])
                if events:
                    batch_num += 1
                    trace = self._format_debug_trace(
                        events,
                        elapsed_ms=None,
                        agent_prefix=agent_id,
                        batch=batch_num,
                    )
                    if trace:
                        try:
                            if self.app:
                                await self.app.bot.send_message(
                                    tg_chat_id, trace, parse_mode="HTML"
                                )
                        except Exception as e:
                            logger.debug(f"[fgmon] send failed: {e}")

                if not data.get("running", True):
                    break  # task finished, main POST will handle final result

        task = asyncio.create_task(_fg_monitor_loop(), name=f"fgmon-{user_id}:{agent_id}")
        return task

    def _start_bg_monitor(
        self,
        tg_chat_id: int,
        user_id: str,
        agent_id: str,
        debug: bool,
    ) -> None:
        """Spawn an asyncio task that polls the background agent and reports to Telegram."""
        key = f"{user_id}:{agent_id}"
        existing = self._bg_monitors.get(key)
        if existing and not existing.done():
            return  # already monitoring this agent for this user
        self._bg_monitor_chat[key] = tg_chat_id
        task = asyncio.create_task(
            self._bg_monitor_loop(tg_chat_id, user_id, agent_id, debug),
            name=f"bgmon-{key}",
        )
        self._bg_monitors[key] = task

    async def _bg_monitor_loop(
        self,
        tg_chat_id: int,
        user_id: str,
        agent_id: str,
        debug: bool,
    ) -> None:
        """
        Poll orchestrator every 5 seconds for debug events and completion status.
        Sends live debug traces to the Telegram chat; auto-sends final result on done.
        """
        key = f"{user_id}:{agent_id}"
        batch_num = 0
        poll_interval = 5  # seconds

        try:
            while True:
                await asyncio.sleep(poll_interval)

                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.get(
                            f"{self.orchestrator_url}/api/v1/tasks/bg/events",
                            params={"user_id": user_id, "agent_id": agent_id},
                        )
                        if resp.status_code != 200:
                            logger.warning(f"[bgmon] poll returned {resp.status_code} for {key}")
                            continue
                        data = resp.json()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(f"[bgmon] poll error for {key}: {e}")
                    continue

                events = data.get("events", [])
                current_status = data.get("status", "running")

                # Send debug trace batch if debug is on and there are new events
                if debug and events:
                    batch_num += 1
                    trace = self._format_debug_trace(
                        events,
                        elapsed_ms=None,
                        agent_prefix=agent_id,
                        batch=batch_num,
                    )
                    if trace:
                        try:
                            await self.app.bot.send_message(tg_chat_id, trace, parse_mode="HTML")
                        except Exception as e:
                            logger.warning(f"[bgmon] debug send failed: {e}")

                if current_status != "running":
                    # Final poll — consume the result
                    try:
                        async with httpx.AsyncClient(timeout=10) as client:
                            final_resp = await client.get(
                                f"{self.orchestrator_url}/api/v1/tasks/bg/events",
                                params={
                                    "user_id": user_id,
                                    "agent_id": agent_id,
                                    "consume_result": "true",
                                },
                            )
                            final_data = (
                                final_resp.json() if final_resp.status_code == 200 else data
                            )
                    except Exception:
                        final_data = data

                    # Send any remaining events
                    last_events = final_data.get("events", [])
                    if debug and last_events:
                        batch_num += 1
                        trace = self._format_debug_trace(
                            last_events,
                            elapsed_ms=None,
                            agent_prefix=agent_id,
                            batch=batch_num,
                        )
                        if trace:
                            try:
                                await self.app.bot.send_message(
                                    tg_chat_id, trace, parse_mode="HTML"
                                )
                            except Exception:
                                pass

                    # Send final result
                    result_text = final_data.get("result") or ""
                    status_label = final_data.get("status", current_status)
                    finished_at = (final_data.get("finished_at") or "")[:16].replace("T", " ")

                    # Don't relay the internal fallback text — it's not a real result
                    _fallback = "Не смог обработать запрос."
                    if result_text.startswith(_fallback):
                        result_text = ""

                    if status_label == "completed":
                        header = f"✅ <b>[{agent_id}]</b> завершил задачу"
                    elif status_label == "cancelled":
                        header = f"🚫 <b>[{agent_id}]</b> задача отменена"
                    else:
                        header = f"❌ <b>[{agent_id}]</b> задача завершилась с ошибкой"

                    if finished_at:
                        header += f" <i>({finished_at})</i>"
                    if not result_text and status_label == "completed":
                        header += " <i>(результат в логах)</i>"

                    try:
                        await self.app.bot.send_message(tg_chat_id, header, parse_mode="HTML")
                    except Exception:
                        pass

                    if result_text:
                        try:
                            await self.app.bot.send_message(
                                tg_chat_id, result_text, parse_mode="Markdown"
                            )
                        except Exception:
                            try:
                                await self.app.bot.send_message(tg_chat_id, result_text)
                            except Exception:
                                pass
                    break

        except asyncio.CancelledError:
            logger.info(f"[bgmon] monitor cancelled for {key}")
        finally:
            self._bg_monitors.pop(key, None)
            self._bg_monitor_chat.pop(key, None)

    async def _cancel_orchestrator_task(self, user_id: str) -> None:
        """Send a cancel signal to the orchestrator for this user."""
        try:
            await self._get_http().post(
                f"{self.orchestrator_url}/api/v1/tasks/cancel",
                params={"user_id": user_id},
                timeout=5.0,
            )
        except Exception as e:
            logger.debug(f"Orchestrator cancel signal failed (non-critical): {e}")

    # -------------------------------------------------------------------------
    # Callback handlers
    # -------------------------------------------------------------------------

    async def cb_chat_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        if not user:
            return

        chat_id = query.data[len(CALLBACK_CHAT_PREFIX) :]
        await self._set_active_chat(str(user.id), chat_id)

        model = await self._get_chat_model(str(user.id), chat_id)
        model_name = self._model_display_name(model)
        agent_id = await self._get_chat_agent(str(user.id), chat_id)
        agent_emoji, agent_name = self._agent_display_info(agent_id)
        short_id = chat_id[:8]

        await query.edit_message_text(
            f"✅ Чат активирован\nID: `{short_id}` | {agent_emoji} {agent_name} | 🔧 {model_name}",
            parse_mode="Markdown",
        )

    async def cb_model_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        if not user:
            return

        model_id = query.data[len(CALLBACK_MODEL_PREFIX) :]
        chat_id = await self._get_active_chat(str(user.id))
        if not chat_id:
            await query.edit_message_text("❌ Нет активного чата")
            return

        ok = await self._set_chat_model(str(user.id), chat_id, model_id)
        model_name = self._model_display_name(model_id)

        if ok:
            await query.edit_message_text(
                f"✅ Модель установлена: *{model_name}*",
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text("❌ Не удалось установить модель")

    async def cb_new_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        if not user:
            return

        chat_id = await self._create_chat(str(user.id), "Новый чат")
        if chat_id:
            await self._set_active_chat(str(user.id), chat_id)
            await query.edit_message_text(
                "✅ Создан новый чат.\n"
                "Используй /rename чтобы дать ему название, "
                "или /model чтобы выбрать модель."
            )
        else:
            await query.edit_message_text("❌ Не удалось создать чат")

    async def cb_agent_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        if not user:
            return

        agent_id = query.data[len(CALLBACK_AGENT_PREFIX) :]
        chat_id = await self._get_active_chat(str(user.id))
        if not chat_id:
            await query.edit_message_text("❌ Нет активного чата. Создай его через /newchat")
            return

        ok = await self._set_chat_agent(str(user.id), chat_id, agent_id)
        agent_emoji, agent_name = self._agent_display_info(agent_id)

        if ok:
            await query.edit_message_text(
                f"✅ Агент переключён: {agent_emoji} *{agent_name}*\n"
                "Следующее сообщение пойдёт этому агенту.",
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text("❌ Не удалось переключить агента")

    async def cb_model_unavail(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle 'Model unavailable — switch?' inline response."""
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        if not user:
            return

        data = query.data  # model_unavail:yes:{model_id} | model_unavail:no
        if data.startswith("model_unavail:yes:"):
            new_model_id = data[len("model_unavail:yes:") :]
            chat_id = await self._get_active_chat(str(user.id))
            if chat_id:
                await self._set_chat_model(str(user.id), chat_id, new_model_id)
                model_name = self._model_display_name(new_model_id)
                await query.edit_message_text(
                    f"✅ Переключено на: *{model_name}*\nПовтори свой запрос.",
                    parse_mode="Markdown",
                )
        else:
            await query.edit_message_text(
                "Ок. Попробуй позже или выбери другую модель через /model"
            )

    # -------------------------------------------------------------------------
    # Message handlers
    # -------------------------------------------------------------------------

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular text messages."""
        user: User | None = update.effective_user
        message = update.message
        if not user or not message or not message.text:
            return

        user_id = str(user.id)
        self._active_tasks[user_id] = asyncio.current_task()  # type: ignore[assignment]
        try:
            await self._process_user_input(
                update=update,
                context=context,
                user=user,
                text=message.text,
            )
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await message.reply_text("✋ Выполнение остановлено")
        finally:
            self._active_tasks.pop(user_id, None)

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle voice / audio messages — transcribe then process as text."""
        user: User | None = update.effective_user
        message = update.message
        if not user or not message:
            return

        user_id = str(user.id)
        self._active_tasks[user_id] = asyncio.current_task()  # type: ignore[assignment]

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )

        try:
            # Download voice file
            voice = message.voice or message.audio
            if not voice:
                return
            file = await context.bot.get_file(voice.file_id)
            ogg_bytes = bytes(await file.download_as_bytearray())

            # Transcribe
            from skills.whisper_transcribe import correct_transcription, transcribe_voice

            raw_text = await transcribe_voice(ogg_bytes)

            if not raw_text.strip():
                await message.reply_text("🎤 Не удалось распознать голосовое сообщение")
                return

            # Correct via LLM
            corrected = await correct_transcription(raw_text, http_client=self.http_client)

            # Show what was heard
            await message.reply_text(
                f"🎤 _Услышал:_ «{corrected}»",
                parse_mode="Markdown",
            )

            # Process as regular text message
            await self._process_user_input(
                update=update,
                context=context,
                user=user,
                text=corrected,
            )

        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await message.reply_text("✋ Выполнение остановлено")
        except RuntimeError as e:
            if "ffmpeg" in str(e).lower():
                await message.reply_text(
                    "❌ ffmpeg не установлен. Запусти: `sudo apt install ffmpeg`",
                    parse_mode="Markdown",
                )
            else:
                await message.reply_text(f"❌ Ошибка транскрипции: {e}")
        except ImportError:
            await message.reply_text(
                "❌ faster-whisper не установлен. Запусти: `pip install faster-whisper`",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Voice handling failed: {e}", exc_info=True)
            await message.reply_text(
                f"❌ Ошибка обработки голоса: `{type(e).__name__}: {e or '(нет описания)'}`",
                parse_mode="Markdown",
            )
        finally:
            self._active_tasks.pop(user_id, None)

    async def _process_user_input(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user: User,
        text: str,
    ) -> None:
        """Send user input to orchestrator and deliver the response."""
        message = update.message
        chat_tg = update.effective_chat

        # Resolve active chat
        chat_id = await self._get_active_chat(str(user.id))
        if not chat_id:
            new_id = await self._create_chat(str(user.id), "Основной чат")
            if new_id:
                await self._set_active_chat(str(user.id), new_id)
                chat_id = new_id

        lock = self._get_lock(str(user.id), chat_id or "default")

        async with lock:
            typing_task: asyncio.Task | None = None
            try:
                # Typing indicator
                async def typing_loop() -> None:
                    while True:
                        await context.bot.send_chat_action(
                            chat_id=chat_tg.id, action=ChatAction.TYPING
                        )
                        await asyncio.sleep(4)

                if chat_tg:
                    typing_task = asyncio.create_task(typing_loop())

                # Load per-chat settings (debug, mode)
                chat_settings = {"debug": False, "mode": "ask"}
                if chat_id:
                    chat_settings = await self._get_chat_settings(str(user.id), chat_id)

                # Send to orchestrator
                params = {
                    "user_id": str(user.id),
                    "description": text,
                    "debug": chat_settings.get("debug", False),
                    "mode": chat_settings.get("mode", "ask"),
                }
                if chat_id:
                    params["chat_id"] = chat_id
                    agent_id = await self._get_chat_agent(str(user.id), chat_id)
                    if agent_id:
                        params["agent_id"] = agent_id

                # Start live trace monitor for foreground tasks when debug is on
                fg_monitor: asyncio.Task | None = None
                _active_agent_id = params.get("agent_id", "orchestrator")
                if chat_settings.get("debug") and chat_tg:
                    fg_monitor = self._start_fg_monitor(
                        tg_chat_id=chat_tg.id,
                        user_id=str(user.id),
                        agent_id=_active_agent_id,
                    )

                response = await self._get_http().post(
                    f"{self.orchestrator_url}/api/v1/tasks",
                    params=params,
                    timeout=120.0,
                )

                # Stop fg monitor — task is done, final trace comes from the response
                if fg_monitor and not fg_monitor.done():
                    fg_monitor.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await fg_monitor

                if response.status_code == 200:
                    result = response.json()

                    if result.get("status") == "success":
                        payload = result.get("result", {})
                        if isinstance(payload, dict):
                            result_text = str(
                                payload.get("output") or payload.get("result") or ""
                            ).strip()
                        else:
                            result_text = str(payload).strip()
                        if not result_text:
                            result_text = "Готово."

                        # Send debug trace before the main response (HTML mode — safe for any content)
                        debug_events = result.get("debug_events")
                        if debug_events:
                            trace = self._format_debug_trace(
                                debug_events,
                                elapsed_ms=result.get("duration_ms"),
                            )
                            if trace:
                                try:
                                    await message.reply_text(trace, parse_mode="HTML")
                                except Exception:
                                    await message.reply_text(trace)

                        # Start background monitors for newly delegated agents
                        bg_started = result.get("background_tasks_started", [])
                        debug_on = chat_settings.get("debug", False)
                        for bg in bg_started:
                            self._start_bg_monitor(
                                tg_chat_id=chat_tg.id,
                                user_id=str(user.id),
                                agent_id=bg["agent_id"],
                                debug=debug_on,
                            )

                        # Catch-all: also start monitors for any running bg tasks
                        # that don't have a monitor yet (handles cases where
                        # background_tasks_started was not populated, e.g. on restart
                        # or when the LLM called the tool in a previous turn).
                        await self._ensure_bg_monitors(
                            user_id=str(user.id),
                            tg_chat_id=chat_tg.id,
                            debug=debug_on,
                        )
                    else:
                        error = result.get("error", "")
                        # Check if it's a model unavailability error
                        if "429" in error or "unavailable" in error.lower():
                            await self._prompt_model_switch(
                                update=update,
                                user_id=str(user.id),
                                chat_id=chat_id or "default",
                                error=error,
                            )
                            return
                        # Show the actual error from the orchestrator
                        err_msg = error or "Неизвестная ошибка оркестратора"
                        result_text = f"❌ Ошибка агента:\n`{err_msg}`"

                    # LLM responses may contain arbitrary Markdown — try V1, fall back to plain
                    try:
                        await message.reply_text(result_text, parse_mode="Markdown")
                    except Exception:
                        await message.reply_text(result_text)

                else:
                    # Non-200: try to read the body for details
                    try:
                        body = response.json()
                        detail = body.get("detail") or body.get("error") or str(body)
                    except Exception:
                        detail = response.text[:200] or "(нет тела ответа)"
                    await message.reply_text(
                        f"❌ Ошибка запроса: HTTP {response.status_code}\n`{detail}`",
                        parse_mode="Markdown",
                    )

            except Exception as e:
                logger.error(f"Message processing failed: {e}", exc_info=True)
                err_type = type(e).__name__
                err_msg = str(e) or "(нет описания)"
                try:
                    await message.reply_text(
                        f"❌ Ошибка: `{err_type}: {err_msg}`",
                        parse_mode="Markdown",
                    )
                except Exception:
                    await message.reply_text(f"❌ Ошибка: {err_type}: {err_msg}")
            finally:
                if typing_task:
                    typing_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await typing_task

    async def _prompt_model_switch(
        self,
        update: Update,
        user_id: str,
        chat_id: str,
        error: str,
    ) -> None:
        """Notify user about model unavailability and offer to switch."""
        models = _load_active_models()
        current_model = await self._get_chat_model(user_id, chat_id)

        # Suggest first available model that isn't current
        fallback = next(
            (m for m in models if m.get("id") != current_model),
            None,
        )

        if fallback:
            fallback_id = fallback["id"]
            fallback_name = fallback.get("display_name", fallback_id)
            current_name = self._model_display_name(current_model)

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            f"✅ Да, переключить на {fallback_name}",
                            callback_data=f"model_unavail:yes:{fallback_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ Нет",
                            callback_data=CALLBACK_MODEL_UNAVAIL_NO,
                        )
                    ],
                ]
            )
            await update.message.reply_text(
                f"⚠️ Модель *{current_name}* недоступна.\nПереключиться на *{fallback_name}*?",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "⚠️ Выбранная модель недоступна. Попробуй позже или выбери другую через /model"
            )


def run_bot() -> None:
    """Entry point: run Telegram bot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured, skipping")
        return

    bot = BalbesTelegramBot()
    bot.initialize()
    bot.start_polling()


if __name__ == "__main__":
    run_bot()
