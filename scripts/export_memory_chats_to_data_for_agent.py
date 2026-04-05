#!/usr/bin/env python3
"""
Сохранить все чаты Memory Service (Redis) в каталог на диске.

Обходит ключи ``chats:*``, для каждого ``user_id`` (namespace памяти) читает
список чатов, ``chat_meta:*``, полную историю из sorted set ``history:*``.

Структура (по умолчанию ``--output /data_for_agent``)::

    {agent_id}__{chat_id}/
        meta.json      — memory_user_id, chat_id, хеш meta из Redis, имя из chats
        history.json   — все сообщения по времени (ZRANGE 0 -1)
        active.flag    — есть только если этот чат был активным у пользователя

При коллизии имён каталога (редко) используется
``{memory_user_id}__{agent_id}__{chat_id}``.

Запуск (каталог по умолчанию уже ``/data_for_agent``, ``PYTHONPATH`` не нужен)::

    python3 scripts/export_memory_chats_to_data_for_agent.py

или обёртка::

    ./scripts/export_chats_for_agent.sh

Переменные окружения: как у сервисов — ``REDIS_*`` (см. ``shared.config``). Или ``--redis-url``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any


def _ensure_project_root_on_path() -> None:
    """Добавляет корень репозитория в sys.path — скрипт можно вызывать без PYTHONPATH=."""
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


import redis.asyncio as aioredis

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger("export_memory_chats")


def _safe_segment(s: str, max_len: int = 120) -> str:
    t = re.sub(r"[^\w.\-]+", "_", s, flags=re.UNICODE).strip("_")
    if not t:
        t = "unknown"
    return t[:max_len]


def _parse_messages(raw: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw:
        try:
            out.append(json.loads(item))
        except json.JSONDecodeError:
            out.append({"_raw": item, "_error": "invalid_json"})
    return out


def _resolve_output_dir(
    base: Path,
    memory_user_id: str,
    agent_id: str,
    chat_id: str,
) -> Path:
    a = _safe_segment(agent_id or "balbes")
    primary = base / f"{a}__{chat_id}"
    if not primary.exists():
        return primary
    # Уже есть каталог с тем же agent+chat — добавляем namespace
    fallback = base / f"{_safe_segment(memory_user_id)}__{a}__{chat_id}"
    if not fallback.exists():
        return fallback
    n = 2
    while True:
        cand = base / f"{_safe_segment(memory_user_id)}__{a}__{chat_id}__{n}"
        if not cand.exists():
            return cand
        n += 1


async def _scan_memory_user_ids(client: aioredis.Redis) -> list[str]:
    cursor = 0
    seen: set[str] = set()
    while True:
        cursor, keys = await client.scan(cursor=cursor, match="chats:*", count=500)
        for k in keys:
            if isinstance(k, bytes):
                k = k.decode("utf-8", errors="replace")
            if k.startswith("chats:"):
                seen.add(k[len("chats:") :])
        if cursor == 0:
            break
    return sorted(seen)


async def export_all(
    redis_url: str,
    output: Path,
    dry_run: bool,
) -> tuple[int, int]:
    client = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    try:
        await client.ping()
        user_ids = await _scan_memory_user_ids(client)
        logger.info("Найдено namespace (memory user_id): %d", len(user_ids))

        exported = 0
        skipped = 0
        for memory_user_id in user_ids:
            chats_key = f"chats:{memory_user_id}"
            chat_map = await client.hgetall(chats_key)
            if not chat_map:
                continue

            active_chat = await client.get(f"active_chat:{memory_user_id}")

            for chat_id, name_from_hash in chat_map.items():
                meta_key = f"chat_meta:{memory_user_id}:{chat_id}"
                history_key = f"history:{memory_user_id}:{chat_id}"
                meta = await client.hgetall(meta_key)
                raw_hist = await client.zrange(history_key, 0, -1)

                if not meta and not raw_hist:
                    skipped += 1
                    logger.debug(
                        "Пропуск пустого чата (нет meta и истории): %s / %s",
                        memory_user_id,
                        chat_id,
                    )
                    continue

                agent_id = (meta.get("agent_id") if meta else None) or "balbes"
                messages = _parse_messages(raw_hist)

                payload_meta = {
                    "memory_user_id": memory_user_id,
                    "chat_id": chat_id,
                    "name_from_chats_hash": name_from_hash,
                    "chat_meta": meta,
                    "active": active_chat == chat_id,
                }

                out_dir = _resolve_output_dir(output, memory_user_id, agent_id, chat_id)
                if dry_run:
                    logger.info("[dry-run] %s", out_dir)
                    exported += 1
                    continue

                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "meta.json").write_text(
                    json.dumps(payload_meta, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                (out_dir / "history.json").write_text(
                    json.dumps(
                        {"messages": messages, "total": len(messages)},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                if active_chat == chat_id:
                    (out_dir / "active.flag").write_text("active\n", encoding="utf-8")

                exported += 1
                logger.info("OK %s", out_dir.name)

        return exported, skipped
    finally:
        await client.aclose()


def main() -> int:
    _ensure_project_root_on_path()
    parser = argparse.ArgumentParser(
        description="Экспорт всех чатов Memory из Redis в каталог (агент + chat_id)."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/data_for_agent"),
        help="Базовый каталог (по умолчанию /data_for_agent)",
    )
    parser.add_argument(
        "--redis-url",
        type=str,
        default=None,
        help="URL Redis; если не задан — из shared.config (REDIS_*)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только список каталогов, без записи файлов",
    )
    args = parser.parse_args()

    if args.redis_url:
        redis_url = args.redis_url
    else:
        try:
            from shared.config import get_settings

            redis_url = get_settings().redis_url
        except Exception as e:
            logger.error("Нужен --redis-url или корректный shared.config: %s", e)
            return 1

    args.output.mkdir(parents=True, exist_ok=True)

    try:
        exported, skipped = asyncio.run(export_all(redis_url, args.output, args.dry_run))
    except Exception as e:
        logger.error("Ошибка экспорта: %s", e)
        return 1

    logger.info("Готово: экспортировано %d, пропущено пустых %d", exported, skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
