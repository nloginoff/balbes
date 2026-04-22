#!/usr/bin/env bash
# Экспорт всех чатов Memory в data_for_agent/ у корня репозитория (см. export_memory_chats_to_data_for_agent.py).
# Нужен пакет redis (async) — не системный python3 без venv.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
PY="$ROOT/.venv/bin/python"
if [[ -x "$PY" ]]; then
  exec "$PY" "$DIR/export_memory_chats_to_data_for_agent.py" "$@"
fi
if command -v uv >/dev/null 2>&1 && [[ -f "$ROOT/pyproject.toml" ]]; then
  cd "$ROOT" || exit 1
  exec uv run python "$DIR/export_memory_chats_to_data_for_agent.py" "$@"
fi
echo "ERROR: no usable Python env. From repo root: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
echo "Then: ./scripts/export_chats_for_agent.sh   or: .venv/bin/python scripts/export_memory_chats_to_data_for_agent.py" >&2
exit 1
