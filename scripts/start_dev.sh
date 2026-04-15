#!/bin/bash

# Start Balbes in DEVELOPMENT mode
# Usage: ./scripts/start_dev.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🚀 Starting Balbes - DEVELOPMENT MODE"
echo "========================================"
echo "Environment: DEV"
echo "Ports: 8100-8200, 8180 webhooks, 8105 blogger, Frontend: 5173"
echo "Database: balbes_dev"
echo ""

# Load dev environment
if [ -f .env.dev ]; then
    export $(cat .env.dev | grep -v '^#' | xargs)
    echo "✅ Loaded .env.dev"
else
    echo "❌ .env.dev not found!"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate
echo "✅ Activated Python virtual environment"

# Start Docker infrastructure (dev)
echo ""
echo "📦 Starting Docker infrastructure (dev)..."
if ! docker ps | grep -q balbes-dev-postgres; then
    sg docker -c 'docker compose -f docker-compose.dev.yml up -d'
    echo "⏳ Waiting for infrastructure to be ready..."
    sleep 10
else
    echo "✅ Dev infrastructure already running"
fi

# Initialize dev database
echo ""
echo "💾 Initializing dev database..."
python scripts/init_db.py 2>/dev/null || echo "   Dev database already initialized"

# Start Memory Service
echo ""
echo "🧠 Starting Memory Service (port 8100)..."
cd "$PROJECT_ROOT/services/memory-service"
uvicorn main:app --host 0.0.0.0 --port 8100 --reload > /tmp/balbes-dev-memory.log 2>&1 &
MEMORY_PID=$!
echo "   PID: $MEMORY_PID"
sleep 2

# Start Skills Registry
echo ""
echo "⚡ Starting Skills Registry (port 8101)..."
cd "$PROJECT_ROOT/services/skills-registry"
uvicorn main:app --host 0.0.0.0 --port 8101 --reload > /tmp/balbes-dev-skills.log 2>&1 &
SKILLS_PID=$!
echo "   PID: $SKILLS_PID"
sleep 2

# Start Orchestrator
echo ""
echo "🎯 Starting Orchestrator (port 8102)..."
cd "$PROJECT_ROOT/services/orchestrator"
uvicorn main:app --host 0.0.0.0 --port 8102 --reload > /tmp/balbes-dev-orchestrator.log 2>&1 &
ORCH_PID=$!
echo "   PID: $ORCH_PID"
sleep 2

# Start Coder Agent
echo ""
echo "💻 Starting Coder Agent (port 8103)..."
cd "$PROJECT_ROOT/services/coder"
uvicorn main:app --host 0.0.0.0 --port 8103 --reload > /tmp/balbes-dev-coder.log 2>&1 &
CODER_PID=$!
echo "   PID: $CODER_PID"
sleep 2

# Start Web Backend
echo ""
echo "🌐 Starting Web Backend (port 8200)..."
cd "$PROJECT_ROOT/services/web-backend"
PYTHONPATH="$PROJECT_ROOT" uvicorn main:app --host 0.0.0.0 --port 8200 --reload > /tmp/balbes-dev-web-backend.log 2>&1 &
BACKEND_PID=$!
echo "   PID: $BACKEND_PID"
sleep 2

# Webhooks Gateway (Telegram / MAX / monitoring notify — not the dashboard)
echo ""
echo "🔔 Starting Webhooks Gateway (port 8180)..."
cd "$PROJECT_ROOT/services/webhooks_gateway"
PYTHONPATH="$PROJECT_ROOT" uvicorn main:app --host 0.0.0.0 --port 8180 --reload > /tmp/balbes-dev-webhooks.log 2>&1 &
WEBHOOKS_PID=$!
echo "   PID: $WEBHOOKS_PID"
sleep 2

# Start Blogger (FastAPI: posts API + scheduled jobs; business bot if token set)
echo ""
echo "📝 Starting Blogger Service (port ${BLOGGER_SERVICE_PORT:-8105})..."
cd "$PROJECT_ROOT"
PYTHONPATH="$PROJECT_ROOT" uvicorn services.blogger.main:app --host 0.0.0.0 --port "${BLOGGER_SERVICE_PORT:-8105}" --reload > /tmp/balbes-dev-blogger.log 2>&1 &
BLOGGER_PID=$!
echo "   PID: $BLOGGER_PID"
sleep 2

# Save PIDs
echo "$MEMORY_PID" > /tmp/balbes-dev-pids.txt
echo "$SKILLS_PID" >> /tmp/balbes-dev-pids.txt
echo "$ORCH_PID" >> /tmp/balbes-dev-pids.txt
echo "$CODER_PID" >> /tmp/balbes-dev-pids.txt
echo "$BACKEND_PID" >> /tmp/balbes-dev-pids.txt
echo "$WEBHOOKS_PID" >> /tmp/balbes-dev-pids.txt
echo "$BLOGGER_PID" >> /tmp/balbes-dev-pids.txt

# Verify services
echo ""
echo "🔍 Verifying services..."
sleep 3

check_service() {
    local url=$1
    local name=$2

    if curl -sf "$url" > /dev/null 2>&1; then
        echo "   ✅ $name"
        return 0
    else
        echo "   ❌ $name"
        return 1
    fi
}

check_service "http://localhost:8100/health" "Memory Service"
check_service "http://localhost:8101/health" "Skills Registry"
check_service "http://localhost:8102/health" "Orchestrator"
check_service "http://localhost:8103/health" "Coder Agent"
check_service "http://localhost:8200/health" "Web Backend"
check_service "http://localhost:8180/health" "Webhooks Gateway"
check_service "http://localhost:${BLOGGER_SERVICE_PORT:-8105}/health" "Blogger Service"

echo ""
echo "========================================"
echo "✅ Development environment started!"
echo ""
echo "📋 URLs:"
echo "   Memory:       http://localhost:8100/docs"
echo "   Skills:       http://localhost:8101/docs"
echo "   Orchestrator: http://localhost:8102/docs"
echo "   Coder:        http://localhost:8103/docs"
echo "   Web Backend:       http://localhost:8200/docs"
echo "   Webhooks Gateway:  http://localhost:8180/docs"
echo "   Blogger:           http://localhost:${BLOGGER_SERVICE_PORT:-8105}/docs"
echo ""
echo "🔧 Frontend (run in separate terminal):"
echo "   cd web-frontend && npm run dev"
echo "   http://localhost:5173"
echo ""
echo "📊 Logs:"
echo "   tail -f /tmp/balbes-dev-*.log"
echo ""
echo "🛑 Stop:"
echo "   ./scripts/stop_dev.sh"
echo "========================================"
