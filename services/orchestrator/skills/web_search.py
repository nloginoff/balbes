"""
Web search skill.

Supports multiple providers with fallback:
  - duckduckgo (free, no API key required)
  - brave     (requires BRAVE_SEARCH_KEY)
  - tavily    (requires TAVILY_API_KEY)

Active provider is read from providers.yaml -> skills.web_search.default_provider.
"""

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from shared.config import get_settings

logger = logging.getLogger("orchestrator.skills.web_search")
settings = get_settings()


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchSkill:
    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._http = http_client
        self._own_client = http_client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=15.0)
        return self._http

    async def close(self) -> None:
        if self._own_client and self._http:
            await self._http.aclose()

    def _load_config(self) -> dict[str, Any]:
        """Load skills config from providers.yaml."""
        try:
            from pathlib import Path

            import yaml

            cfg_path = Path(__file__).parent.parent.parent.parent / "config" / "providers.yaml"
            if cfg_path.exists():
                with open(cfg_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                return data.get("skills", {}).get("web_search", {})
        except Exception as e:
            logger.warning(f"Failed to load providers.yaml: {e}")
        return {}

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        cfg = self._load_config()
        default = cfg.get("default_provider", "duckduckgo")
        providers_cfg = cfg.get("providers", {})

        order = [default] + [p for p in ["duckduckgo", "brave", "tavily"] if p != default]

        for provider in order:
            p_cfg = providers_cfg.get(provider, {})
            if not p_cfg.get("enabled", provider == "duckduckgo"):
                continue
            try:
                if provider == "duckduckgo":
                    return await self._search_duckduckgo(query, max_results)
                if provider == "brave":
                    key = settings.brave_search_key
                    if key:
                        return await self._search_brave(query, max_results, key)
                if provider == "tavily":
                    key = settings.tavily_api_key
                    if key:
                        return await self._search_tavily(query, max_results, key)
            except Exception as e:
                logger.warning(f"Search provider {provider} failed: {e}, trying next")
                continue

        logger.error("All search providers failed")
        return []

    async def _search_duckduckgo(self, query: str, max_results: int) -> list[SearchResult]:
        """Search using DuckDuckGo HTML (no API key required)."""
        client = await self._get_client()
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        headers = {"User-Agent": "Balbes-Agent/1.0"}

        response = await client.get(
            "https://api.duckduckgo.com/",
            params=params,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        results: list[SearchResult] = []

        # Abstract (instant answer)
        if data.get("AbstractText") and data.get("AbstractURL"):
            results.append(
                SearchResult(
                    title=data.get("Heading", "DuckDuckGo Instant Answer"),
                    url=data["AbstractURL"],
                    snippet=data["AbstractText"][:300],
                )
            )

        # Related topics
        for topic in data.get("RelatedTopics", []):
            if len(results) >= max_results:
                break
            if "Text" in topic and "FirstURL" in topic:
                results.append(
                    SearchResult(
                        title=topic.get("Text", "")[:80],
                        url=topic["FirstURL"],
                        snippet=topic.get("Text", "")[:300],
                    )
                )

        if not results:
            # Fallback: use DuckDuckGo Lite HTML scrape
            results = await self._search_duckduckgo_lite(query, max_results, client)

        return results[:max_results]

    async def _search_duckduckgo_lite(
        self,
        query: str,
        max_results: int,
        client: httpx.AsyncClient,
    ) -> list[SearchResult]:
        """Fallback: scrape DuckDuckGo HTML results."""
        try:
            from duckduckgo_search import DDGS

            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(
                        SearchResult(
                            title=r.get("title", ""),
                            url=r.get("href", ""),
                            snippet=r.get("body", "")[:300],
                        )
                    )
            return results
        except ImportError:
            logger.warning("duckduckgo_search package not installed, using empty results")
            return []
        except Exception as e:
            logger.warning(f"DuckDuckGo DDGS search failed: {e}")
            return []

    async def _search_brave(self, query: str, max_results: int, api_key: str) -> list[SearchResult]:
        client = await self._get_client()
        response = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("web", {}).get("results", [])[:max_results]:
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("description", "")[:300],
                )
            )
        return results

    async def _search_tavily(
        self, query: str, max_results: int, api_key: str
    ) -> list[SearchResult]:
        client = await self._get_client()
        response = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
            },
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("results", [])[:max_results]:
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", "")[:300],
                )
            )
        return results
