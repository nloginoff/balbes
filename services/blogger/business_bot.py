"""
Business bot — silent Telegram bot with dual role:
  1. In group chats: anonymizes and stores messages to business_messages table.
  2. In private chat with owner: handles evening check-in conversation and
     approval replies for personal blog posts.

SECURITY:
  - All private messages from non-owner users are silently ignored.
  - The bot never responds to strangers in private chats.
  - Group message processing is restricted to registered business_chats only.
  - Commands are only accepted from the owner (owner_tg_id check on every handler).
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import yaml
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .anonymizer import AnonymizationEngine

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


def _load_active_models() -> list[dict]:
    """Load active_models from config/providers.yaml (same list as orchestrator)."""
    cfg_path = _PROJECT_ROOT / "config" / "providers.yaml"
    try:
        with cfg_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("active_models", [])
    except Exception as exc:
        logger_mod = logging.getLogger("blogger.business_bot")
        logger_mod.warning("Could not load active_models from providers.yaml: %s", exc)
        return []


if TYPE_CHECKING:
    from .agent import BloggerAgent

logger = logging.getLogger("blogger.business_bot")

_TG_LIMIT = 4096


def _split_long(text: str, limit: int = _TG_LIMIT) -> list[str]:
    """Split text into Telegram-safe chunks."""
    if len(text) <= limit:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = start + limit
        if end < len(text):
            cut = text.rfind("\n", start, end)
            end = cut if cut > start else end
        chunks.append(text[start:end])
        start = end
    return chunks


# In-memory state: are we waiting for check-in reply from owner?
_WAITING_CHECKIN: dict[int, bool] = {}
# In-memory state: are we waiting for edit instructions for a post?
_WAITING_EDIT: dict[int, str | None] = {}  # owner_chat_id → post_id


class BusinessBot:
    """
    Wraps python-telegram-bot Application for the business monitoring bot.
    """

    def __init__(
        self,
        token: str,
        owner_tg_id: int,
        db: asyncpg.Pool,
        agent: "BloggerAgent",
    ):
        self.token = token
        self.owner_tg_id = owner_tg_id
        self.db = db
        self.agent = agent
        self._app: Application | None = None

    def _owner_filter(self) -> filters.BaseFilter:
        """Return a filter that passes only messages from the owner."""
        return filters.User(user_id=self.owner_tg_id)

    async def _post_init(self, app: Application) -> None:
        """Set bot commands menu visible in Telegram."""
        commands = [
            BotCommand("generate", "Сгенерировать пост по чатам"),
            BotCommand("drafts", "Черновики постов"),
            BotCommand("published", "Опубликованные посты"),
            BotCommand("queue", "Очередь на публикацию"),
            BotCommand("summary", "Бизнес-саммари за день"),
            BotCommand("model", "Выбрать LLM модель"),
            BotCommand("chats", "Список чатов / переключить"),
            BotCommand("newchat", "Создать новый чат"),
            BotCommand("rename", "Переименовать чат"),
            BotCommand("clear", "Очистить историю чата"),
            BotCommand("list_chats", "Зарегистрированные бизнес-группы"),
            BotCommand("help", "Справка"),
        ]
        try:
            await app.bot.set_my_commands(commands)
            logger.info("Bot commands menu updated (%d commands)", len(commands))
        except Exception as exc:
            logger.warning("Could not set bot commands: %s", exc)

    def build(self) -> Application:
        """Build and configure the Telegram Application."""
        app = Application.builder().token(self.token).post_init(self._post_init).build()

        owner = self._owner_filter()

        # Commands — owner only
        app.add_handler(CommandHandler("start", self._cmd_start, filters=owner))
        app.add_handler(CommandHandler("help", self._cmd_help, filters=owner))
        app.add_handler(CommandHandler("model", self._cmd_model, filters=owner))
        app.add_handler(CommandHandler("chats", self._cmd_chats, filters=owner))
        app.add_handler(CommandHandler("newchat", self._cmd_newchat, filters=owner))
        app.add_handler(CommandHandler("rename", self._cmd_rename, filters=owner))
        app.add_handler(CommandHandler("clear", self._cmd_clear, filters=owner))
        app.add_handler(
            CommandHandler("register_business_chat", self._cmd_register_chat, filters=owner)
        )
        app.add_handler(CommandHandler("list_chats", self._cmd_list_chats, filters=owner))
        app.add_handler(CommandHandler("drafts", self._cmd_drafts, filters=owner))
        app.add_handler(CommandHandler("published", self._cmd_published, filters=owner))
        app.add_handler(CommandHandler("queue", self._cmd_queue, filters=owner))
        app.add_handler(CommandHandler("generate", self._cmd_generate, filters=owner))
        app.add_handler(CommandHandler("summary", self._cmd_summary, filters=owner))

        # Inline callbacks
        app.add_handler(CallbackQueryHandler(self._cb_model_selected, pattern="^bbot_model:"))
        app.add_handler(CallbackQueryHandler(self._cb_chat_selected, pattern="^bbot_chat:"))

        # Group messages: anonymize and store (all users in registered groups)
        app.add_handler(
            MessageHandler(
                filters.TEXT & filters.ChatType.GROUPS,
                self._handle_group_message,
            )
        )

        # Private messages — ONLY from owner, all others silently ignored
        app.add_handler(
            MessageHandler(
                filters.TEXT & filters.ChatType.PRIVATE & owner,
                self._handle_private_message,
            )
        )

        # Catch-all for private messages from strangers — log and ignore
        app.add_handler(
            MessageHandler(
                filters.ChatType.PRIVATE & ~owner,
                self._handle_stranger,
            )
        )

        self._app = app
        return app

    # ── MODELS: loaded from providers.yaml (same list as orchestrator) ──────
    @staticmethod
    def _get_models() -> list[tuple[str, str]]:
        """Return list of (id_without_openrouter_prefix, display_name) from providers.yaml."""
        raw = _load_active_models()
        result = []
        for m in raw:
            mid = m.get("id", "")
            # Strip "openrouter/" prefix — we add it back on save
            short_id = mid.removeprefix("openrouter/")
            label = m.get("display_name", short_id)
            if short_id:
                result.append((short_id, label))
        return result

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "Привет! Я бизнес-бот Балбеса.\n\n"
            "Пиши мне в любое время — я слушаю и отвечаю через LLM.\n"
            "Могу создавать посты, показывать черновики, делать бизнес-саммари.\n\n"
            "Также добавь меня в рабочие Telegram-группы — я буду собирать информацию.\n"
            "Вечером в 20:00 проведём check-in и подготовим пост для блога.\n\n"
            "/help — список команд"
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "*Команды бизнес-бота:*\n\n"
            "✍️ *Генерация*\n"
            "/generate — сгенерировать пост по последним чатам\n"
            "/summary — бизнес-саммари за сегодня\n\n"
            "📝 *Посты*\n"
            "/drafts — черновики\n"
            "/published — опубликованные\n"
            "/queue — очередь на публикацию\n\n"
            "🤖 *Модель*\n"
            "/model — выбрать LLM для текущего чата\n\n"
            "💬 *Чаты*\n"
            "/chats — список / переключить\n"
            "/newchat \\[название\\] — создать новый чат\n"
            "/rename \\[название\\] — переименовать\n"
            "/clear — очистить историю\n\n"
            "⚙️ *Бизнес-наблюдение*\n"
            "/list\\_chats — зарегистрированные группы\n"
            "/register\\_business\\_chat — добавить группу\n\n"
            "*Просто пиши текстом:*\n"
            "— «придумай пост о запуске продукта»\n"
            "— «одобри пост abc12345»\n"
            "— любой вопрос или задача",
            parse_mode="Markdown",
        )

    async def _cmd_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        owner_id = update.effective_user.id
        chat_id = await self.agent.bbot_get_active_chat(owner_id)
        current = (await self.agent.bbot_get_chat_model(owner_id, chat_id)).removeprefix(
            "openrouter/"
        )
        models = self._get_models()
        buttons = [
            [
                InlineKeyboardButton(
                    f"{'✅ ' if model_id == current else ''}{label}",
                    callback_data=f"bbot_model:{model_id}",
                )
            ]
            for model_id, label in models
        ]
        await update.message.reply_text(
            "Выбери модель для текущего чата:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    async def _cb_model_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        owner_id = update.effective_user.id
        model_id = query.data.removeprefix("bbot_model:")
        full_id = f"openrouter/{model_id}"
        chat_id = await self.agent.bbot_get_active_chat(owner_id)
        await self.agent.bbot_set_chat_model(owner_id, chat_id, full_id)
        label = next((lbl for mid, lbl in self._get_models() if mid == model_id), model_id)
        await query.edit_message_text(f"✅ Модель чата: *{label}*", parse_mode="Markdown")

    async def _cmd_drafts(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        posts = await self.agent.queue.list_posts(status="draft", limit=10)
        if not posts:
            await update.message.reply_text("Нет черновиков.")
            return
        lines = ["*Черновики:*\n"]
        for p in posts:
            lines.append(
                f"• `{p.get('id', '')[:8]}` — {p.get('title', '(без названия)')} "
                f"[{p.get('post_type', '')}]"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _cmd_published(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        posts = await self.agent.queue.list_posts(status="published", limit=10)
        if not posts:
            await update.message.reply_text("Пока нет опубликованных постов.")
            return
        lines = ["*Опубликованные посты:*\n"]
        for p in posts:
            ts = p.get("published_at") or p.get("created_at", "")
            date_str = str(ts)[:10] if ts else "?"
            lines.append(
                f"• `{p.get('id', '')[:8]}` — {p.get('title', '(без названия)')} "
                f"[{p.get('post_type', '')}] {date_str}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _cmd_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show approved posts waiting to be published."""
        posts = await self.agent.queue.list_posts(status="approved", limit=10)
        if not posts:
            await update.message.reply_text("Очередь пуста — нет одобренных постов.")
            return
        lines = ["*В очереди на публикацию:*\n"]
        for p in posts:
            lines.append(
                f"• `{p.get('id', '')[:8]}` — {p.get('title', '(без названия)')} "
                f"[{p.get('post_type', '')}]"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _cmd_generate(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Generate a new post immediately from recent chats and files."""
        msg = update.effective_message
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
        await msg.reply_text("Генерирую пост по последним чатам…")

        owner_id = update.effective_user.id
        # Use chat's active model
        chat_id = await self.agent.bbot_get_active_chat(owner_id)
        post_model = await self.agent.bbot_get_chat_model(owner_id, chat_id)

        post = await self.agent.generate_agent_post(model=post_model)
        if not post:
            await msg.reply_text(
                "Нет новых материалов для поста.\n\n"
                "Попробуй:\n"
                "— Написать тему текстом, я сделаю черновик\n"
                "— /summary — бизнес-саммари за день"
            )
            return
        draft_id = await self.agent.create_and_send_draft(post, post_type="agent")
        if draft_id:
            await msg.reply_text(
                f"✅ Пост сгенерирован и отправлен на согласование.\nID: `{draft_id[:8]}`",
                parse_mode="Markdown",
            )

    async def _cmd_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Generate a business summary from today's business chats."""
        msg = update.effective_message
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
        await msg.reply_text("Генерирую бизнес-саммари…")
        summary = await self.agent.generate_business_summary()
        if not summary:
            await msg.reply_text(
                "Нет данных из бизнес-чатов за сегодня.\n"
                "Добавь меня в рабочие группы командой /register_business_chat"
            )
            return
        for chunk in _split_long(summary):
            await msg.reply_text(chunk, parse_mode="Markdown")

    # ── Multi-chat commands ───────────────────────────────────────────────────

    async def _cmd_chats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """List all business-bot chats with inline switch buttons."""
        owner_id = update.effective_user.id
        chats = await self.agent.bbot_get_chats(owner_id)
        active_id = await self.agent.bbot_get_active_chat(owner_id)

        if not chats:
            await update.message.reply_text("Пока нет чатов. Создай первый: /newchat Название")
            return

        buttons = []
        for chat in chats:
            cid = chat.get("chat_id") or chat.get("id", "")
            name = chat.get("name", cid)
            label = f"✅ {name}" if cid == active_id else name
            buttons.append([InlineKeyboardButton(label, callback_data=f"bbot_chat:{cid}")])

        await update.message.reply_text(
            "*Твои чаты:*\nНажми чтобы переключиться.",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown",
        )

    async def _cb_chat_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        owner_id = update.effective_user.id
        chat_id = query.data.removeprefix("bbot_chat:")
        await self.agent.bbot_set_active_chat(owner_id, chat_id)

        # get chat name for confirmation
        chats = await self.agent.bbot_get_chats(owner_id)
        name = next(
            (c.get("name", chat_id) for c in chats if (c.get("chat_id") or c.get("id")) == chat_id),
            chat_id,
        )
        await query.edit_message_text(f"✅ Переключился на чат: *{name}*", parse_mode="Markdown")

    async def _cmd_newchat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Create a new chat. Usage: /newchat [name]"""
        owner_id = update.effective_user.id
        name = " ".join(context.args) if context.args else "Новый чат"
        chat_id = await self.agent.bbot_create_chat(owner_id, name)
        await self.agent.bbot_set_active_chat(owner_id, chat_id)
        await update.message.reply_text(
            f"✅ Создан и активирован чат: *{name}*\nID: `{chat_id[:8]}`",
            parse_mode="Markdown",
        )

    async def _cmd_rename(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Rename the active chat. Usage: /rename New Name"""
        owner_id = update.effective_user.id
        if not context.args:
            await update.message.reply_text("Использование: /rename Новое название")
            return
        name = " ".join(context.args)
        chat_id = await self.agent.bbot_get_active_chat(owner_id)
        await self.agent.bbot_rename_chat(owner_id, chat_id, name)
        await update.message.reply_text(f"✅ Чат переименован: *{name}*", parse_mode="Markdown")

    async def _cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Clear history of the active chat."""
        owner_id = update.effective_user.id
        chat_id = await self.agent.bbot_get_active_chat(owner_id)
        await self.agent.bbot_clear_history(owner_id, chat_id)
        await update.message.reply_text("🗑 История текущего чата очищена.")

    async def _cmd_register_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Register a business group chat. Usage: /register_business_chat <group_id> <name> <strategy>"""
        args = context.args or []
        if len(args) < 2:
            await update.message.reply_text(
                "Использование: /register_business_chat <group_id> <название> [initials|roles|full]\n"
                "Пример: /register_business_chat -1001234567890 'Команда разработки' initials"
            )
            return

        group_id = args[0]
        name = args[1]
        strategy = args[2] if len(args) > 2 else "initials"

        if strategy not in ("initials", "roles", "full"):
            await update.message.reply_text("Стратегия должна быть: initials, roles или full")
            return

        try:
            await self.db.execute(
                """
                INSERT INTO business_chats (tg_group_id, name, anon_strategy)
                VALUES ($1, $2, $3)
                ON CONFLICT (tg_group_id) DO UPDATE
                SET name = EXCLUDED.name, anon_strategy = EXCLUDED.anon_strategy, is_active = TRUE
                """,
                group_id,
                name,
                strategy,
            )
            await update.message.reply_text(
                f"✅ Чат зарегистрирован: {name}\nID: {group_id}\nСтратегия: {strategy}"
            )
        except Exception as exc:
            logger.error("register_chat error: %s", exc)
            await update.message.reply_text(f"❌ Ошибка: {exc}")

    async def _cmd_list_chats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            rows = await self.db.fetch(
                "SELECT tg_group_id, name, anon_strategy, is_active FROM business_chats ORDER BY name"
            )
            if not rows:
                await update.message.reply_text("Нет зарегистрированных бизнес-чатов.")
                return
            lines = ["*Зарегистрированные бизнес-чаты:*\n"]
            for r in rows:
                status = "✅" if r["is_active"] else "❌"
                lines.append(f"{status} {r['name']} ({r['anon_strategy']})\n`{r['tg_group_id']}`")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as exc:
            await update.message.reply_text(f"❌ Ошибка: {exc}")

    async def _handle_group_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Store anonymized messages from registered business groups."""
        msg = update.effective_message
        chat = update.effective_chat
        user = update.effective_user

        if not msg or not chat or not user:
            return

        text = msg.text or msg.caption
        if not text:
            return

        try:
            row = await self.db.fetchrow(
                "SELECT id, anon_strategy, role_map FROM business_chats WHERE tg_group_id = $1 AND is_active",
                str(chat.id),
            )
            if not row:
                return  # unregistered group — ignore silently

            role_map: dict = row["role_map"] or {}
            engine = AnonymizationEngine(row["anon_strategy"], role_map)
            anon_sender, anon_content = engine.process(
                user_id=user.id,
                first_name=user.first_name,
                text=text,
                last_name=user.last_name,
                username=user.username,
            )

            if not anon_content.strip():
                return

            import datetime

            await self.db.execute(
                """
                INSERT INTO business_messages (chat_id, anon_sender, content, ts)
                VALUES ($1, $2, $3, $4)
                """,
                row["id"],
                anon_sender,
                anon_content,
                msg.date or datetime.datetime.now(datetime.timezone.utc),
            )
        except Exception as exc:
            logger.error("_handle_group_message error: %s", exc)

    async def _handle_private_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle private messages from the owner — check-in replies or edit instructions."""
        msg = update.effective_message
        user = update.effective_user

        if not msg or not user:
            return

        owner_id = user.id
        text = (msg.text or "").strip()

        # Check-in reply mode
        if _WAITING_CHECKIN.get(owner_id):
            _WAITING_CHECKIN[owner_id] = False
            await self.agent.handle_checkin_reply(owner_id, text)
            return

        # Edit instruction mode
        post_id = _WAITING_EDIT.get(owner_id)
        if post_id:
            _WAITING_EDIT[owner_id] = None
            await self.agent.handle_edit_instruction(owner_id, post_id, text)
            return

        # Default: full LLM conversation
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)

        async def reply_fn(text: str) -> None:
            for chunk in _split_long(text):
                await msg.reply_text(chunk, parse_mode="Markdown")

        await self.agent.handle_owner_message(owner_id, text, reply_fn)

    async def _handle_stranger(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Silently ignore private messages from anyone who is not the owner.

        We intentionally do NOT reply — no error message, no confirmation —
        to avoid leaking that this bot exists or is active.
        """
        user = update.effective_user
        logger.warning(
            "Ignored private message from non-owner user_id=%s username=%s",
            user.id if user else "?",
            user.username if user else "?",
        )
        # No reply — complete silence

    def set_waiting_checkin(self, owner_id: int, waiting: bool = True) -> None:
        """Called by scheduler to indicate next message is a check-in reply."""
        _WAITING_CHECKIN[owner_id] = waiting

    def set_waiting_edit(self, owner_id: int, post_id: str | None) -> None:
        """Called when user clicks 'Edit' on approval — next message is edit instructions."""
        _WAITING_EDIT[owner_id] = post_id
