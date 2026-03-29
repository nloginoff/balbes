#!/bin/bash
# Health check script for Balbes environments
# Usage:
#   ./scripts/healthcheck.sh              # auto detect env (dev/test/prod)
#   ./scripts/healthcheck.sh dev|test|prod

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

MODE="${1:-auto}"
ALL_HEALTHY=true
TOTAL=0
PASSED=0

check_http() {
    local name="$1"
    local url="$2"
    TOTAL=$((TOTAL + 1))
    if curl -sf "$url" > /dev/null 2>&1; then
        PASSED=$((PASSED + 1))
        echo -e "${GREEN}✅${NC} $name - $url"
    else
        ALL_HEALTHY=false
        echo -e "${RED}❌${NC} $name - $url"
    fi
}

check_container() {
    local name="$1"
    local container="$2"
    TOTAL=$((TOTAL + 1))
    if docker ps --format "{{.Names}}" 2>/dev/null | grep -q "^${container}\$"; then
        PASSED=$((PASSED + 1))
        echo -e "${GREEN}✅${NC} $name (${container})"
    else
        ALL_HEALTHY=false
        echo -e "${RED}❌${NC} $name (${container})"
    fi
}

check_process() {
    local name="$1"
    local pattern="$2"
    TOTAL=$((TOTAL + 1))
    if pgrep -f "$pattern" > /dev/null 2>&1; then
        PASSED=$((PASSED + 1))
        echo -e "${GREEN}✅${NC} $name"
    else
        ALL_HEALTHY=false
        echo -e "${RED}❌${NC} $name"
    fi
}

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
        echo "Invalid mode: $MODE"
        echo "Usage: ./scripts/healthcheck.sh [dev|test|prod]"
        exit 1
        ;;
esac

echo "=================================================="
echo "Balbes Health Check ($MODE)"
echo "=================================================="
echo ""

echo "🚀 Application Services"
echo ""
if [[ "$MODE" == "dev" ]]; then
    check_http "Memory Service" "http://localhost:8100/health"
    check_http "Skills Registry" "http://localhost:8101/health"
    check_http "Orchestrator" "http://localhost:8102/health"
    check_http "Coder Agent" "http://localhost:8103/health"
    check_http "Web Backend" "http://localhost:8200/health"
elif [[ "$MODE" == "test" ]]; then
    check_http "Memory Service" "http://localhost:9100/health"
    check_http "Skills Registry" "http://localhost:9101/health"
    check_http "Orchestrator" "http://localhost:9102/health"
    check_http "Coder Agent" "http://localhost:9103/health"
    check_http "Web Backend" "http://localhost:9200/health"
else
    check_http "Memory Service" "http://localhost:18100/health"
    check_http "Skills Registry" "http://localhost:18101/health"
    check_http "Orchestrator" "http://localhost:18102/health"
    check_http "Coder Agent" "http://localhost:18103/health"
    check_http "Web Backend" "http://localhost:18200/health"
    if [ -f .env.prod ]; then
        # shellcheck disable=SC2046
        export $(cat .env.prod | grep -v '^#' | xargs)
        if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
            check_process "Telegram Bot Polling" "telegram_bot.py"
        fi
    fi
fi

echo ""
echo "📦 Infrastructure (Docker containers)"
echo ""
if [[ "$MODE" == "dev" ]]; then
    check_container "PostgreSQL" "balbes-dev-postgres"
    check_container "Redis" "balbes-dev-redis"
    check_container "Qdrant" "balbes-dev-qdrant"
    check_container "RabbitMQ" "balbes-dev-rabbitmq"
elif [[ "$MODE" == "test" ]]; then
    check_container "PostgreSQL" "balbes-test-postgres"
    check_container "Redis" "balbes-test-redis"
    check_container "Qdrant" "balbes-test-qdrant"
else
    check_container "PostgreSQL" "balbes-prod-postgres"
    check_container "Redis" "balbes-prod-redis"
    check_container "Qdrant" "balbes-prod-qdrant"
    check_container "RabbitMQ" "balbes-prod-rabbitmq"
fi

echo ""
echo "=================================================="
if [ "$ALL_HEALTHY" = true ]; then
    echo -e "${GREEN}✅ All checks passed ($PASSED/$TOTAL)${NC}"
else
    echo -e "${YELLOW}⚠️  Partial health: $PASSED/$TOTAL checks passed${NC}"
fi
echo "=================================================="
