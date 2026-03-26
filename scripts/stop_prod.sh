#!/bin/bash

# Stop Balbes PRODUCTION environment
# Usage: ./scripts/stop_prod.sh

echo "🛑 Stopping Balbes - PRODUCTION MODE"
echo "========================================"
echo ""
echo "⚠️  WARNING: This will stop production services!"
echo ""
read -p "Are you sure? [y/N] " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# Stop systemd services if they exist
if systemctl list-unit-files | grep -q balbes-memory; then
    echo "Stopping systemd services..."
    sudo systemctl stop balbes-memory balbes-skills balbes-orchestrator balbes-coder balbes-web-backend
else
    # Kill manual processes
    if [ -f /tmp/balbes-prod-pids.txt ]; then
        echo "Stopping manual processes..."
        while IFS= read -r pid; do
            if ps -p "$pid" > /dev/null 2>&1; then
                echo "   Stopping PID: $pid"
                kill "$pid" 2>/dev/null || true
            fi
        done < /tmp/balbes-prod-pids.txt
        rm /tmp/balbes-prod-pids.txt
    fi
fi

sleep 2

# Docker stays running for production (data persistence)
echo ""
echo "📦 Production Docker containers kept running (data persistence)"
echo "   To stop Docker: sg docker -c 'docker-compose -f docker-compose.prod.yml down'"
echo ""
echo "✅ Production services stopped!"
echo "   Infrastructure still running (PostgreSQL, Redis, Qdrant)"
