#!/bin/bash

# Visual status check for all environments
# Usage: ./scripts/status_all_envs.sh

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         Balbes Multi-Environment Status Check                 ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

check_service() {
    local url=$1
    if curl -sf "$url" > /dev/null 2>&1; then
        echo "✅"
    else
        echo "❌"
    fi
}

check_port() {
    local port=$1
    if lsof -ti:$port > /dev/null 2>&1; then
        echo "✅"
    else
        echo "❌"
    fi
}

check_process() {
    local pattern=$1
    if pgrep -f "$pattern" > /dev/null 2>&1; then
        echo "✅"
    else
        echo "❌"
    fi
}

# Development Environment
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│ 🟦 DEVELOPMENT (ports 8100-8200, DB: balbes_dev)           │"
echo "├─────────────────────────────────────────────────────────────┤"
printf "│ Memory Service (8100)      : %s                            │\n" "$(check_service http://localhost:8100/health)"
printf "│ Skills Registry (8101)     : %s                            │\n" "$(check_service http://localhost:8101/health)"
printf "│ Orchestrator (8102)        : %s                            │\n" "$(check_service http://localhost:8102/health)"
printf "│ Coder Agent (8103)         : %s                            │\n" "$(check_service http://localhost:8103/health)"
printf "│ Web Backend (8200)         : %s                            │\n" "$(check_service http://localhost:8200/health)"
printf "│ Blogger (8105)             : %s                            │\n" "$(check_service http://localhost:8105/health)"
printf "│ Frontend (5173)            : %s                            │\n" "$(check_port 5173)"
echo "└─────────────────────────────────────────────────────────────┘"
echo ""

# Testing Environment
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│ 🟨 TESTING (ports 9100-9200, DB: balbes_test)              │"
echo "├─────────────────────────────────────────────────────────────┤"
printf "│ Memory Service (9100)      : %s                            │\n" "$(check_service http://localhost:9100/health)"
printf "│ Skills Registry (9101)     : %s                            │\n" "$(check_service http://localhost:9101/health)"
printf "│ Orchestrator (9102)        : %s                            │\n" "$(check_service http://localhost:9102/health)"
printf "│ Coder Agent (9103)         : %s                            │\n" "$(check_service http://localhost:9103/health)"
printf "│ Web Backend (9200)         : %s                            │\n" "$(check_service http://localhost:9200/health)"
printf "│ Blogger (9105)             : %s                            │\n" "$(check_service http://localhost:9105/health)"
printf "│ Frontend (5174)            : %s                            │\n" "$(check_port 5174)"
echo "└─────────────────────────────────────────────────────────────┘"
echo ""

# Production Environment
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│ 🟩 PRODUCTION (ports 18100-18200, DB: balbes)              │"
echo "├─────────────────────────────────────────────────────────────┤"

if systemctl list-unit-files 2>/dev/null | grep -q balbes-memory; then
    printf "│ Memory Service (systemd)   : %s                            │\n" "$(systemctl is-active balbes-memory 2>/dev/null | grep -q active && echo ✅ || echo ❌)"
    printf "│ Skills Registry (systemd)  : %s                            │\n" "$(systemctl is-active balbes-skills 2>/dev/null | grep -q active && echo ✅ || echo ❌)"
    printf "│ Orchestrator (systemd)     : %s                            │\n" "$(systemctl is-active balbes-orchestrator 2>/dev/null | grep -q active && echo ✅ || echo ❌)"
    printf "│ Coder Agent (systemd)      : %s                            │\n" "$(systemctl is-active balbes-coder 2>/dev/null | grep -q active && echo ✅ || echo ❌)"
    printf "│ Web Backend (systemd)      : %s                            │\n" "$(systemctl is-active balbes-web-backend 2>/dev/null | grep -q active && echo ✅ || echo ❌)"
    if systemctl list-unit-files 2>/dev/null | grep -q '^balbes-webhooks-gateway.service'; then
        printf "│ Webhooks Gateway (systemd) : %s                            │\n" "$(systemctl is-active balbes-webhooks-gateway 2>/dev/null | grep -q active && echo ✅ || echo ❌)"
    fi
    if systemctl list-unit-files 2>/dev/null | grep -q '^balbes-blogger.service'; then
        printf "│ Blogger (systemd)          : %s                            │\n" "$(systemctl is-active balbes-blogger 2>/dev/null | grep -q active && echo ✅ || echo ❌)"
    fi
else
    printf "│ Memory Service (18100)     : %s                            │\n" "$(check_service http://localhost:18100/health)"
    printf "│ Skills Registry (18101)    : %s                            │\n" "$(check_service http://localhost:18101/health)"
    printf "│ Orchestrator (18102)       : %s                            │\n" "$(check_service http://localhost:18102/health)"
    printf "│ Coder Agent (18103)        : %s                            │\n" "$(check_service http://localhost:18103/health)"
    printf "│ Web Backend (18200)        : %s                            │\n" "$(check_service http://localhost:18200/health)"
    printf "│ Webhooks Gateway (18180)   : %s                            │\n" "$(check_service http://localhost:18180/health)"
    printf "│ Blogger (18105)            : %s                            │\n" "$(check_service http://localhost:18105/health)"
fi

printf "│ Telegram Bot (polling)     : %s                            │\n" "$(check_process 'python telegram_bot.py')"
printf "│ Nginx (80/443)             : %s                            │\n" "$(systemctl is-active nginx 2>/dev/null | grep -q active && echo ✅ || echo ❌)"
echo "└─────────────────────────────────────────────────────────────┘"
echo ""

# Docker Infrastructure
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│ 🐳 Docker Infrastructure                                    │"
echo "├─────────────────────────────────────────────────────────────┤"

check_docker() {
    local name=$1
    if docker ps --format "{{.Names}}" 2>/dev/null | grep -q "$name"; then
        echo "✅"
    else
        echo "❌"
    fi
}

printf "│ Dev PostgreSQL             : %s                            │\n" "$(check_docker balbes-dev-postgres)"
printf "│ Dev Redis                  : %s                            │\n" "$(check_docker balbes-dev-redis)"
printf "│ Dev Qdrant                 : %s                            │\n" "$(check_docker balbes-dev-qdrant)"
echo "│                                                             │"
printf "│ Test PostgreSQL            : %s                            │\n" "$(check_docker balbes-test-postgres)"
printf "│ Test Redis                 : %s                            │\n" "$(check_docker balbes-test-redis)"
printf "│ Test Qdrant                : %s                            │\n" "$(check_docker balbes-test-qdrant)"
echo "│                                                             │"
printf "│ Prod PostgreSQL            : %s                            │\n" "$(check_docker balbes-prod-postgres)"
printf "│ Prod Redis                 : %s                            │\n" "$(check_docker balbes-prod-redis)"
printf "│ Prod Qdrant                : %s                            │\n" "$(check_docker balbes-prod-qdrant)"
echo "└─────────────────────────────────────────────────────────────┘"
echo ""

# Summary
dev_count=0
for u in http://localhost:8100/health http://localhost:8101/health http://localhost:8102/health http://localhost:8103/health http://localhost:8200/health http://localhost:8105/health; do
    curl -sf "$u" > /dev/null 2>&1 && dev_count=$((dev_count + 1)) || true
done
test_count=0
for u in http://localhost:9100/health http://localhost:9101/health http://localhost:9102/health http://localhost:9103/health http://localhost:9200/health http://localhost:9105/health; do
    curl -sf "$u" > /dev/null 2>&1 && test_count=$((test_count + 1)) || true
done

echo "📊 Summary:"
echo "   Dev:  $dev_count/6 services online"
echo "   Test: $test_count/6 services online"
echo ""
