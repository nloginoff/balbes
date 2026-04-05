#!/bin/bash

# Stop Balbes PRODUCTION environment
# Usage: ./scripts/stop_prod.sh

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
PID_FILE="$PROJECT_ROOT/.pids-prod.txt"

echo "🛑 Stopping Balbes - PRODUCTION MODE"
echo "========================================"
echo ""
echo "⚠️  WARNING: This will stop production services!"
echo ""
echo "Proceeding without interactive confirmation (script mode)."

# Stop systemd services if they exist
if systemctl list-unit-files | grep -q balbes-memory; then
    echo "Stopping systemd services..."
    sudo systemctl stop balbes-memory balbes-skills balbes-orchestrator balbes-coder balbes-web-backend
    if systemctl list-unit-files 2>/dev/null | grep -q '^balbes-blogger.service'; then
        sudo systemctl stop balbes-blogger
    fi
else
    # Kill manual processes
    if [ -f "$PID_FILE" ]; then
        echo "Stopping manual processes..."
        while IFS= read -r pid; do
            if ps -p "$pid" > /dev/null 2>&1; then
                echo "   Stopping PID: $pid"
                kill "$pid" 2>/dev/null || true
            fi
        done < "$PID_FILE"
    fi
fi

sleep 2

# Force-stop any remaining prod services by PID file
if [ -f "$PID_FILE" ]; then
    while IFS= read -r pid; do
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "   Force stopping PID: $pid"
            kill -9 "$pid" 2>/dev/null || true
        fi
    done < "$PID_FILE"
    rm -f "$PID_FILE"
fi

# Also stop Telegram bot polling process if running
telegram_pids=$(pgrep -f "python telegram_bot.py" || true)
if [ -n "$telegram_pids" ]; then
    for pid in $telegram_pids; do
        echo "   Stopping Telegram bot PID: $pid"
        kill "$pid" 2>/dev/null || true
    done
fi

# Fallback: kill anything still bound to prod ports
echo "Checking for leftover prod processes on ports..."
for port in 18100 18101 18102 18103 18105 18200; do
    pids=$(lsof -ti:"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        for pid in $pids; do
            echo "   Killing process on port $port (PID: $pid)"
            kill "$pid" 2>/dev/null || true
        done
    fi
done

sleep 1

# Last pass with SIGKILL for stubborn workers
for port in 18100 18101 18102 18103 18105 18200; do
    pids=$(lsof -ti:"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        for pid in $pids; do
            echo "   Force killing process on port $port (PID: $pid)"
            kill -9 "$pid" 2>/dev/null || true
        done
    fi
done

# Docker stays running for production (data persistence)
echo ""
echo "📦 Production Docker containers kept running (data persistence)"
echo "   To stop Docker: cd \"$PROJECT_ROOT\" && sg docker -c 'docker compose -f docker-compose.prod.yml down'"
echo ""
echo "✅ Production services stopped!"
echo "   Infrastructure still running (PostgreSQL, Redis, Qdrant)"
