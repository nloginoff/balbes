#!/usr/bin/env bash
# =============================================================================
# setup_memory_repo.sh — One-time setup for the private agent memory repo.
#
# This links data/agents/ to a private GitHub repository so that all agent
# workspace files (MEMORY.md, HEARTBEAT.md, etc.) are versioned privately,
# separate from the main project repository.
#
# Usage:
#   bash scripts/setup_memory_repo.sh <git-repo-ssh-url>
#
# Example:
#   bash scripts/setup_memory_repo.sh git@github.com:nloginoff/balbes-memory.git
#
# Run this script:
#   - On the DEV server  — first time, initializes and pushes existing files
#   - On the PROD server — after running on dev, clones the existing repo
# =============================================================================

set -euo pipefail

REPO_URL="${1:-}"

if [[ -z "$REPO_URL" ]]; then
    echo "❌  Usage: $0 <git-repo-ssh-url>"
    echo "    Example: $0 git@github.com:nloginoff/balbes-memory.git"
    echo ""
    echo "    1. Go to https://github.com/new"
    echo "    2. Name it: balbes-memory"
    echo "    3. Select: Private"
    echo "    4. Don't add README / .gitignore"
    echo "    5. Copy the SSH URL and pass it here"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
AGENTS_DIR="$PROJECT_ROOT/data/agents"

# Inherit git identity from the main project
GIT_NAME="$(git -C "$PROJECT_ROOT" config user.name 2>/dev/null || echo 'Balbes Agent')"
GIT_EMAIL="$(git -C "$PROJECT_ROOT" config user.email 2>/dev/null || echo 'agent@localhost')"

mkdir -p "$AGENTS_DIR"
cd "$AGENTS_DIR"

echo ""
echo "📂  Target directory: $AGENTS_DIR"
echo "🔗  Remote:           $REPO_URL"
echo ""

# ---------------------------------------------------------------------------
# Case 1: Already a git repo — just update remote and sync
# ---------------------------------------------------------------------------
if [[ -d ".git" ]]; then
    echo "✅  Git repo already exists in data/agents/"

    CURRENT_REMOTE="$(git remote get-url origin 2>/dev/null || echo '')"
    if [[ "$CURRENT_REMOTE" != "$REPO_URL" ]]; then
        if git remote | grep -q "^origin$"; then
            git remote set-url origin "$REPO_URL"
        else
            git remote add origin "$REPO_URL"
        fi
        echo "🔄  Remote updated to: $REPO_URL"
    fi

    git add -A
    if ! git diff --cached --quiet 2>/dev/null; then
        git commit -m "sync: manual backup $(date -u '+%Y-%m-%d %H:%M UTC')"
    fi

    git push origin HEAD
    echo "✅  Synced to remote."
    echo ""
    exit 0
fi

# ---------------------------------------------------------------------------
# Case 2: Remote repo already exists (e.g. setting up PROD) — clone it
# ---------------------------------------------------------------------------
if git ls-remote "$REPO_URL" HEAD &>/dev/null; then
    echo "🌐  Remote repo exists. Importing into data/agents/..."

    TMPDIR_CLONE="$(mktemp -d)"
    git clone --depth=1 "$REPO_URL" "$TMPDIR_CLONE/clone"

    # Move the .git folder into data/agents/ and restore working tree
    mv "$TMPDIR_CLONE/clone/.git" .git
    rm -rf "$TMPDIR_CLONE"

    git reset --hard HEAD
    echo "✅  Cloned existing memory repo into data/agents/"
    echo ""

    # Check if we have local files not yet in the repo and commit them
    git add -A
    if ! git diff --cached --quiet 2>/dev/null; then
        git commit -m "sync: merge local files from this host"
        git push origin HEAD
    fi
    exit 0
fi

# ---------------------------------------------------------------------------
# Case 3: Fresh init — new empty remote repo
# ---------------------------------------------------------------------------
echo "🔧  Initializing fresh memory repo in data/agents/ ..."
git init -b master
git remote add origin "$REPO_URL"

git config user.name  "$GIT_NAME"
git config user.email "$GIT_EMAIL"

# Create a root .gitignore so only .md files are tracked
cat > .gitignore <<'GITIGNORE'
# Track only workspace markdown files
*
!*.md
!.gitignore
GITIGNORE

git add -A

if ! git diff --cached --quiet 2>/dev/null; then
    git commit -m "init: import existing agent workspace files"
    echo "✅  Initial commit created"
else
    # Nothing to commit yet — make an empty initial commit so push works
    git commit --allow-empty -m "init: create memory repo"
fi

echo "🚀  Pushing to $REPO_URL ..."
git push -u origin master

echo ""
echo "========================================================"
echo "✅  Memory repo setup complete!"
echo "========================================================"
echo ""
echo "Next step — remove data/agents/ from the MAIN repo tracking:"
echo ""
echo "  cd $PROJECT_ROOT"
echo "  git rm -r --cached data/agents/"
echo "  git add .gitignore"
echo "  git commit -m 'chore: move agent workspace to private memory repo'"
echo "  git push"
echo ""
echo "After that, the agent will auto-commit & push every time it"
echo "writes a workspace file (MEMORY.md, HEARTBEAT.md, etc.)."
echo ""
