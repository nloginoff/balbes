"""
Seed base skills into Skills Registry.

Usage examples:
    python scripts/seed_skills.py
    ENV=prod python scripts/seed_skills.py --base-url http://localhost:18101/api/v1/skills
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class SeedResult:
    created: int = 0
    skipped: int = 0
    failed: int = 0


BASE_SKILLS: list[dict[str, Any]] = [
    {
        "name": "general_chat_response",
        "description": "Answer general user messages politely in Russian and English.",
        "version": "1.0.0",
        "category": "conversation",
        "implementation_url": "https://example.com/skills/general_chat_response",
        "tags": ["chat", "greeting", "conversation", "assistant"],
        "input_schema": {"parameters": {"text": {"type": "string"}}, "required": ["text"]},
        "output_schema": {"format": "text", "description": "Assistant response text"},
        "estimated_tokens": 600,
        "authors": ["balbes"],
        "dependencies": [],
    },
    {
        "name": "task_clarification",
        "description": "Ask clarifying questions when task description is ambiguous.",
        "version": "1.0.0",
        "category": "conversation",
        "implementation_url": "https://example.com/skills/task_clarification",
        "tags": ["clarification", "assistant", "dialog"],
        "input_schema": {"parameters": {"task": {"type": "string"}}, "required": ["task"]},
        "output_schema": {"format": "text", "description": "Clarifying question"},
        "estimated_tokens": 500,
        "authors": ["balbes"],
        "dependencies": [],
    },
]


def _default_base_url() -> str:
    env = os.getenv("ENV", "dev").lower()
    if env == "prod":
        return "http://localhost:18101/api/v1/skills"
    if env == "test":
        return "http://localhost:9101/api/v1/skills"
    return "http://localhost:8101/api/v1/skills"


async def seed_skills(base_url: str, timeout: float = 60.0) -> SeedResult:
    result = SeedResult()

    async with httpx.AsyncClient(timeout=timeout) as client:
        for skill in BASE_SKILLS:
            response = await client.post(base_url, json=skill)
            if response.status_code in (200, 201):
                print(f"OK    {skill['name']}")
                result = SeedResult(result.created + 1, result.skipped, result.failed)
                continue

            if response.status_code == 400 and "already exists" in response.text.lower():
                print(f"SKIP  {skill['name']} (already exists)")
                result = SeedResult(result.created, result.skipped + 1, result.failed)
                continue

            print(f"FAIL  {skill['name']} -> {response.status_code}: {response.text}")
            result = SeedResult(result.created, result.skipped, result.failed + 1)

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed base skills to Skills Registry.")
    parser.add_argument(
        "--base-url",
        default=_default_base_url(),
        help="Skills Registry create endpoint (default depends on ENV).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds.",
    )
    return parser.parse_args()


async def _main() -> int:
    args = parse_args()
    summary = await seed_skills(base_url=args.base_url, timeout=args.timeout)
    print(f"\nDone. created={summary.created}, skipped={summary.skipped}, failed={summary.failed}")
    return 0 if summary.failed == 0 else 1


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
