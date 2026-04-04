#!/bin/bash

# Start Balbes in PRODUCTION mode
# Usage: ./scripts/start_prod.sh

set -e

#PROJECT_ROOT="/home/balbes/projects/dev"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
LOG_DIR="$PROJECT_ROOT/logs/prod"
PID_FILE="$PROJECT_ROOT/.pids-prod.txt"

echo "🚢 Starting Balbes - PRODUCTION MODE"
echo "========================================"
echo "Environment: PROD"
echo "Ports: services=${MEMORY_SERVICE_PORT:-18100}..${WEB_BACKEND_PORT:-18200}, infra=${POSTGRES_PORT:-15432}/${REDIS_PORT:-16379}/${QDRANT_PORT:-16333}/${RABBITMQ_PORT:-15673}"
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
    mkdir -p "$LOG_DIR"
    : > "$PID_FILE"

    cd "$PROJECT_ROOT/services/memory-service"
    ENV=prod uvicorn main:app --host 0.0.0.0 --port "${MEMORY_SERVICE_PORT:-18100}" --workers 2 > "$LOG_DIR/memory.log" 2>&1 &
    echo "$!" >> "$PID_FILE"

    cd "$PROJECT_ROOT/services/skills-registry"
    ENV=prod uvicorn main:app --host 0.0.0.0 --port "${SKILLS_REGISTRY_PORT:-18101}" --workers 2 > "$LOG_DIR/skills.log" 2>&1 &
    echo "$!" >> "$PID_FILE"

    cd "$PROJECT_ROOT/services/orchestrator"
    ENV=prod uvicorn main:app --host 0.0.0.0 --port "${ORCHESTRATOR_PORT:-18102}" --workers 1 > "$LOG_DIR/orchestrator.log" 2>&1 &
    echo "$!" >> "$PID_FILE"

    cd "$PROJECT_ROOT/services/coder"
    ENV=prod uvicorn main:app --host 0.0.0.0 --port "${CODER_PORT:-18103}" --workers 2 > "$LOG_DIR/coder.log" 2>&1 &
    echo "$!" >> "$PID_FILE"

    cd "$PROJECT_ROOT/services/web-backend"
    ENV=prod uvicorn main:app --host 0.0.0.0 --port "${WEB_BACKEND_PORT:-18200}" --workers 4 > "$LOG_DIR/web-backend.log" 2>&1 &
    echo "$!" >> "$PID_FILE"

    cd "$PROJECT_ROOT"
    ENV=prod PYTHONPATH="$PROJECT_ROOT" uvicorn services.blogger.main:app --host 0.0.0.0 --port "${BLOGGER_SERVICE_PORT:-18105}" --workers 1 > "$LOG_DIR/blogger.log" 2>&1 &
    echo "$!" >> "$PID_FILE"
    cd "$PROJECT_ROOT"

    if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
        cd "$PROJECT_ROOT/services/orchestrator"
        ENV=prod PYTHONUNBUFFERED=1 python -u telegram_bot.py > "$LOG_DIR/telegram-bot.log" 2>&1 &
        echo "$!" >> "$PID_FILE"
        echo "Started Telegram bot polling"
    else
        echo "Skipping Telegram bot (TELEGRAM_BOT_TOKEN is empty)"
    fi

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

check_service "http://localhost:${MEMORY_SERVICE_PORT:-18100}/health" "Memory Service"
check_service "http://localhost:${SKILLS_REGISTRY_PORT:-18101}/health" "Skills Registry"
check_service "http://localhost:${ORCHESTRATOR_PORT:-18102}/health" "Orchestrator"
check_service "http://localhost:${CODER_PORT:-18103}/health" "Coder Agent"
check_service "http://localhost:${WEB_BACKEND_PORT:-18200}/health" "Web Backend"
check_service "http://localhost:${BLOGGER_SERVICE_PORT:-18105}/health" "Blogger Service"
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    if pgrep -f "python telegram_bot.py" > /dev/null 2>&1; then
        echo "   ✅ Telegram Bot"
    else
        echo "   ❌ Telegram Bot FAILED"
    fi
fi
if [ -n "$BUSINESS_BOT_TOKEN" ]; then
    if pgrep -f "uvicorn.*blogger" > /dev/null 2>&1; then
        echo "   ✅ Business Bot (inside Blogger service)"
    fi
fi

echo ""
echo "========================================"
echo "✅ Production environment started!"
echo ""
echo "🌐 Access:"
echo "   API: http://localhost:${WEB_BACKEND_PORT:-18200}"
echo "   Docs: http://localhost:${WEB_BACKEND_PORT:-18200}/docs"
echo ""
echo "📊 Monitoring:"
echo "   systemctl status balbes-*"
echo "   docker ps"
echo "   ./scripts/status.sh prod"
echo ""
echo "📝 Logs:"
echo "   tail -f $LOG_DIR/*.log"
echo "   journalctl -u balbes-* -f"
echo ""
echo "🛑 Stop:"
echo "   sudo systemctl stop balbes-*"
echo "========================================"
