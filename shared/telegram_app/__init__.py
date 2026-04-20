"""Shared Telegram bot implementation (Balbes orchestrator UI).

Avoid importing ``balbes_bot`` at package import time: ``shared.outbound.mirror`` imports
``shared.telegram_app.text``, and ``balbes_bot`` imports mirror — eager exports here caused
a circular import and broke the webhooks gateway.
"""

from __future__ import annotations

from typing import Any

__all__ = ["BalbesTelegramBot", "run_bot"]


def __getattr__(name: str) -> Any:
    if name == "BalbesTelegramBot":
        from shared.telegram_app.balbes_bot import BalbesTelegramBot

        return BalbesTelegramBot
    if name == "run_bot":
        from shared.telegram_app.balbes_bot import run_bot

        return run_bot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
