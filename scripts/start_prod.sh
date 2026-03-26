#!/bin/bash

# Start Balbes in PRODUCTION mode
# Usage: ./scripts/start_prod.sh

set -e

PROJECT_ROOT="/home/balbes/projects/dev"
cd "$PROJECT_ROOT"

echo "🚢 Starting Balbes - PRODUCTION MODE"
echo "========================================"
echo "Environment: PROD"
echo "Ports: 8100-8200"
echo "Database: balbes"
echo ""

# Load prod environment
if [ -f .env.prod ]; then
    # Check if passwords are still default
    if grep -q "CHANGE_ME" .env.prod; then
        echo "❌ ERROR: .env.prod contains default passwords!"
        echo "   Please update POSTGRES_PASSWORD, REDIS_PASSWORD, QDRANT_API_KEY"
        echo "   Also update JWT_SECRET_KEY with: openssl rand -hex 32"
        exit 1
    fi

    export $(cat .env.prod | grep -v '^#' | xargs)
    echo "✅ Loaded .env.prod"
else
    echo "❌ .env.prod not found!"
    exit 1
fi

# Verify critical configs
if [ -z "$POSTGRES_PASSWORD" ] || [ -z "$JWT_SECRET_KEY" ]; then
    echo "❌ ERROR: Missing critical configuration!"
    exit 1
fi

# Start Docker infrastructure (prod)
echo ""
echo "📦 Starting Docker infrastructure (prod)..."
sg docker -c 'docker compose -f docker-compose.prod.yml up -d'
echo "⏳ Waiting for infrastructure to be ready..."
sleep 15

# Initialize prod database
echo ""
echo "💾 Initializing production database..."
python scripts/init_db.py 2>/dev/null || echo "   Production database already initialized"

# Build frontend
echo ""
echo "🎨 Building frontend for production..."
cd "$PROJECT_ROOT/web-frontend"
if [ ! -d "dist" ] || [ "$(find src -newer dist -print -quit)" ]; then
    npm run build
    echo "✅ Frontend built"
else
    echo "✅ Frontend already built"
fi

# Start services via Docker or systemd
echo ""
echo "🚀 Starting production services..."

# Option 1: Run services directly (systemd recommended)
cd "$PROJECT_ROOT"

# Check if systemd services exist
if systemctl list-unit-files | grep -q balbes-memory; then
    echo "Using systemd services..."
    sudo systemctl start balbes-memory balbes-skills balbes-orchestrator balbes-coder balbes-web-backend
else
    echo "Starting services manually..."

    source .venv/bin/activate

    cd "$PROJECT_ROOT/services/memory-service"
    uvicorn main:app --host 0.0.0.0 --port 8100 --workers 2 > /var/log/balbes-memory.log 2>&1 &
    echo "$!" >> /tmp/balbes-prod-pids.txt

    cd "$PROJECT_ROOT/services/skills-registry"
    uvicorn main:app --host 0.0.0.0 --port 8101 --workers 2 > /var/log/balbes-skills.log 2>&1 &
    echo "$!" >> /tmp/balbes-prod-pids.txt

    cd "$PROJECT_ROOT/services/orchestrator"
    uvicorn main:app --host 0.0.0.0 --port 8102 --workers 2 > /var/log/balbes-orchestrator.log 2>&1 &
    echo "$!" >> /tmp/balbes-prod-pids.txt

    cd "$PROJECT_ROOT/services/coder"
    uvicorn main:app --host 0.0.0.0 --port 8103 --workers 2 > /var/log/balbes-coder.log 2>&1 &
    echo "$!" >> /tmp/balbes-prod-pids.txt

    cd "$PROJECT_ROOT/services/web-backend"
    uvicorn main:app --host 0.0.0.0 --port 8200 --workers 4 > /var/log/balbes-web-backend.log 2>&1 &
    echo "$!" >> /tmp/balbes-prod-pids.txt

    sleep 5
fi

# Verify
echo ""
echo "🔍 Verifying production services..."

check_service() {
    local url=$1
    local name=$2

    if curl -sf "$url" > /dev/null 2>&1; then
        echo "   ✅ $name"
        return 0
    else
        echo "   ❌ $name FAILED"
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
echo "✅ Production environment started!"
echo ""
echo "🌐 Access:"
echo "   API: http://localhost:8200"
echo "   Docs: http://localhost:8200/docs"
echo ""
echo "📊 Monitoring:"
echo "   systemctl status balbes-*"
echo "   docker ps"
echo "   ./scripts/status.sh prod"
echo ""
echo "📝 Logs:"
echo "   tail -f /var/log/balbes-*.log"
echo "   journalctl -u balbes-* -f"
echo ""
echo "🛑 Stop:"
echo "   sudo systemctl stop balbes-*"
echo "========================================"
