#!/usr/bin/env bash
# Экспорт всех чатов Memory в /data_for_agent (см. export_memory_chats_to_data_for_agent.py).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/export_memory_chats_to_data_for_agent.py" "$@"
