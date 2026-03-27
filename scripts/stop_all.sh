#!/bin/bash

# Stop all Balbes services
# Usage: ./scripts/stop_all.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🛑 Stopping Balbes Multi-Agent System..."
echo "========================================"

# Read PIDs
if [ -f /tmp/balbes-pids.txt ]; then
    echo ""
    echo "Stopping services..."

    while IFS= read -r pid; do
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "   Killing PID: $pid"
            kill "$pid" 2>/dev/null || true
        fi
    done < /tmp/balbes-pids.txt

    rm /tmp/balbes-pids.txt
else
    echo "No PID file found, searching for processes..."

    # Kill by port
    for port in 8100 8101 8102 8103 8200; do
        pid=$(lsof -ti:$port 2>/dev/null || true)
        if [ -n "$pid" ]; then
            echo "   Killing process on port $port (PID: $pid)"
            kill $pid 2>/dev/null || true
        fi
    done
fi

# Wait for processes to stop
sleep 2

# Stop Docker infrastructure (optional)
read -p "Stop Docker infrastructure (Redis, PostgreSQL, Qdrant)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Stopping Docker containers..."
    sg docker -c 'docker compose -f docker-compose.dev.yml down'
fi

echo ""
echo "========================================"
echo "✅ All services stopped!"
echo "========================================"
