#!/usr/bin/env bash
# Example: run a second Telegram bot process pointing at another orchestrator HTTP port
# and a different TELEGRAM_BOT_TOKEN (separate @BotFather bot).
#
# Usage:
#   cp scripts/run_second_orchestrator_bot.example.sh scripts/run_second_orchestrator_bot.sh
#   chmod +x scripts/run_second_orchestrator_bot.sh
#   Edit TELEGRAM_BOT_TOKEN and ORCHESTRATOR_PORT, then run from repo root:
#   ./scripts/run_second_orchestrator_bot.sh
#
set -euo pipefail
cd "$(dirname "$0")/.."

export ORCHESTRATOR_PORT="${ORCHESTRATOR_PORT:-8103}"
export TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:?Set TELEGRAM_BOT_TOKEN for the second bot}"
# Optional: restrict who may use this bot (comma-separated Telegram user ids)
# export TELEGRAM_ALLOWED_USERS="123456789"

PYTHONPATH=. exec python -m services.orchestrator.telegram_bot
