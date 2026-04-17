"""
Single source of truth: slash commands per Telegram role (orchestrator vs blogger).

Registration and /setMyCommands are driven by these lists + TelegramFeatureFlags.
Handlers: getattr(bot, handler_name); missing methods are skipped.
"""

from __future__ import annotations

from dataclasses import dataclass

from telegram import BotCommand
from telegram.ext import Application, CommandHandler
from telegram.ext import filters as tg_filters

from shared.agent_manifest import TelegramFeatureFlags


@dataclass(frozen=True)
class SlashCommandRow:
    """One /command: YAML flag, command name, menu label, handler method on the bot class."""

    flag: str
    command: str
    description: str
    handler: str


# Menu order = tuple order.
SLASH_COMMANDS_ORCHESTRATOR: tuple[SlashCommandRow, ...] = (
    SlashCommandRow("start_command", "start", "Начать работу", "cmd_start"),
    SlashCommandRow("help_command", "help", "Справка по командам", "cmd_help"),
    SlashCommandRow("stop_command", "stop", "⛔ Остановить текущее действие агента", "cmd_stop"),
    SlashCommandRow("agents_switch", "agents", "Список агентов / переключить агента", "cmd_agents"),
    SlashCommandRow("multi_chat", "chats", "Список чатов / переключить чат", "cmd_chats"),
    SlashCommandRow("multi_chat", "newchat", "Создать новый чат", "cmd_newchat"),
    SlashCommandRow("multi_chat", "rename", "Переименовать текущий чат", "cmd_rename"),
    SlashCommandRow("model_switch", "model", "Выбрать модель для чата", "cmd_model"),
    SlashCommandRow("clear_command", "clear", "Очистить историю чата", "cmd_clear"),
    SlashCommandRow(
        "memory_commands", "remember", "Сохранить в долгосрочную память", "cmd_remember"
    ),
    SlashCommandRow("memory_commands", "recall", "Найти в долгосрочной памяти", "cmd_recall"),
    SlashCommandRow(
        "heartbeat_cmd", "heartbeat", "Запустить проверку прямо сейчас", "cmd_heartbeat"
    ),
    SlashCommandRow("debug_command", "debug", "🔍 Включить/выключить трейс действий", "cmd_debug"),
    SlashCommandRow(
        "mode_command", "mode", "🤖 Режим: agent (exec) / 📝 ask (только чтение)", "cmd_mode"
    ),
    SlashCommandRow("tasks_command", "tasks", "📋 Список задач агентов (реестр)", "cmd_tasks"),
    SlashCommandRow("status_command", "status", "Статус системы", "cmd_status"),
    SlashCommandRow(
        "link_command",
        "link",
        "Привязать MAX / ввести код (один аккаунт)",
        "cmd_link",
    ),
)

SLASH_COMMANDS_BLOGGER: tuple[SlashCommandRow, ...] = (
    SlashCommandRow("start_command", "start", "Начать", "_cmd_start"),
    SlashCommandRow("posts_commands", "generate", "Сгенерировать пост по чатам", "_cmd_generate"),
    SlashCommandRow("posts_commands", "drafts", "Черновики постов (полный текст)", "_cmd_drafts"),
    SlashCommandRow(
        "posts_commands", "draft", "Один черновик по ID (8 символов)", "_cmd_draft_one"
    ),
    SlashCommandRow("posts_commands", "published", "Опубликованные посты", "_cmd_published"),
    SlashCommandRow("posts_commands", "queue", "Очередь на публикацию", "_cmd_queue"),
    SlashCommandRow("posts_commands", "summary", "Бизнес-саммари за день", "_cmd_summary"),
    SlashCommandRow("model_switch", "model", "Выбрать LLM модель", "_cmd_model"),
    SlashCommandRow("multi_chat", "chats", "Список чатов / переключить", "_cmd_chats"),
    SlashCommandRow("multi_chat", "newchat", "Создать новый чат", "_cmd_newchat"),
    SlashCommandRow("multi_chat", "rename", "Переименовать чат", "_cmd_rename"),
    SlashCommandRow("multi_chat", "clear", "Очистить историю чата", "_cmd_clear"),
    SlashCommandRow(
        "business_groups", "list_chats", "Зарегистрированные бизнес-группы", "_cmd_list_chats"
    ),
    SlashCommandRow(
        "register_business_chat",
        "register_business_chat",
        "Добавить бизнес-группу",
        "_cmd_register_chat",
    ),
    SlashCommandRow("help_command", "help", "Справка", "_cmd_help"),
    SlashCommandRow("debug_command", "debug", "🔍 Включить/выключить трейс действий", "cmd_debug"),
    SlashCommandRow("stop_command", "stop", "⛔ Остановить действие агента", "cmd_stop"),
    SlashCommandRow("agents_switch", "agents", "Список агентов / переключить", "cmd_agents"),
    SlashCommandRow(
        "memory_commands", "remember", "Сохранить в долгосрочную память", "cmd_remember"
    ),
    SlashCommandRow("memory_commands", "recall", "Найти в долгосрочной памяти", "cmd_recall"),
    SlashCommandRow("heartbeat_cmd", "heartbeat", "Запустить проверку", "cmd_heartbeat"),
    SlashCommandRow("mode_command", "mode", "Режим agent / ask", "cmd_mode"),
    SlashCommandRow("tasks_command", "tasks", "Список задач (реестр)", "cmd_tasks"),
    SlashCommandRow("status_command", "status", "Статус системы", "cmd_status"),
)


def _rows_for_role(role: str) -> tuple[SlashCommandRow, ...]:
    if role == "orchestrator":
        return SLASH_COMMANDS_ORCHESTRATOR
    if role == "blogger":
        return SLASH_COMMANDS_BLOGGER
    raise ValueError(f"Unknown telegram role: {role!r}")


def build_slash_bot_commands(tg: TelegramFeatureFlags, role: str) -> list[BotCommand]:
    """Build BotCommand list for /setMyCommands."""
    out: list[BotCommand] = []
    for row in _rows_for_role(role):
        if not getattr(tg, row.flag, False):
            continue
        out.append(BotCommand(row.command, row.description))
    return out


def register_slash_command_handlers(
    app: Application,
    tg: TelegramFeatureFlags,
    bot: object,
    *,
    role: str,
    owner_filter: tg_filters.BaseFilter | None = None,
) -> None:
    """Register CommandHandler for each enabled row where the bot implements the handler."""
    for row in _rows_for_role(role):
        if not getattr(tg, row.flag, False):
            continue
        fn = getattr(bot, row.handler, None)
        if not callable(fn):
            continue
        app.add_handler(CommandHandler(row.command, fn, filters=owner_filter))
