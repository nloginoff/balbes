#!/usr/bin/env bash
# =============================================================================
# backup_memory.sh — Manually commit and push all agent workspace changes.
#
# Use this when you want to immediately save the current state of all
# agent workspace files to the private memory repo.
#
# Usage:
#   bash scripts/backup_memory.sh [commit-message]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
AGENTS_DIR="$PROJECT_ROOT/data/agents"

MSG="${1:-backup: manual save $(date -u '+%Y-%m-%d %H:%M UTC')}"

if [[ ! -d "$AGENTS_DIR/.git" ]]; then
    echo "❌  data/agents/ is not a git repository."
    echo "    Run: bash scripts/setup_memory_repo.sh <repo-url>"
    exit 1
fi

cd "$AGENTS_DIR"

git add -A

if git diff --cached --quiet 2>/dev/null; then
    echo "✅  Nothing to commit — workspace is clean."
    exit 0
fi

git commit -m "$MSG"
git push origin HEAD

echo "✅  Backup pushed: $MSG"
