"""
Telegram Bot entrypoint for the orchestrator service.

Implementation lives in shared.telegram_app.balbes_bot so other services can reuse imports.
"""

from shared.telegram_app.balbes_bot import BalbesTelegramBot, run_bot

__all__ = ["BalbesTelegramBot", "run_bot"]

if __name__ == "__main__":
    run_bot()
