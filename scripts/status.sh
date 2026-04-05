#!/bin/bash

# Check status of all Balbes services
# Usage: ./scripts/status.sh

echo "📊 Balbes System Status"
echo "========================================"

# Infrastructure
echo ""
echo "🐳 Infrastructure (Docker):"
docker ps --filter "name=balbes-" --format "   {{.Names}}: {{.Status}}" 2>/dev/null || echo "   Docker not accessible"

# Services
echo ""
echo "🔧 Microservices:"

check_service() {
    local url=$1
    local name=$2
    local port=$3

    if curl -sf "$url" > /dev/null 2>&1; then
        echo "   ✅ $name (port $port): HEALTHY"
    else
        pid=$(lsof -ti:$port 2>/dev/null || true)
        if [ -n "$pid" ]; then
            echo "   ⚠️  $name (port $port): RUNNING but not responding (PID: $pid)"
        else
            echo "   ❌ $name (port $port): OFFLINE"
        fi
    fi
}

check_service "http://localhost:8100/health" "Memory Service" 8100
check_service "http://localhost:8101/health" "Skills Registry" 8101
check_service "http://localhost:8102/health" "Orchestrator" 8102
check_service "http://localhost:8103/health" "Coder Agent" 8103
check_service "http://localhost:8200/health" "Web Backend" 8200
check_service "http://localhost:8105/health" "Blogger Service" 8105
check_service "http://localhost:5173" "Frontend" 5173

# Database connections
echo ""
echo "💾 Database Connections:"
if psql -h localhost -U balbes -d balbes -c "SELECT 1;" > /dev/null 2>&1; then
    echo "   ✅ PostgreSQL: CONNECTED"
else
    echo "   ❌ PostgreSQL: OFFLINE"
fi

if redis-cli -h localhost ping > /dev/null 2>&1; then
    echo "   ✅ Redis: CONNECTED"
else
    echo "   ❌ Redis: OFFLINE"
fi

if curl -sf http://localhost:6333/health > /dev/null 2>&1; then
    echo "   ✅ Qdrant: CONNECTED"
else
    echo "   ❌ Qdrant: OFFLINE"
fi

echo ""
echo "========================================"

# Count running services (HTTP apps + frontend + db + redis)
total=9
running=$(curl -sf http://localhost:8100/health > /dev/null 2>&1 && echo 1 || echo 0)
running=$((running + $(curl -sf http://localhost:8101/health > /dev/null 2>&1 && echo 1 || echo 0)))
running=$((running + $(curl -sf http://localhost:8102/health > /dev/null 2>&1 && echo 1 || echo 0)))
running=$((running + $(curl -sf http://localhost:8103/health > /dev/null 2>&1 && echo 1 || echo 0)))
running=$((running + $(curl -sf http://localhost:8200/health > /dev/null 2>&1 && echo 1 || echo 0)))
running=$((running + $(curl -sf http://localhost:8105/health > /dev/null 2>&1 && echo 1 || echo 0)))
running=$((running + $(curl -sf http://localhost:5173 > /dev/null 2>&1 && echo 1 || echo 0)))
running=$((running + $(psql -h localhost -U balbes -d balbes -c "SELECT 1;" > /dev/null 2>&1 && echo 1 || echo 0)))
running=$((running + $(redis-cli -h localhost ping > /dev/null 2>&1 && echo 1 || echo 0)))

echo "Summary: $running/$total services operational"
echo ""
