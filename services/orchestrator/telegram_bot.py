"""
Telegram Bot for Balbes Multi-Agent System.

Commands:
  /start          — welcome message
  /help           — command reference
  /status         — orchestrator health check
  /chats          — list chats (inline keyboard), switch active chat
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
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from shared.config import get_settings

settings = get_settings()
logger = logging.getLogger("orchestrator.telegram")

CALLBACK_CHAT_PREFIX = "chat:"
CALLBACK_MODEL_PREFIX = "model:"
CALLBACK_NEW_CHAT = "new_chat"
CALLBACK_MODEL_UNAVAIL_YES = "model_unavail:yes:"
CALLBACK_MODEL_UNAVAIL_NO = "model_unavail:no"


def _load_active_models() -> list[dict]:
    """Load active_models list from providers.yaml."""
    try:
        import yaml

        cfg_path = Path(__file__).parent.parent.parent / "config" / "providers.yaml"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data.get("active_models", [])
    except Exception as e:
        logger.warning(f"Failed to load active_models: {e}")
    return []


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

    def initialize(self) -> None:
        """Initialize Telegram bot application."""
        logger.info("Initializing Telegram bot...")
        self.app = (
            Application.builder()
            .token(self.token)
            .concurrent_updates(False)  # sequential — required for correct state handling
            .build()
        )
        self._setup_handlers()
        logger.info("Telegram bot initialized")

    def start_polling(self) -> None:
        if not self.app:
            raise RuntimeError("Bot not initialized")
        logger.info("Starting bot polling...")
        self.app.run_polling(drop_pending_updates=True)

    def _setup_handlers(self) -> None:
        if not self.app:
            return

        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("clear", self.cmd_clear))
        self.app.add_handler(CommandHandler("chats", self.cmd_chats))
        self.app.add_handler(CommandHandler("newchat", self.cmd_newchat))
        self.app.add_handler(CommandHandler("rename", self.cmd_rename))
        self.app.add_handler(CommandHandler("model", self.cmd_model))
        self.app.add_handler(CommandHandler("remember", self.cmd_remember))
        self.app.add_handler(CommandHandler("recall", self.cmd_recall))

        # Inline keyboard callbacks
        self.app.add_handler(
            CallbackQueryHandler(self.cb_chat_selected, pattern=f"^{CALLBACK_CHAT_PREFIX}")
        )
        self.app.add_handler(
            CallbackQueryHandler(self.cb_model_selected, pattern=f"^{CALLBACK_MODEL_PREFIX}")
        )
        self.app.add_handler(
            CallbackQueryHandler(self.cb_new_chat, pattern=f"^{CALLBACK_NEW_CHAT}$")
        )
        self.app.add_handler(CallbackQueryHandler(self.cb_model_unavail, pattern="^model_unavail:"))

        # Voice messages
        self.app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.handle_voice))

        # Regular text messages
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def _set_commands(self) -> None:
        if not self.app:
            return
        commands = [
            BotCommand("start", "Начать работу"),
            BotCommand("help", "Справка по командам"),
            BotCommand("status", "Статус системы"),
            BotCommand("chats", "Список чатов / переключить"),
            BotCommand("newchat", "Создать новый чат"),
            BotCommand("rename", "Переименовать текущий чат"),
            BotCommand("model", "Выбрать модель для чата"),
            BotCommand("clear", "Очистить историю чата"),
            BotCommand("remember", "Сохранить в долгосрочную память"),
            BotCommand("recall", "Найти в долгосрочной памяти"),
        ]
        await self.app.bot.set_my_commands(commands)

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
            "/chats — список чатов, переключиться\n"
            "/newchat \\[название\\] — создать новый чат\n"
            "/rename название — переименовать текущий чат\n"
            "/model — выбрать модель для текущего чата\n"
            "/clear — очистить историю текущего чата\n"
            "/remember текст — сохранить в долгосрочную память\n"
            "/recall запрос — найти в долгосрочной памяти\n"
            "/status — статус системы\n"
            "/help — эта справка\n\n"
            "🎤 *Голосовые сообщения* принимаются автоматически.\n"
            "📎 Отправь ссылку — прочту страницу.\n"
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
            await update.message.reply_text(f"❌ Ошибка: {e}")

    async def cmd_chats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user: User | None = update.effective_user
        if not user:
            return

        chats = await self._get_chats(str(user.id))
        active_id = await self._get_active_chat(str(user.id))

        if not chats:
            await update.message.reply_text("У тебя пока нет чатов. Создай первый с /newchat")
            return

        buttons = []
        for chat in chats:
            cid = chat["chat_id"]
            name = chat.get("name", "Без названия")
            model = self._model_display_name(chat.get("model_id"))
            mark = "✅ " if cid == active_id else ""
            label = f"{mark}{name}  [{model}]"
            buttons.append(
                [InlineKeyboardButton(label, callback_data=f"{CALLBACK_CHAT_PREFIX}{cid}")]
            )

        buttons.append([InlineKeyboardButton("➕ Новый чат", callback_data=CALLBACK_NEW_CHAT)])
        keyboard = InlineKeyboardMarkup(buttons)

        await update.message.reply_text(
            "📋 *Твои чаты:*\nНажми, чтобы переключиться",
            reply_markup=keyboard,
            parse_mode="Markdown",
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
            await update.message.reply_text(f"❌ Ошибка: {e}")

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
            await update.message.reply_text(f"❌ Ошибка: {e}")

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
            await update.message.reply_text(f"❌ Ошибка: {e}")

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

        await query.edit_message_text(
            f"✅ Переключён на чат\nМодель: *{model_name}*",
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

        await self._process_user_input(
            update=update,
            context=context,
            user=user,
            text=message.text,
        )

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle voice / audio messages — transcribe then process as text."""
        user: User | None = update.effective_user
        message = update.message
        if not user or not message:
            return

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
            await message.reply_text(f"❌ Ошибка обработки голоса: {e}")

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

                # Send to orchestrator
                params = {"user_id": str(user.id), "description": text}
                if chat_id:
                    params["chat_id"] = chat_id

                response = await self._get_http().post(
                    f"{self.orchestrator_url}/api/v1/tasks",
                    params=params,
                    timeout=120.0,
                )

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
                        result_text = "Не удалось выполнить запрос. Попробуй уточнить."

                    await message.reply_text(result_text)

                else:
                    await message.reply_text(f"❌ Ошибка запроса: {response.status_code}")

            except Exception as e:
                logger.error(f"Message processing failed: {e}", exc_info=True)
                await message.reply_text(f"❌ Ошибка: {e}")
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
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured, skipping")
        return

    bot = BalbesTelegramBot()
    bot.initialize()
    bot.start_polling()


if __name__ == "__main__":
    run_bot()
