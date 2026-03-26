#!/bin/bash

# Start all Balbes services
# Usage: ./scripts/start_all.sh

set -e

PROJECT_ROOT="/home/balbes/projects/dev"
cd "$PROJECT_ROOT"

echo "🚀 Starting Balbes Multi-Agent System..."
echo "========================================"

# Activate virtual environment
source .venv/bin/activate

# Check if infrastructure is running
echo ""
echo "📦 Checking infrastructure..."
if ! docker ps | grep -q balbes-redis; then
    echo "Starting Docker infrastructure..."
    sg docker -c 'docker compose up -d'
    echo "Waiting for infrastructure to be ready..."
    sleep 10
fi

# Initialize database if needed
echo ""
echo "💾 Initializing database..."
python scripts/init_db.py 2>/dev/null || echo "Database already initialized"

# Start Memory Service
echo ""
echo "🧠 Starting Memory Service (port 8100)..."
cd "$PROJECT_ROOT/services/memory-service"
uvicorn main:app --host 0.0.0.0 --port 8100 > /tmp/balbes-memory.log 2>&1 &
MEMORY_PID=$!
echo "   PID: $MEMORY_PID"
sleep 2

# Start Skills Registry
echo ""
echo "⚡ Starting Skills Registry (port 8101)..."
cd "$PROJECT_ROOT/services/skills-registry"
uvicorn main:app --host 0.0.0.0 --port 8101 > /tmp/balbes-skills.log 2>&1 &
SKILLS_PID=$!
echo "   PID: $SKILLS_PID"
sleep 2

# Start Orchestrator
echo ""
echo "🎯 Starting Orchestrator (port 8102)..."
cd "$PROJECT_ROOT/services/orchestrator"
uvicorn main:app --host 0.0.0.0 --port 8102 > /tmp/balbes-orchestrator.log 2>&1 &
ORCH_PID=$!
echo "   PID: $ORCH_PID"
sleep 2

# Start Coder Agent
echo ""
echo "💻 Starting Coder Agent (port 8103)..."
cd "$PROJECT_ROOT/services/coder"
uvicorn main:app --host 0.0.0.0 --port 8103 > /tmp/balbes-coder.log 2>&1 &
CODER_PID=$!
echo "   PID: $CODER_PID"
sleep 2

# Start Web Backend
echo ""
echo "🌐 Starting Web Backend (port 8200)..."
cd "$PROJECT_ROOT/services/web-backend"
uvicorn main:app --host 0.0.0.0 --port 8200 > /tmp/balbes-web-backend.log 2>&1 &
BACKEND_PID=$!
echo "   PID: $BACKEND_PID"
sleep 2

# Save PIDs
echo "$MEMORY_PID" > /tmp/balbes-pids.txt
echo "$SKILLS_PID" >> /tmp/balbes-pids.txt
echo "$ORCH_PID" >> /tmp/balbes-pids.txt
echo "$CODER_PID" >> /tmp/balbes-pids.txt
echo "$BACKEND_PID" >> /tmp/balbes-pids.txt

# Verify services
echo ""
echo "🔍 Verifying services..."
sleep 3

check_service() {
    local url=$1
    local name=$2

    if curl -sf "$url" > /dev/null 2>&1; then
        echo "   ✅ $name: HEALTHY"
        return 0
    else
        echo "   ❌ $name: FAILED"
        return 1
    fi
}

check_service "http://localhost:8100/health" "Memory Service"
check_service "http://localhost:8101/health" "Skills Registry"
check_service "http://localhost:8102/health" "Orchestrator"
check_service "http://localhost:8103/health" "Coder Agent"
check_service "http://localhost:8200/health" "Web Backend"

echo ""
echo "========================================"
echo "✅ All services started!"
echo ""
echo "Service URLs:"
echo "   Memory Service:   http://localhost:8100"
echo "   Skills Registry:  http://localhost:8101"
echo "   Orchestrator:     http://localhost:8102"
echo "   Coder Agent:      http://localhost:8103"
echo "   Web Backend:      http://localhost:8200"
echo ""
echo "Logs:"
echo "   Memory:       tail -f /tmp/balbes-memory.log"
echo "   Skills:       tail -f /tmp/balbes-skills.log"
echo "   Orchestrator: tail -f /tmp/balbes-orchestrator.log"
echo "   Coder:        tail -f /tmp/balbes-coder.log"
echo "   Web Backend:  tail -f /tmp/balbes-web-backend.log"
echo ""
echo "To start frontend:"
echo "   cd $PROJECT_ROOT/web-frontend && npm run dev"
echo ""
echo "To stop all services:"
echo "   ./scripts/stop_all.sh"
echo "========================================"
