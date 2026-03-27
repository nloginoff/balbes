#!/bin/bash

# Stop Balbes DEVELOPMENT environment
# Usage: ./scripts/stop_dev.sh

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🛑 Stopping Balbes - DEVELOPMENT MODE"
echo "========================================"

# Kill dev services
if [ -f /tmp/balbes-dev-pids.txt ]; then
    while IFS= read -r pid; do
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "   Stopping PID: $pid"
            kill "$pid" 2>/dev/null || true
        fi
    done < /tmp/balbes-dev-pids.txt
    rm /tmp/balbes-dev-pids.txt
fi

# Kill by port
for port in 8100 8101 8102 8103 8200; do
    pid=$(lsof -ti:$port 2>/dev/null || true)
    if [ -n "$pid" ]; then
        echo "   Stopping service on port $port (PID: $pid)"
        kill $pid 2>/dev/null || true
    fi
done

sleep 2

# Optional: Stop Docker
read -p "Stop Docker infrastructure (dev)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sg docker -c 'docker compose -f docker-compose.dev.yml down'
fi

# Cleanup logs
rm -f /tmp/balbes-dev-*.log

echo ""
echo "✅ Development environment stopped!"
