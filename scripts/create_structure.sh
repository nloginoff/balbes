#!/bin/bash
# Create complete project structure

set -e

echo "Creating Balbes Multi-Agent System structure..."
echo ""

# Services
echo "📁 Creating service directories..."
mkdir -p services/orchestrator/{handlers,prompts}
mkdir -p services/coder/{prompts,templates}
mkdir -p services/memory-service/{api,clients,services}
mkdir -p services/skills-registry
mkdir -p services/web/backend/{api,websocket}
mkdir -p services/web/frontend/src/{pages,components/{ui},hooks,store,api,types,lib}
echo "  ✅ Services"

# Shared
echo "📁 Creating shared directory..."
mkdir -p shared/skills
touch shared/__init__.py
touch shared/skills/__init__.py
echo "  ✅ Shared"

# Config
echo "📁 Creating config directories..."
mkdir -p config/agents
mkdir -p config/skills
echo "  ✅ Config"

# Data (with .gitkeep)
echo "📁 Creating data directories..."
mkdir -p data/logs
mkdir -p data/coder_output/skills
mkdir -p data/postgres
mkdir -p data/redis
mkdir -p data/rabbitmq
mkdir -p data/qdrant
touch data/logs/.gitkeep
touch data/coder_output/.gitkeep
touch data/postgres/.gitkeep
touch data/redis/.gitkeep
touch data/rabbitmq/.gitkeep
touch data/qdrant/.gitkeep
echo "  ✅ Data"

# Scripts
echo "📁 Creating scripts directory..."
mkdir -p scripts
chmod +x scripts/*.py 2>/dev/null || true
chmod +x scripts/*.sh 2>/dev/null || true
echo "  ✅ Scripts"

# Tests
echo "📁 Creating tests directory..."
mkdir -p tests/unit/test_skills
mkdir -p tests/integration
mkdir -p tests/e2e
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/integration/__init__.py
touch tests/e2e/__init__.py
echo "  ✅ Tests"

# Docs (already should exist)
echo "📁 Checking docs directory..."
mkdir -p docs
echo "  ✅ Docs"

# Backups
echo "📁 Creating backups directory..."
mkdir -p backups
touch backups/.gitkeep
echo "  ✅ Backups"

echo ""
echo "✅ Project structure created!"
echo ""
echo "Directory tree:"
tree -L 2 -d --charset ascii || ls -R

echo ""
echo "Next steps:"
echo "  1. Copy .env.example to .env and fill in values"
echo "  2. Run: make validate"
echo "  3. Run: make setup"
