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

# Development Environment
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│ 🟦 DEVELOPMENT (ports 8100-8200, DB: balbes_dev)           │"
echo "├─────────────────────────────────────────────────────────────┤"
printf "│ Memory Service (8100)      : %s                            │\n" "$(check_service http://localhost:8100/health)"
printf "│ Skills Registry (8101)     : %s                            │\n" "$(check_service http://localhost:8101/health)"
printf "│ Orchestrator (8102)        : %s                            │\n" "$(check_service http://localhost:8102/health)"
printf "│ Coder Agent (8103)         : %s                            │\n" "$(check_service http://localhost:8103/health)"
printf "│ Web Backend (8200)         : %s                            │\n" "$(check_service http://localhost:8200/health)"
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
else
    printf "│ Memory Service (18100)     : %s                            │\n" "$(check_service http://localhost:18100/health)"
    printf "│ Skills Registry (18101)    : %s                            │\n" "$(check_service http://localhost:18101/health)"
    printf "│ Orchestrator (18102)       : %s                            │\n" "$(check_service http://localhost:18102/health)"
    printf "│ Coder Agent (18103)        : %s                            │\n" "$(check_service http://localhost:18103/health)"
    printf "│ Web Backend (18200)        : %s                            │\n" "$(check_service http://localhost:18200/health)"
fi

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
dev_count=$(curl -sf http://localhost:8100/health http://localhost:8101/health http://localhost:8102/health http://localhost:8103/health http://localhost:8200/health 2>/dev/null | wc -l)
test_count=$(curl -sf http://localhost:9100/health http://localhost:9101/health http://localhost:9102/health http://localhost:9103/health http://localhost:9200/health 2>/dev/null | wc -l)

echo "📊 Summary:"
echo "   Dev:  $dev_count/5 services online"
echo "   Test: $test_count/5 services online"
echo ""
