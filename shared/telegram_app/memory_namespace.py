"""
Memory Service user_id for Telegram-facing agents.

Format: ``{agent_manifest_id}_{telegram_user_id}`` — один namespace на пару
(агент из config/agents/*.yaml, пользователь Telegram). Так оркестратор (balbes),
блогер (blogger) и будущие агенты не пересекают чаты и историю в Redis.

Исторический префикс бизнес-бота ``bbot_<id>`` сохраняется только как fallback чтения.
"""

from __future__ import annotations

from dataclasses import dataclass


def memory_user_id(agent_manifest_id: str, telegram_user_id: int) -> str:
    """
    Canonical Memory `user_id` for an agent manifest id + Telegram user.

    `agent_manifest_id` — значение `id:` из `config/agents/<name>.yaml` (например `blogger`, `balbes`).
    """
    aid = (agent_manifest_id or "").strip().lower()
    return f"{aid}_{int(telegram_user_id)}"


def legacy_blogger_bbot_user_id(telegram_user_id: int) -> str:
    """Старый namespace бизнес-бота до унификации (только для чтения / миграции)."""
    return f"bbot_{int(telegram_user_id)}"


def blogger_memory_user_ids_try_order(telegram_user_id: int) -> tuple[str, str]:
    """Порядок: сначала канонический `blogger_*`, затем legacy `bbot_*`."""
    return (
        memory_user_id("blogger", telegram_user_id),
        legacy_blogger_bbot_user_id(telegram_user_id),
    )


# --- Общий контейнер для новых агентов (один импорт — один user_id) -----------------


@dataclass
class TelegramMemoryNamespace:
    """
    Канонический ``user_id`` и базовый URL Memory для пары (манифест агента, Telegram user).

    Новые сервисы создают ``TelegramMemoryNamespace(memory_url, "myagent", tg_id)``
    и используют ``.user_id`` во всех путях ``/api/v1/chats/{user_id}/...``.
    """

    memory_base_url: str
    agent_manifest_id: str
    telegram_user_id: int

    @property
    def user_id(self) -> str:
        return memory_user_id(self.agent_manifest_id, self.telegram_user_id)

    def chats_collection_url(self) -> str:
        return f"{self.memory_base_url.rstrip('/')}/api/v1/chats/{self.user_id}"
