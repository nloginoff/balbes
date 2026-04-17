#!/usr/bin/env python3
"""
MAX platform-api: list / delete / apply webhook subscriptions.

Docs:
  GET/POST/DELETE https://dev.max.ru/docs-api/methods/GET/subscriptions
  Authorization: raw access token (no \"Bearer\" prefix).

Examples:
  ENV=prod python scripts/max_subscriptions.py list
  python scripts/max_subscriptions.py list --env-file /path/to/.env.prod
  python scripts/max_subscriptions.py delete --url https://example.com/webhook/max
  python scripts/max_subscriptions.py apply --url https://example.com/webhook/max --delete-first
"""

from __future__ import annotations

import argparse
import json
import os
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


def _normalize_access_token(token: str) -> str:
    t = (token or "").strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return t


def _request(
    method: str,
    base_url: str,
    path: str,
    *,
    token: str,
    query: dict[str, str] | None = None,
    body: dict | None = None,
    timeout: float = 60.0,
) -> tuple[int, dict | list | str]:
    base = base_url.rstrip("/")
    url = f"{base}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    data: bytes | None = None
    headers = {
        "Authorization": _normalize_access_token(token),
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        code = e.code
    try:
        parsed: dict | list = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return code, raw
    return code, parsed


def _find_subscription_urls(payload: dict | list | str) -> list[str]:
    if not isinstance(payload, dict):
        return []
    subs = payload.get("subscriptions")
    if not isinstance(subs, list):
        return []
    urls: list[str] = []
    for item in subs:
        if isinstance(item, dict) and item.get("url"):
            urls.append(str(item["url"]))
    return urls


def cmd_list(args: argparse.Namespace, token: str, api_url: str) -> int:
    code, payload = _request("GET", api_url, "/subscriptions", token=token)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if code != 200:
        print(f"HTTP {code}", file=sys.stderr)
        return 1
    return 0


def cmd_delete(args: argparse.Namespace, token: str, api_url: str) -> int:
    code, payload = _request(
        "DELETE",
        api_url,
        "/subscriptions",
        token=token,
        query={"url": args.url},
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if code != 200:
        print(f"HTTP {code}", file=sys.stderr)
        return 1
    return 0


def cmd_apply(args: argparse.Namespace, token: str, api_url: str) -> int:
    secret = args.secret
    if args.secret_from_env:
        env = _parse_env_file(Path(args.env_file))
        secret = env.get("MAX_WEBHOOK_SECRET", "").strip()
    if not secret:
        print(
            "Missing secret: pass --secret or --secret-from-env with MAX_WEBHOOK_SECRET in env file",
            file=sys.stderr,
        )
        return 1

    update_types = [x.strip() for x in args.update_types.split(",") if x.strip()]

    if args.delete_first:
        print("DELETE old subscription (same url)...", file=sys.stderr)
        dcode, dpayload = _request(
            "DELETE",
            api_url,
            "/subscriptions",
            token=token,
            query={"url": args.url},
        )
        print(json.dumps(dpayload, ensure_ascii=False, indent=2))
        if dcode not in (200, 404):
            print(f"DELETE HTTP {dcode} (continuing if subscription was missing)", file=sys.stderr)

    body = {
        "url": args.url,
        "update_types": update_types,
        "secret": secret,
    }
    print("POST /subscriptions ...", file=sys.stderr)
    pcode, ppayload = _request("POST", api_url, "/subscriptions", token=token, body=body)
    print(json.dumps(ppayload, ensure_ascii=False, indent=2))
    if pcode != 200:
        print(f"POST HTTP {pcode}", file=sys.stderr)
        return 1
    if isinstance(ppayload, dict) and ppayload.get("success") is False:
        print("POST reported success=false", file=sys.stderr)
        return 1

    print("GET /subscriptions (verify)...", file=sys.stderr)
    gcode, gpayload = _request("GET", api_url, "/subscriptions", token=token)
    if gcode != 200:
        print(json.dumps(gpayload, ensure_ascii=False, indent=2))
        print(f"Verify GET HTTP {gcode}", file=sys.stderr)
        return 1

    urls = _find_subscription_urls(gpayload)
    if args.url not in urls:
        print("VERIFY FAILED: webhook URL not found in subscriptions list:", file=sys.stderr)
        print("URLs:", urls, file=sys.stderr)
        print(json.dumps(gpayload, ensure_ascii=False, indent=2))
        return 1
    print(f"VERIFY OK: {args.url!r} is in subscriptions ({len(urls)} total).", file=sys.stderr)
    return 0


def main() -> int:
    root = _project_root()
    default_env = root / f".env.{os.getenv('ENV', 'prod')}"
    parser = argparse.ArgumentParser(description="MAX /subscriptions helper")
    parser.add_argument(
        "--env-file",
        default=str(default_env),
        help=f"Env file (default: {default_env})",
    )
    parser.add_argument(
        "--api-url",
        default="",
        help="Override MAX_API_URL (default from env file or https://platform-api.max.ru)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="GET /subscriptions")
    p_list.set_defaults(func=cmd_list)

    p_del = sub.add_parser("delete", help="DELETE /subscriptions?url=...")
    p_del.add_argument("--url", required=True, help="Webhook URL to remove")
    p_del.set_defaults(func=cmd_delete)

    p_apply = sub.add_parser("apply", help="POST /subscriptions and verify via GET")
    p_apply.add_argument("--url", required=True, help="Public https://.../webhook/max")
    p_apply.add_argument("--secret", default="", help="Webhook secret (or use --secret-from-env)")
    p_apply.add_argument(
        "--secret-from-env",
        action="store_true",
        help="Read MAX_WEBHOOK_SECRET from --env-file",
    )
    p_apply.add_argument(
        "--update-types",
        default="message_created,bot_started",
        help="Comma-separated update types",
    )
    p_apply.add_argument(
        "--delete-first",
        action="store_true",
        help="DELETE subscription for this URL before POST (use when changing secret or fixing stale subscription)",
    )
    p_apply.set_defaults(func=cmd_apply)

    args = parser.parse_args()
    env_path = Path(args.env_file)
    env = _parse_env_file(env_path)
    token = env.get("MAX_BOT_TOKEN", "").strip()
    if not token:
        print("MAX_BOT_TOKEN missing in env file", file=sys.stderr)
        return 1
    api_url = (
        args.api_url or env.get("MAX_API_URL") or ""
    ).strip() or "https://platform-api.max.ru"

    return int(args.func(args, token, api_url))


if __name__ == "__main__":
    raise SystemExit(main())
