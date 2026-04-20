#!/bin/bash
# Telegram agent diagnostics: service health, webhook info, recent gateway logs.
# Run on the host where Balbes prod/dev runs (same directory as .env / .env.prod).
#
# Usage: ./scripts/diagnose_telegram_stack.sh [dev|test|prod]
# Default: auto (same heuristic as healthcheck.sh)

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

MODE="${1:-auto}"

detect_mode() {
    if curl -sf "http://localhost:18100/health" > /dev/null 2>&1 || curl -sf "http://localhost:18200/health" > /dev/null 2>&1; then
        echo "prod"
    elif curl -sf "http://localhost:9100/health" > /dev/null 2>&1 || curl -sf "http://localhost:9200/health" > /dev/null 2>&1; then
        echo "test"
    else
        echo "dev"
    fi
}

if [[ "$MODE" == "auto" ]]; then
    MODE="$(detect_mode)"
fi

case "$MODE" in
    dev|test|prod) ;;
    *)
        echo "Usage: $0 [dev|test|prod]"
        exit 1
        ;;
esac

echo "=================================================="
echo "Telegram stack diagnostics (mode=$MODE)"
echo "=================================================="
echo ""

ENV_FILE=""
if [[ "$MODE" == "prod" ]] && [[ -f .env.prod ]]; then
    ENV_FILE=".env.prod"
elif [[ -f .env ]]; then
    ENV_FILE=".env"
elif [[ "$MODE" == "dev" ]] && [[ -f .env.dev ]]; then
    ENV_FILE=".env.dev"
elif [[ "$MODE" == "test" ]] && [[ -f .env.test ]]; then
    ENV_FILE=".env.test"
fi
if [[ -n "$ENV_FILE" ]]; then
    # shellcheck disable=SC2046
    export $(grep -v '^#' "$ENV_FILE" | xargs)
    echo "Loaded $ENV_FILE"
else
    echo "No .env / .env.prod — using default ports for mode=$MODE"
fi
echo ""

case "$MODE" in
    prod)
        MEM="${MEMORY_SERVICE_PORT:-18100}"
        ORCH="${ORCHESTRATOR_PORT:-18102}"
        WH="${WEBHOOKS_GATEWAY_PORT:-18180}"
        ;;
    test)
        MEM="${MEMORY_SERVICE_PORT:-9100}"
        ORCH="${ORCHESTRATOR_PORT:-9102}"
        WH="${WEBHOOKS_GATEWAY_PORT:-9180}"
        ;;
    *)
        MEM="${MEMORY_SERVICE_PORT:-8100}"
        ORCH="${ORCHESTRATOR_PORT:-8102}"
        WH="${WEBHOOKS_GATEWAY_PORT:-8180}"
        ;;
esac

echo "--- HTTP health ---"
curl -sf "http://localhost:${MEM}/health" > /dev/null && echo "Memory http://localhost:${MEM}/health OK" || echo "Memory http://localhost:${MEM}/health FAIL"
curl -sf "http://localhost:${ORCH}/health" > /dev/null && echo "Orchestrator http://localhost:${ORCH}/health OK" || echo "Orchestrator http://localhost:${ORCH}/health FAIL"
curl -sf "http://localhost:${WH}/health" > /dev/null && echo "Webhooks Gateway http://localhost:${WH}/health OK" || echo "Webhooks Gateway http://localhost:${WH}/health FAIL"
echo ""

echo "--- TELEGRAM_BOT_MODE ---"
echo "TELEGRAM_BOT_MODE=${TELEGRAM_BOT_MODE:-<unset defaults to polling in start_prod>}"
echo ""

if [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    echo "--- getWebhookInfo (public URL / errors from Telegram) ---"
    if ! out=$(curl -sS --max-time 15 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"); then
        echo "getWebhookInfo request failed"
    else
        echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('result') or {}; print('url:', r.get('url')); print('pending_update_count:', r.get('pending_update_count')); print('last_error_date:', r.get('last_error_date')); print('last_error_message:', r.get('last_error_message'))" 2>/dev/null || echo "$out"
    fi
else
    echo "TELEGRAM_BOT_TOKEN not set — cannot call getWebhookInfo"
fi
echo ""

echo "--- Recent webhooks gateway log (if file exists) ---"
LOG_FILE="$PROJECT_ROOT/logs/${MODE}/webhooks-gateway.log"
if [[ -f "$LOG_FILE" ]]; then
    tail -n 25 "$LOG_FILE"
else
    echo "No $LOG_FILE (start services or check journalctl below)"
fi
echo ""

echo "--- systemd (if available) ---"
if command -v journalctl >/dev/null 2>&1; then
    journalctl -u balbes-webhooks-gateway -n 20 --no-pager 2>/dev/null || echo "No journal for balbes-webhooks-gateway"
else
    echo "journalctl not available"
fi
echo ""
echo "Done."
