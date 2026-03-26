#!/bin/bash

# Stop Balbes TESTING environment
# Usage: ./scripts/stop_test.sh

echo "🛑 Stopping Balbes - TESTING MODE"
echo "========================================"

# Kill test services
if [ -f /tmp/balbes-test-pids.txt ]; then
    while IFS= read -r pid; do
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "   Stopping PID: $pid"
            kill "$pid" 2>/dev/null || true
        fi
    done < /tmp/balbes-test-pids.txt
    rm /tmp/balbes-test-pids.txt
fi

# Kill by port (test ports)
for port in 9100 9101 9102 9103 9200; do
    pid=$(lsof -ti:$port 2>/dev/null || true)
    if [ -n "$pid" ]; then
        echo "   Stopping service on port $port (PID: $pid)"
        kill $pid 2>/dev/null || true
    fi
done

sleep 2

# Stop and cleanup Docker (test always cleans up)
echo ""
echo "🧹 Cleaning up Docker test infrastructure..."
cd /home/balbes/projects/dev
sg docker -c 'docker-compose -f docker-compose.test.yml down -v'

# Cleanup logs
rm -f /tmp/balbes-test-*.log

echo ""
echo "✅ Test environment stopped and cleaned up!"
