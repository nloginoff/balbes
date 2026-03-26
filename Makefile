.PHONY: help infra-up infra-down infra-logs dev-* prod-* db-* test clean setup

# Default target
help:
	@echo "Balbes Multi-Agent System - Available Commands"
	@echo ""
	@echo "📦 Infrastructure (Development):"
	@echo "  make infra-up        - Start infrastructure services (PostgreSQL, Redis, RabbitMQ, Qdrant)"
	@echo "  make infra-down      - Stop infrastructure services"
	@echo "  make infra-logs      - Show infrastructure logs"
	@echo "  make infra-status    - Show infrastructure status"
	@echo ""
	@echo "🚀 Development Services:"
	@echo "  make dev-memory      - Run Memory Service"
	@echo "  make dev-skills      - Run Skills Registry"
	@echo "  make dev-orch        - Run Orchestrator + Telegram bot"
	@echo "  make dev-coder       - Run Coder Agent"
	@echo "  make dev-web         - Run Web Backend API"
	@echo "  make dev-frontend    - Run Web Frontend (React)"
	@echo ""
	@echo "🏭 Production:"
	@echo "  make prod-build      - Build all Docker images"
	@echo "  make prod-up         - Start all services in production mode"
	@echo "  make prod-down       - Stop all production services"
	@echo "  make prod-restart    - Restart all production services"
	@echo "  make prod-logs       - Show all production logs"
	@echo "  make prod-status     - Show production services status"
	@echo ""
	@echo "🗄️  Database:"
	@echo "  make db-init         - Initialize PostgreSQL schema"
	@echo "  make db-seed         - Load base skills into registry"
	@echo "  make db-backup       - Backup PostgreSQL database"
	@echo "  make db-restore      - Restore PostgreSQL from backup"
	@echo "  make db-shell        - Open PostgreSQL shell"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  make test            - Run all tests"
	@echo "  make test-unit       - Run unit tests"
	@echo "  make test-integration - Run integration tests"
	@echo "  make test-e2e        - Run end-to-end tests"
	@echo "  make test-cov        - Run tests with coverage report"
	@echo ""
	@echo "✨ Code Quality:"
	@echo "  make lint            - Run ruff linting"
	@echo "  make format          - Run ruff formatting"
	@echo "  make quality         - Run all quality checks"
	@echo ""
	@echo "🧹 Cleanup:"
	@echo "  make clean           - Clean temporary files and caches"
	@echo "  make clean-logs      - Clean old log files"
	@echo "  make clean-all       - Clean everything (including Docker volumes)"
	@echo ""
	@echo "⚙️  Setup:"
	@echo "  make setup           - First time setup (infra + db-init + db-seed)"
	@echo "  make validate        - Validate configuration"

# =============================================================================
# Infrastructure (Development)
# =============================================================================

infra-up:
	@echo "🚀 Starting infrastructure services..."
	docker compose -f docker-compose.infra.yml up -d
	@echo "⏳ Waiting for services to be healthy..."
	@sleep 5
	@make infra-status

infra-down:
	@echo "🛑 Stopping infrastructure services..."
	docker compose -f docker-compose.infra.yml down

infra-logs:
	docker compose -f docker-compose.infra.yml logs -f

infra-status:
	@echo "📊 Infrastructure Status:"
	@docker compose -f docker-compose.infra.yml ps

# =============================================================================
# Development Services
# =============================================================================

dev-memory:
	@echo "🧠 Starting Memory Service..."
	cd services/memory-service && uvicorn main:app --reload --host 0.0.0.0 --port 8100

dev-skills:
	@echo "🛠️  Starting Skills Registry..."
	cd services/skills-registry && uvicorn main:app --reload --host 0.0.0.0 --port 8101

dev-orch:
	@echo "🎯 Starting Orchestrator Agent..."
	cd services/orchestrator && python main.py

dev-coder:
	@echo "💻 Starting Coder Agent..."
	cd services/coder && python main.py

dev-web:
	@echo "🌐 Starting Web Backend..."
	cd services/web/backend && uvicorn main:app --reload --host 0.0.0.0 --port 8200

dev-frontend:
	@echo "⚛️  Starting Web Frontend..."
	cd services/web/frontend && npm run dev

# =============================================================================
# Production
# =============================================================================

prod-build:
	@echo "🏗️  Building Docker images..."
	docker-compose -f docker-compose.prod.yml build

prod-up:
	@echo "🚀 Starting production services..."
	docker-compose -f docker-compose.prod.yml up -d
	@echo "⏳ Waiting for services to be healthy..."
	@sleep 10
	@make prod-status

prod-down:
	@echo "🛑 Stopping production services..."
	docker-compose -f docker-compose.prod.yml down

prod-restart:
	@echo "🔄 Restarting production services..."
	docker-compose -f docker-compose.prod.yml restart

prod-logs:
	docker-compose -f docker-compose.prod.yml logs -f

prod-status:
	@echo "📊 Production Services Status:"
	@docker-compose -f docker-compose.prod.yml ps

# =============================================================================
# Database Operations
# =============================================================================

db-init:
	@echo "🗄️  Initializing PostgreSQL schema..."
	python scripts/init_db.py

db-seed:
	@echo "🌱 Seeding base skills..."
	python scripts/seed_skills.py

db-backup:
	@echo "💾 Backing up PostgreSQL..."
	@mkdir -p backups
	docker exec balbes-postgres pg_dump -U balbes balbes_agents > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "✅ Backup created in backups/"

db-restore:
	@echo "📥 Restore PostgreSQL backup"
	@echo "Usage: make db-restore FILE=backups/backup_20260326_030000.sql"
	@if [ -z "$(FILE)" ]; then \
		echo "❌ Error: FILE parameter required"; \
		exit 1; \
	fi
	docker exec -i balbes-postgres psql -U balbes balbes_agents < $(FILE)
	@echo "✅ Database restored"

db-shell:
	@echo "🐘 Opening PostgreSQL shell..."
	docker exec -it balbes-postgres psql -U balbes -d balbes_agents

redis-shell:
	@echo "📮 Opening Redis CLI..."
	docker exec -it balbes-redis redis-cli

# =============================================================================
# Testing
# =============================================================================

test:
	@echo "🧪 Running all tests..."
	pytest

test-unit:
	@echo "🧪 Running unit tests..."
	pytest tests/unit -v

test-integration:
	@echo "🧪 Running integration tests..."
	pytest tests/integration -v

test-e2e:
	@echo "🧪 Running end-to-end tests..."
	pytest tests/e2e -v

test-cov:
	@echo "🧪 Running tests with coverage..."
	pytest --cov=shared --cov=services --cov-report=html --cov-report=term
	@echo "📊 Coverage report generated: htmlcov/index.html"

# =============================================================================
# Code Quality
# =============================================================================

lint:
	@echo "🔍 Running ruff linting..."
	ruff check .

format:
	@echo "✨ Running ruff formatting..."
	ruff format .

quality: lint
	@echo "✅ Code quality checks complete"

# =============================================================================
# Cleanup
# =============================================================================

clean:
	@echo "🧹 Cleaning temporary files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage 2>/dev/null || true
	@echo "✅ Cleanup complete"

clean-logs:
	@echo "🧹 Cleaning old log files..."
	find data/logs -name "*.log" -mtime +7 -delete 2>/dev/null || true
	@echo "✅ Old logs deleted"

clean-all: clean clean-logs
	@echo "🧹 Cleaning all data and Docker volumes..."
	@read -p "⚠️  This will delete ALL data. Continue? (y/N): " confirm && [ "$$confirm" = "y" ]
	docker-compose -f docker-compose.infra.yml down -v
	rm -rf data/postgres data/redis data/rabbitmq data/qdrant
	@echo "✅ Complete cleanup done"

# =============================================================================
# Setup & Validation
# =============================================================================

setup: infra-up db-init db-seed
	@echo ""
	@echo "✅ Setup complete!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Review .env file (make sure API keys are set)"
	@echo "  2. Start services:"
	@echo "     Terminal 1: make dev-memory"
	@echo "     Terminal 2: make dev-skills"
	@echo "     Terminal 3: make dev-orch"
	@echo "     Terminal 4: make dev-coder"
	@echo "     Terminal 5: make dev-web"
	@echo "     Terminal 6: make dev-frontend"
	@echo "  3. Test Telegram bot: /start"
	@echo "  4. Open Web UI: http://localhost:5173"

validate:
	@echo "🔍 Validating configuration..."
	python scripts/validate_config.py

# =============================================================================
# Utilities
# =============================================================================

diagnostic:
	@echo "🔍 Running system diagnostic..."
	@bash scripts/diagnostic.sh

healthcheck:
	@echo "🏥 Checking service health..."
	@bash scripts/healthcheck.sh

logs-errors:
	@echo "❌ Recent errors from all services:"
	@cat data/logs/*.log 2>/dev/null | jq 'select(.status == "error")' | tail -20

tokens-today:
	@echo "💰 Token usage today:"
	@psql -h localhost -U balbes -d balbes_agents -t -c "SELECT * FROM v_tokens_today;"

# =============================================================================
# Documentation
# =============================================================================

docs:
	@echo "📚 Available documentation:"
	@ls -1 docs/*.md | sed 's/^/  - /'
	@echo ""
	@echo "Start with: docs/QUICKSTART.md"

# =============================================================================
# Development Shortcuts
# =============================================================================

# Быстрый restart агента в dev mode
restart-orch:
	@pkill -f "python.*orchestrator/main.py" || true
	@sleep 1
	@make dev-orch

restart-coder:
	@pkill -f "python.*coder/main.py" || true
	@sleep 1
	@make dev-coder

# Показать все запущенные Python процессы (агенты)
ps-agents:
	@echo "🤖 Running agent processes:"
	@ps aux | grep -E "orchestrator|coder" | grep -v grep
