"""
Telegram Bot integration for Balbes Multi-Agent System.

Handles:
- User commands (/start, /help, /status)
- Task submission from Telegram
- Result delivery
- Inline query processing
"""

import logging

import httpx
from telegram import (
    BotCommand,
    Update,
    User,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from shared.config import get_settings

settings = get_settings()
logger = logging.getLogger("orchestrator.telegram")


class BalbesTelegramBot:
    """
    Telegram Bot for Balbes System.

    Features:
    - Task submission
    - Status checking
    - Help and documentation
    - Real-time task updates
    """

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.app: Application | None = None
        self.http_client: httpx.AsyncClient | None = None
        self.orchestrator_url = f"http://localhost:{settings.orchestrator_port}"

    def initialize(self) -> None:
        """Initialize Telegram bot"""
        logger.info("Initializing Telegram bot...")

        self.app = Application.builder().token(self.token).build()

        # Add handlers
        self._setup_handlers()

        logger.info("Telegram bot initialized")

    def start_polling(self) -> None:
        """Start bot polling"""
        if not self.app:
            raise RuntimeError("Bot not initialized")

        logger.info("Starting bot polling...")
        self.app.run_polling()

    def _setup_handlers(self) -> None:
        """Setup message handlers"""
        if not self.app:
            return

        # Start command
        self.app.add_handler(CommandHandler("start", self.cmd_start))

        # Help command
        self.app.add_handler(CommandHandler("help", self.cmd_help))

        # Status command
        self.app.add_handler(CommandHandler("status", self.cmd_status))

        # Clear command
        self.app.add_handler(CommandHandler("clear", self.cmd_clear))

        # Regular messages (task submission)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def _set_commands(self) -> None:
        """Set bot commands in Telegram"""
        if not self.app:
            return

        commands = [
            BotCommand("/start", "Start using Balbes"),
            BotCommand("/help", "Show help and examples"),
            BotCommand("/status", "Check orchestrator status"),
            BotCommand("/clear", "Clear conversation history"),
        ]

        await self.app.bot.set_my_commands(commands)
        logger.info("Bot commands set")

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command"""
        user: User | None = update.effective_user

        if not user:
            return

        welcome_text = f"""
🤖 Welcome to **Balbes Multi-Agent System**, {user.first_name}!

I'm an intelligent orchestrator that can:
- 🔍 Search and retrieve information
- 📝 Process and summarize text
- 🛠️ Execute complex tasks
- 💾 Remember conversation context

Send me a task and I'll help you accomplish it!

Examples:
- "Summarize the top 3 AI trends in 2024"
- "What are the best practices for Python testing?"
- "Create a plan for learning machine learning"

Type /help to see all available commands.
        """

        await update.message.reply_text(
            welcome_text,
            parse_mode="Markdown",
        )

        logger.info(f"User {user.id} started conversation")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command"""
        help_text = """
📚 **Available Commands:**

/start - Start or restart conversation
/help - Show this help message
/status - Check orchestrator status
/clear - Clear conversation history

🎯 **How to Use:**

1. Simply type your task or question
2. I'll search for the best skill to handle it
3. You'll get the result!

💡 **Tips:**

- Be specific in your requests
- Use natural language
- Ask follow-up questions
- Request different perspectives

🔗 **Integration:**

Connected services:
- Memory Service (context & history)
- Skills Registry (task execution)
- Real-time notifications
        """

        await update.message.reply_text(
            help_text,
            parse_mode="Markdown",
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command"""
        try:
            if not self.http_client:
                self.http_client = httpx.AsyncClient(timeout=30.0)

            response = await self.http_client.get(f"{self.orchestrator_url}/api/v1/status")

            if response.status_code == 200:
                data = response.json()
                status_text = f"""
✅ **Orchestrator Status**: {data.get("status", "unknown").upper()}

🔗 **Services**:
- Memory Service: `{data["services"]["memory_service"]}`
- Skills Registry: `{data["services"]["skills_registry"]}`

⏰ **Timestamp**: {data.get("timestamp", "N/A")}
                """
                await update.message.reply_text(
                    status_text,
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(f"⚠️ Status check failed: {response.status_code}")

        except Exception as e:
            logger.error(f"Status check failed: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /clear command"""
        user: User | None = update.effective_user

        if not user:
            return

        try:
            if not self.http_client:
                self.http_client = httpx.AsyncClient(timeout=30.0)

            # Call Memory Service to clear context
            response = await self.http_client.delete(
                f"{settings.memory_service_url}/api/v1/context/{user.id}"
            )

            if response.status_code in [200, 204]:
                await update.message.reply_text("✅ Conversation history cleared!")
                logger.info(f"Cleared history for user {user.id}")
            else:
                await update.message.reply_text(f"⚠️ Clear failed: {response.status_code}")

        except Exception as e:
            logger.error(f"Clear command failed: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular text messages (task submission)"""
        user: User | None = update.effective_user
        message = update.message

        if not user or not message or not message.text:
            return

        task_description = message.text

        try:
            # Show processing indicator
            processing_msg = await update.message.reply_text("⏳ Processing your request...")

            # Send task to orchestrator
            if not self.http_client:
                self.http_client = httpx.AsyncClient(timeout=30.0)

            response = await self.http_client.post(
                f"{self.orchestrator_url}/api/v1/tasks",
                json={
                    "user_id": str(user.id),
                    "description": task_description,
                },
            )

            if response.status_code == 200:
                result = response.json()

                # Delete processing message
                await processing_msg.delete()

                # Send result
                if result.get("status") == "success":
                    result_text = f"""
✅ **Task Completed**

📌 **Task**: {task_description[:100]}...

🎯 **Skill Used**: {result.get("skill_used", "N/A")}

📊 **Result**:
```
{str(result.get("result", {}))[:200]}
```

⏱️ **Duration**: {result.get("duration_ms", 0):.0f}ms
                    """
                else:
                    result_text = f"""
❌ **Task Failed**

📌 **Task**: {task_description[:100]}...

❌ **Error**: {result.get("error", "Unknown error")}
                    """

                await update.message.reply_text(
                    result_text,
                    parse_mode="Markdown",
                )

                logger.info(f"Task completed for user {user.id}: {result.get('status')}")
            else:
                await processing_msg.delete()
                await update.message.reply_text(
                    f"❌ Request failed: {response.status_code}\n{response.text}"
                )

        except Exception as e:
            logger.error(f"Message handling failed: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")


def run_bot() -> None:
    """Run Telegram bot"""
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured, skipping bot initialization")
        return

    bot = BalbesTelegramBot()
    bot.initialize()
    bot.start_polling()


if __name__ == "__main__":
    run_bot()
