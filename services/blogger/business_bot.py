"""
Business bot — silent Telegram bot with dual role:
  1. In group chats: anonymizes and stores messages to business_messages table.
  2. In private chat with owner: handles evening check-in conversation and
     approval replies for personal blog posts.

Separate bot token (BUSINESS_BOT_TOKEN) to keep business monitoring
cleanly separated from the main orchestrator bot.
"""

import logging
from typing import TYPE_CHECKING

import asyncpg
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .anonymizer import AnonymizationEngine

if TYPE_CHECKING:
    from .agent import BloggerAgent

logger = logging.getLogger("blogger.business_bot")

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

    def build(self) -> Application:
        """Build and configure the Telegram Application."""
        app = Application.builder().token(self.token).build()

        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("register_business_chat", self._cmd_register_chat))
        app.add_handler(CommandHandler("list_chats", self._cmd_list_chats))

        # Group messages: anonymize and store
        app.add_handler(
            MessageHandler(
                filters.TEXT & filters.ChatType.GROUPS,
                self._handle_group_message,
            )
        )

        # Private messages from owner: check-in replies and edit instructions
        app.add_handler(
            MessageHandler(
                filters.TEXT & filters.ChatType.PRIVATE,
                self._handle_private_message,
            )
        )

        self._app = app
        return app

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user and update.effective_user.id == self.owner_tg_id:
            await update.message.reply_text(
                "Привет! Я бизнес-бот Балбеса.\n\n"
                "Добавь меня в рабочие Telegram-группы — я буду собирать информацию.\n"
                "Здесь, в личке, будем проводить вечерние check-in и согласовывать посты."
            )
        else:
            await update.message.reply_text("Этот бот работает только с владельцем системы.")

    async def _cmd_register_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Register a business group chat. Usage: /register_business_chat <group_id> <name> <strategy>"""
        if not update.effective_user or update.effective_user.id != self.owner_tg_id:
            return

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
        if not update.effective_user or update.effective_user.id != self.owner_tg_id:
            return
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

        if not msg or not user or user.id != self.owner_tg_id:
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

        # Default: forward to orchestrator / ignore
        await msg.reply_text(
            "Напиши /start для справки. Вечерний check-in начнётся автоматически в 20:00."
        )

    def set_waiting_checkin(self, owner_id: int, waiting: bool = True) -> None:
        """Called by scheduler to indicate next message is a check-in reply."""
        _WAITING_CHECKIN[owner_id] = waiting

    def set_waiting_edit(self, owner_id: int, post_id: str | None) -> None:
        """Called when user clicks 'Edit' on approval — next message is edit instructions."""
        _WAITING_EDIT[owner_id] = post_id
