"""
MAX Messenger UI helpers: inline keyboards (callback), slash commands, help text.

Docs: https://dev.max.ru/docs-api (inline_keyboard, message_callback).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.utils import get_providers_config

# Callback payload prefixes (keep short; MAX limits payload length)
CB_MENU = "MENU"
CB_CHAT = "C"
CB_MODEL = "M"
CB_AGENT = "A"
SEP = "|"

BTN_TEXT_MAX = 56


def _truncate(s: str, n: int = BTN_TEXT_MAX) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def inline_keyboard_attachment(button_rows: list[list[dict[str, str]]]) -> dict[str, Any]:
    """Build inline_keyboard attachment for POST /messages body."""
    return {"type": "inline_keyboard", "payload": {"buttons": button_rows}}


def build_main_menu_keyboard() -> list[list[dict[str, str]]]:
    """Quick actions like Telegram bot menu."""
    return [
        [
            {"type": "callback", "text": "📋 Чаты", "payload": CB_MENU + SEP + "chats"},
            {"type": "callback", "text": "🤖 Модель", "payload": CB_MENU + SEP + "model"},
        ],
        [
            {"type": "callback", "text": "👥 Агенты", "payload": CB_MENU + SEP + "agents"},
            {"type": "callback", "text": "📊 Статус", "payload": CB_MENU + SEP + "status"},
        ],
        [
            {"type": "callback", "text": "❓ Справка", "payload": CB_MENU + SEP + "help"},
        ],
    ]


def build_chat_switch_keyboard(
    chats: list[dict[str, Any]],
    active_id: str | None,
) -> list[list[dict[str, str]]]:
    rows: list[list[dict[str, str]]] = []
    for c in chats:
        cid = str(c.get("chat_id", ""))
        if not cid:
            continue
        name = _truncate(str(c.get("name") or "Чат"))
        mark = "✅ " if cid == active_id else ""
        rows.append(
            [
                {
                    "type": "callback",
                    "text": _truncate(f"{mark}{name}"),
                    "payload": f"{CB_CHAT}{SEP}{cid}",
                }
            ]
        )
    rows.append(
        [{"type": "callback", "text": "➕ Новый чат", "payload": CB_MENU + SEP + "newchat"}]
    )
    return rows


def build_model_switch_keyboard(models: list[dict[str, Any]]) -> list[list[dict[str, str]]]:
    rows: list[list[dict[str, str]]] = []
    for i, m in enumerate(models):
        label = _truncate(str(m.get("display_name") or m.get("id") or f"model_{i}"))
        rows.append([{"type": "callback", "text": label, "payload": f"{CB_MODEL}{SEP}{i}"}])
    return rows


def build_agent_switch_keyboard(
    agents: list[dict[str, Any]], current_id: str | None
) -> list[list[dict[str, str]]]:
    rows: list[list[dict[str, str]]] = []
    for i, a in enumerate(agents):
        aid = str(a.get("id", ""))
        emoji = str(a.get("emoji") or "🤖")
        name = str(a.get("display_name") or aid)
        mark = "✅ " if aid == current_id else ""
        rows.append(
            [
                {
                    "type": "callback",
                    "text": _truncate(f"{mark}{emoji} {name}"),
                    "payload": f"{CB_AGENT}{SEP}{i}",
                }
            ]
        )
    return rows


def load_active_models() -> list[dict[str, Any]]:
    return list(get_providers_config().get("active_models") or [])


def load_agents_list() -> list[dict[str, Any]]:
    return list(get_providers_config().get("agents") or [])


def model_display_name(model_id: str | None) -> str:
    if not model_id:
        return "default"
    for m in load_active_models():
        if m.get("id") == model_id:
            return str(m.get("display_name") or model_id)
    return model_id.split("/")[-1] if "/" in model_id else model_id


@dataclass
class MaxUiReply:
    """Outbound MAX message (text + optional inline keyboard)."""

    text: str
    attachments: list[dict[str, Any]] | None = None
    text_format: str | None = "markdown"


MAX_HELP_TEXT = (
    "**Команды (как в Telegram)**\n\n"
    "/agents — агенты и переключение\n"
    "/chats — список чатов и переключение\n"
    "/newchat [название] — новый чат\n"
    "/rename название — переименовать текущий чат\n"
    "/model — выбор модели\n"
    "/clear — очистить историю текущего чата\n"
    "/link — связать с Telegram (/link telegram или /link КОД)\n"
    "/status — статус системы\n"
    "/help — эта справка\n\n"
    "Ниже — кнопки меню. Обычный текст уходит агенту (как в Telegram)."
)
