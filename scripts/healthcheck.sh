#!/bin/bash
# Health check script for all services

set -e

echo "=================================================="
echo "Balbes Multi-Agent System - Health Check"
echo "=================================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track overall health
ALL_HEALTHY=true

# Function to check service
check_service() {
    local name=$1
    local command=$2

    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✅${NC} $name"
    else
        echo -e "${RED}❌${NC} $name"
        ALL_HEALTHY=false
    fi
}

# Function to check HTTP endpoint
check_http() {
    local name=$1
    local url=$2

    if curl -sf "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✅${NC} $name - $url"
    else
        echo -e "${RED}❌${NC} $name - $url"
        ALL_HEALTHY=false
    fi
}

# Infrastructure
echo "📦 Infrastructure Services"
echo ""

check_service "PostgreSQL" "docker exec balbes-postgres pg_isready -U balbes -d balbes_agents"
check_service "Redis" "docker exec balbes-redis redis-cli ping | grep -q PONG"
check_service "RabbitMQ" "curl -sf -u guest:guest http://localhost:15672/api/health/checks/alarms | grep -q '\"status\":\"ok\"'"
check_service "Qdrant" "curl -sf http://localhost:6333/healthz | grep -q 'ok'"

echo ""
echo "🚀 Application Services"
echo ""

check_http "Memory Service" "http://localhost:8100/health"
check_http "Skills Registry" "http://localhost:8101/health"
check_http "Web Backend" "http://localhost:8200/health"

# Check if agent processes are running (for dev mode)
echo ""
echo "🤖 Agent Processes"
echo ""

if ps aux | grep -q "[p]ython.*orchestrator/main.py"; then
    echo -e "${GREEN}✅${NC} Orchestrator (running)"
else
    echo -e "${YELLOW}⚠️${NC}  Orchestrator (not running - start with: make dev-orch)"
fi

if ps aux | grep -q "[p]ython.*coder/main.py"; then
    echo -e "${GREEN}✅${NC} Coder (running)"
else
    echo -e "${YELLOW}⚠️${NC}  Coder (not running - start with: make dev-coder)"
fi

# Check Docker containers (for prod mode)
if docker ps --format '{{.Names}}' | grep -q 'balbes-orchestrator'; then
    echo -e "${GREEN}✅${NC} Orchestrator container (running)"
fi

if docker ps --format '{{.Names}}' | grep -q 'balbes-coder'; then
    echo -e "${GREEN}✅${NC} Coder container (running)"
fi

# Summary
echo ""
echo "=================================================="
if [ "$ALL_HEALTHY" = true ]; then
    echo -e "${GREEN}✅ All critical services are healthy!${NC}"
    echo ""
    echo "System is ready to use:"
    echo "  - Telegram bot: /start"
    echo "  - Web UI: http://localhost:5173"
    echo "  - Memory API: http://localhost:8100/docs"
    echo "  - Skills API: http://localhost:8101/docs"
    echo "  - Web API: http://localhost:8200/docs"
else
    echo -e "${RED}❌ Some services are not healthy${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check Docker: docker ps"
    echo "  2. Start infrastructure: make infra-up"
    echo "  3. Check logs: make infra-logs"
    echo "  4. See docs/DEPLOYMENT.md for details"
fi
echo "=================================================="
