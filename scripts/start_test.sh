#!/bin/bash

# Start Balbes in TESTING mode
# Usage: ./scripts/start_test.sh

set -e

PROJECT_ROOT="/home/balbes/projects/dev"
cd "$PROJECT_ROOT"

echo "🧪 Starting Balbes - TESTING MODE"
echo "========================================"
echo "Environment: TEST"
echo "Ports: 9100-9200, Frontend: 5174"
echo "Database: balbes_test (port 5433)"
echo ""

# Load test environment
if [ -f .env.test ]; then
    export $(cat .env.test | grep -v '^#' | xargs)
    echo "✅ Loaded .env.test"
else
    echo "❌ .env.test not found!"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate
echo "✅ Activated Python virtual environment"

# Start Docker infrastructure (test - uses tmpfs, no persistence)
echo ""
echo "📦 Starting Docker infrastructure (test)..."
sg docker -c 'docker-compose -f docker-compose.test.yml down -v 2>/dev/null || true'
sg docker -c 'docker-compose -f docker-compose.test.yml up -d'
echo "⏳ Waiting for test infrastructure..."
sleep 10

# Initialize test database
echo ""
echo "💾 Initializing test database..."
POSTGRES_PORT=5433 POSTGRES_DB=balbes_test python scripts/init_db.py

# Start Memory Service (test ports)
echo ""
echo "🧠 Starting Memory Service (port 9100)..."
cd "$PROJECT_ROOT/services/memory-service"
uvicorn main:app --host 0.0.0.0 --port 9100 > /tmp/balbes-test-memory.log 2>&1 &
MEMORY_PID=$!
sleep 2

# Start Skills Registry
echo ""
echo "⚡ Starting Skills Registry (port 9101)..."
cd "$PROJECT_ROOT/services/skills-registry"
uvicorn main:app --host 0.0.0.0 --port 9101 > /tmp/balbes-test-skills.log 2>&1 &
SKILLS_PID=$!
sleep 2

# Start Orchestrator
echo ""
echo "🎯 Starting Orchestrator (port 9102)..."
cd "$PROJECT_ROOT/services/orchestrator"
uvicorn main:app --host 0.0.0.0 --port 9102 > /tmp/balbes-test-orchestrator.log 2>&1 &
ORCH_PID=$!
sleep 2

# Start Coder Agent
echo ""
echo "💻 Starting Coder Agent (port 9103)..."
cd "$PROJECT_ROOT/services/coder"
uvicorn main:app --host 0.0.0.0 --port 9103 > /tmp/balbes-test-coder.log 2>&1 &
CODER_PID=$!
sleep 2

# Start Web Backend
echo ""
echo "🌐 Starting Web Backend (port 9200)..."
cd "$PROJECT_ROOT/services/web-backend"
uvicorn main:app --host 0.0.0.0 --port 9200 > /tmp/balbes-test-web-backend.log 2>&1 &
BACKEND_PID=$!
sleep 2

# Save PIDs
echo "$MEMORY_PID" > /tmp/balbes-test-pids.txt
echo "$SKILLS_PID" >> /tmp/balbes-test-pids.txt
echo "$ORCH_PID" >> /tmp/balbes-test-pids.txt
echo "$CODER_PID" >> /tmp/balbes-test-pids.txt
echo "$BACKEND_PID" >> /tmp/balbes-test-pids.txt

# Verify
echo ""
echo "🔍 Verifying test services..."
sleep 3

cd "$PROJECT_ROOT"

check_service() {
    local url=$1
    local name=$2

    if curl -sf "$url" > /dev/null 2>&1; then
        echo "   ✅ $name"
        return 0
    else
        echo "   ⚠️  $name (starting...)"
        return 1
    fi
}

check_service "http://localhost:9100/health" "Memory (9100)"
check_service "http://localhost:9101/health" "Skills (9101)"
check_service "http://localhost:9102/health" "Orchestrator (9102)"
check_service "http://localhost:9103/health" "Coder (9103)"
check_service "http://localhost:9200/health" "Web Backend (9200)"

echo ""
echo "========================================"
echo "✅ Test environment ready!"
echo ""
echo "🧪 Run tests:"
echo "   pytest tests/test_e2e.py -v"
echo "   pytest tests/test_performance.py -v"
echo "   pytest tests/ -v"
echo ""
echo "📋 Test URLs:"
echo "   Memory:   http://localhost:9100/docs"
echo "   Skills:   http://localhost:9101/docs"
echo "   Orch:     http://localhost:9102/docs"
echo "   Coder:    http://localhost:9103/docs"
echo "   Backend:  http://localhost:9200/docs"
echo ""
echo "🛑 Stop & cleanup:"
echo "   ./scripts/stop_test.sh"
echo "========================================"
