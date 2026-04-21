#!/usr/bin/env python3
"""
Отправить тестовое сообщение через MAX platform-api — проверка, что MAX_BOT_TOKEN живой.

Использует POST /messages с ``user_id`` (личка) или ``chat_id`` (чат/группа), как в
https://dev.max.ru/docs-api/methods/POST/messages

Примеры::

  cd /path/to/balbes   # каталог с .env.prod
  python scripts/max_send_test.py --env-file .env.prod --user-id 123456789

  # Если в .env уже задан NOTIFY_MAX_USER_ID или NOTIFY_MAX_CHAT_ID:
  python scripts/max_send_test.py --env-file .env.prod
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _normalize_token(token: str) -> str:
    t = (token or "").strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return t


def main() -> int:
    ap = argparse.ArgumentParser(description="MAX: send one test message (token check)")
    ap.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Файл с MAX_BOT_TOKEN (по умолчанию: .env.prod рядом с корнем проекта)",
    )
    ap.add_argument("--api-url", default=None, help="Переопределить MAX_API_URL")
    ap.add_argument("--token", default=None, help="Переопределить токен (иначе из env)")
    ap.add_argument("--user-id", type=int, default=None, help="Получатель: user_id (личка)")
    ap.add_argument("--chat-id", type=int, default=None, help="Получатель: chat_id (чат)")
    ap.add_argument(
        "--text",
        default="✅ MAX token test: сообщение дошло. Скрипт max_send_test.py",
        help="Текст сообщения",
    )
    args = ap.parse_args()

    env_path = args.env_file
    if env_path is None:
        cand = _project_root() / ".env.prod"
        env_path = cand if cand.is_file() else _project_root() / ".env"

    env = _parse_env_file(env_path) if env_path.is_file() else {}

    token = _normalize_token(args.token or env.get("MAX_BOT_TOKEN", ""))
    if not token:
        print("ERROR: задайте MAX_BOT_TOKEN в env или --token", file=sys.stderr)
        return 1

    base = (args.api_url or env.get("MAX_API_URL") or "https://platform-api.max.ru").rstrip("/")

    uid = args.user_id
    if uid is None and env.get("NOTIFY_MAX_USER_ID", "").strip():
        try:
            uid = int(env["NOTIFY_MAX_USER_ID"].strip())
        except ValueError:
            pass

    cid = args.chat_id
    if cid is None and env.get("NOTIFY_MAX_CHAT_ID", "").strip():
        cid_raw = env["NOTIFY_MAX_CHAT_ID"].strip()
        try:
            cid = int(cid_raw)
        except ValueError:
            pass

    if (uid is not None) == (cid is not None):
        print(
            "ERROR: укажите ровно один из --user-id или --chat-id "
            "(или задайте в env только NOTIFY_MAX_USER_ID или только NOTIFY_MAX_CHAT_ID)",
            file=sys.stderr,
        )
        return 1

    query: dict[str, str] = {}
    if uid is not None:
        query["user_id"] = str(uid)
    else:
        query["chat_id"] = str(cid)

    url = f"{base}/messages?{urllib.parse.urlencode(query)}"
    body = json.dumps({"text": args.text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": token,
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=30.0, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            print(f"HTTP {resp.status}")
            print(raw[:2000])
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}", file=sys.stderr)
        print(err[:2000], file=sys.stderr)
        return 1
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
