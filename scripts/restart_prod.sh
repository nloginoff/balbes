#!/bin/bash

# Restart Balbes PRODUCTION environment
# Usage: ./scripts/restart_prod.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔄 Restarting Balbes - PRODUCTION MODE"
echo "========================================"
echo ""

echo "1) Stopping production services..."
./scripts/stop_prod.sh

echo ""
echo "2) Starting production services..."
ENV=prod ./scripts/start_prod.sh

echo ""
echo "3) Post-restart health check..."
./scripts/healthcheck.sh prod || true

echo ""
echo "========================================"
echo "✅ Production restart completed"
echo "========================================"
