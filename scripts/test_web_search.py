#!/usr/bin/env python3
"""
Quick CLI test for all configured web search providers.

Usage:
    cd /home/balbes/projects/dev
    source .venv/bin/activate
    ENV=prod python scripts/test_web_search.py
    ENV=prod python scripts/test_web_search.py --query "Python asyncio" --provider yandex
    ENV=prod python scripts/test_web_search.py --provider all
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Project root on sys.path so shared imports work
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "shared"))
sys.path.insert(0, str(PROJECT_ROOT / "services" / "orchestrator"))

# Load .env.prod if ENV=prod
env = os.environ.get("ENV", "dev")
env_file = PROJECT_ROOT / f".env.{env}"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())
    print(f"✅ Loaded {env_file.name}\n")
else:
    print(f"⚠️  {env_file} not found, using existing env vars\n")


async def test_provider(provider: str, query: str, max_results: int = 3) -> None:
    from skills.web_search import WebSearchSkill

    skill = WebSearchSkill()
    print(f"{'─' * 60}")
    print(f"🔍 Provider: {provider.upper()}")
    print(f"   Query:    {query}")
    print(f"{'─' * 60}")
    try:
        results, used = await skill.search(
            query=query,
            max_results=max_results,
            provider_override=provider,
        )
        if not results:
            print(f"   ⚠️  No results returned (provider={used})")
        else:
            print(f"   ✅ {len(results)} result(s) [provider={used}]")
            for i, r in enumerate(results, 1):
                print(f"\n   {i}. {r.title}")
                print(f"      {r.url}")
                if r.snippet:
                    print(f"      {r.snippet[:150]}")
    except Exception as e:
        print(f"   ❌ Error: {type(e).__name__}: {e}")
    finally:
        await skill.close()
    print()


async def check_keys() -> dict[str, bool]:
    from shared.config import get_settings

    s = get_settings()
    keys = {
        "tavily": bool(s.tavily_api_key),
        "yandex": bool(s.yandex_search_key and s.yandex_search_user),
        "brave": bool(s.brave_search_key),
    }
    print("📋 API keys status:")
    for p, ok in keys.items():
        icon = "✅" if ok else "❌"
        print(f"   {icon} {p}")
    print()
    return keys


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test web search providers")
    parser.add_argument("--query", default="Бойцовский клуб игра", help="Search query")
    parser.add_argument(
        "--provider",
        default="all",
        choices=["all", "tavily", "yandex", "brave"],
        help="Provider to test (default: all configured)",
    )
    parser.add_argument("--max", type=int, default=3, help="Max results per provider")
    args = parser.parse_args()

    keys = await check_keys()

    if args.provider == "all":
        for provider, has_key in keys.items():
            if has_key:
                await test_provider(provider, args.query, args.max)
            else:
                print(f"⏭️  Skipping {provider} — API key not set\n")
    else:
        await test_provider(args.provider, args.query, args.max)


if __name__ == "__main__":
    asyncio.run(main())
