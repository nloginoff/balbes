#!/usr/bin/env python3
"""
Сохранить все чаты Memory Service (Redis) в каталог на диске.

Обходит ключи ``chats:*``, для каждого ``user_id`` (namespace памяти) читает
список чатов, ``chat_meta:*``, полную историю из sorted set ``history:*``.

Структура (каталог задаётся ``--output``, см. ниже)::

    {agent_id}__{chat_id}/
        meta.json      — memory_user_id, chat_id, хеш meta из Redis, имя из chats
        history.json   — все сообщения по времени (ZRANGE 0 -1)
        active.flag    — есть только если этот чат был активным у пользователя

При коллизии имён каталога (редко) используется
``{memory_user_id}__{agent_id}__{chat_id}``.

Запуск::

    python3 scripts/export_memory_chats_to_data_for_agent.py

или ``./scripts/export_chats_for_agent.sh``

Куда писать по умолчанию: ``<корень_деплоя>/data_for_agent/`` (корень репозитория на проде, не корень ФС).
Явно: ``--output путь`` или ``EXPORT_CHATS_OUTPUT``.

Redis: ``REDIS_*`` / ``REDIS_URL``. Файлы окружения: сначала ``.env``, иначе ``.env.prod``; затем ``.env.{ENV}``
(если ``ENV=prod``, подтянется ``.env.prod`` поверх). Явно: ``--env-file /path/.env.prod`` или ``--redis-url``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger("export_memory_chats")


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _early_env_file_from_argv() -> Path | None:
    """Парсит --env-file до основного argparse, чтобы подмешать Redis до чтения флагов."""
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--env-file" and i + 1 < len(argv):
            return Path(argv[i + 1])
        if a.startswith("--env-file="):
            return Path(a.split("=", 1)[1])
    return None


def _load_project_env_file(explicit: Path | None = None) -> None:
    """Загружает .env из корня деплоя (без shared.config)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = _project_root()
    if explicit is not None:
        if explicit.is_file():
            load_dotenv(explicit, override=True)
            logger.info("Переменные из %s", explicit)
        else:
            logger.warning("Файл не найден: %s", explicit)
        return
    if (root / ".env").is_file():
        load_dotenv(root / ".env", override=False)
    elif (root / ".env.prod").is_file():
        load_dotenv(root / ".env.prod", override=False)
        logger.info("Загружен %s (файла .env нет)", root / ".env.prod")
    env = os.environ.get("ENV", "dev")
    specific = root / f".env.{env}"
    if specific.is_file():
        load_dotenv(specific, override=True)


def _redis_url_for_log(url: str) -> str:
    """Убирает пароль из URL для лога."""
    if "@" in url and "://" in url:
        return re.sub(r":([^/@]+)@", r":***@", url, count=1)
    return url


def _redis_url_from_env() -> str:
    """Собирает URL из окружения; не требует полной конфигурации приложения."""
    u = (os.environ.get("REDIS_URL") or "").strip()
    if u:
        return u
    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    password = (os.environ.get("REDIS_PASSWORD") or "").strip()
    db = int(os.environ.get("REDIS_DB", "0"))
    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


def _choose_base_output_dir(cli_output: Path | None) -> Path:
    """По умолчанию ``<корень репозитория>/data_for_agent`` (корень prod-деплоя, не ``/`` на диске)."""
    if cli_output is not None:
        return cli_output
    env = (
        os.environ.get("EXPORT_CHATS_OUTPUT") or os.environ.get("BALBES_EXPORT_CHATS_DIR") or ""
    ).strip()
    if env:
        return Path(env)
    return _project_root() / "data_for_agent"


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
    _load_project_env_file(_early_env_file_from_argv())
    parser = argparse.ArgumentParser(
        description="Экспорт всех чатов Memory из Redis в каталог (агент + chat_id)."
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Явный путь к .env (обрабатывается первым; иначе .env / .env.prod / .env.{ENV})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Базовый каталог (по умолчанию: data_for_agent в корне репозитория / деплоя)",
    )
    parser.add_argument(
        "--redis-url",
        type=str,
        default=None,
        help="URL Redis; иначе REDIS_URL или REDIS_HOST/REDIS_PORT/REDIS_PASSWORD/REDIS_DB",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только список каталогов, без записи файлов",
    )
    args = parser.parse_args()

    redis_url = (args.redis_url or "").strip() or _redis_url_from_env()

    output = _choose_base_output_dir(args.output)
    output.mkdir(parents=True, exist_ok=True)
    logger.info("Каталог экспорта: %s", output.resolve())
    logger.info("Redis: %s", _redis_url_for_log(redis_url))

    try:
        exported, skipped = asyncio.run(export_all(redis_url, output, args.dry_run))
    except Exception as e:
        err = str(e)
        if "Connect call failed" in err or "Connection refused" in err or "111" in err:
            logger.error(
                "Redis недоступен по %s. Укажите хост/порт Redis (с хоста к контейнеру — проброшенный порт). "
                "Пример: ENV=prod ./export_chats_for_agent.sh или --env-file ../.env.prod или --redis-url redis://...",
                _redis_url_for_log(redis_url),
            )
        else:
            logger.error("Ошибка экспорта: %s", e)
        return 1

    logger.info("Готово: экспортировано %d, пропущено пустых %d", exported, skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
