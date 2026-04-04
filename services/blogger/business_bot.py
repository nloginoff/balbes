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
from typing import TYPE_CHECKING

import asyncpg
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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

    def build(self) -> Application:
        """Build and configure the Telegram Application."""
        app = Application.builder().token(self.token).build()

        owner = self._owner_filter()

        # Commands — owner only
        app.add_handler(CommandHandler("start", self._cmd_start, filters=owner))
        app.add_handler(CommandHandler("help", self._cmd_help, filters=owner))
        app.add_handler(CommandHandler("model", self._cmd_model, filters=owner))
        app.add_handler(
            CommandHandler("register_business_chat", self._cmd_register_chat, filters=owner)
        )
        app.add_handler(CommandHandler("list_chats", self._cmd_list_chats, filters=owner))
        app.add_handler(CommandHandler("drafts", self._cmd_drafts, filters=owner))

        # Model selection callback
        app.add_handler(CallbackQueryHandler(self._cb_model_selected, pattern="^bbot_model:"))

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

    # ── MODELS available for selection ──────────────────────────────────────
    MODELS = [
        ("minimax/minimax-m2.5:free", "MiniMax M2.5 (free)"),
        ("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B (cheap)"),
        ("moonshotai/kimi-k2.5", "Kimi K2.5 (medium)"),
        ("google/gemini-flash-1.5", "Gemini Flash (medium)"),
        ("anthropic/claude-sonnet-4-5", "Claude Sonnet (premium)"),
    ]

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
            "/help — эта справка\n"
            "/model — выбрать LLM модель\n"
            "/drafts — показать черновики постов\n"
            "/list\\_chats — зарегистрированные бизнес-чаты\n"
            "/register\\_business\\_chat — добавить группу\n\n"
            "*Что можно писать просто текстом:*\n"
            "— «придумай пост о запуске нового проекта»\n"
            "— «покажи что в очереди на публикацию»\n"
            "— «сделай саммари бизнес-чатов»\n"
            "— «одобри пост abc12345»\n"
            "— любой вопрос или идея",
            parse_mode="Markdown",
        )

    async def _cmd_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        current = self.agent._conversation_model.removeprefix("openrouter/")
        buttons = [
            [
                InlineKeyboardButton(
                    f"{'✅ ' if model_id == current else ''}{label}",
                    callback_data=f"bbot_model:{model_id}",
                )
            ]
            for model_id, label in self.MODELS
        ]
        await update.message.reply_text(
            "Выбери модель для общения:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    async def _cb_model_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        model_id = query.data.removeprefix("bbot_model:")
        full_id = f"openrouter/{model_id}"
        self.agent.set_conversation_model(full_id)
        label = next((lbl for mid, lbl in self.MODELS if mid == model_id), model_id)
        await query.edit_message_text(f"✅ Модель выбрана: *{label}*", parse_mode="Markdown")

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
