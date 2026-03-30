"""
Web search skill.

Supports multiple providers with fallback:
  - tavily  (requires TAVILY_API_KEY  — best for AI agents)
  - yandex  (requires YANDEX_SEARCH_KEY + YANDEX_SEARCH_USER — great for RU queries)
  - brave   (requires BRAVE_SEARCH_KEY)

Active provider is read from providers.yaml -> skills.web_search.default_provider.
Providers are tried in order; on failure the next one is used automatically.
"""

import logging
import xml.etree.ElementTree as ET
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
        """Load skills.web_search config from providers.yaml."""
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
        default = cfg.get("default_provider", "tavily")
        providers_cfg = cfg.get("providers", {})

        all_providers = ["tavily", "yandex", "brave"]
        order = [default] + [p for p in all_providers if p != default]

        for provider in order:
            p_cfg = providers_cfg.get(provider, {})
            if not p_cfg.get("enabled", False):
                continue
            try:
                if provider == "tavily":
                    key = settings.tavily_api_key
                    if key:
                        results = await self._search_tavily(query, max_results, key)
                        if results:
                            return results
                elif provider == "yandex":
                    key = settings.yandex_search_key
                    user = settings.yandex_search_user
                    if key and user:
                        deferred = p_cfg.get("use_deferred", False)
                        if deferred:
                            results = await self._search_yandex_deferred(
                                query, max_results, user, key
                            )
                        else:
                            results = await self._search_yandex(query, max_results, user, key)
                        if results:
                            return results
                elif provider == "brave":
                    key = settings.brave_search_key
                    if key:
                        results = await self._search_brave(query, max_results, key)
                        if results:
                            return results
            except Exception as e:
                logger.warning(f"Search provider {provider} failed: {e}, trying next")
                continue

        logger.error("All search providers failed or returned no results")
        return []

    # -------------------------------------------------------------------------
    # Tavily
    # -------------------------------------------------------------------------

    async def _search_tavily(
        self, query: str, max_results: int, api_key: str
    ) -> list[SearchResult]:
        """Search using Tavily AI Search API (best for AI agents)."""
        client = await self._get_client()
        response = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
            },
            timeout=15.0,
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

    # -------------------------------------------------------------------------
    # Yandex XML
    # -------------------------------------------------------------------------

    @staticmethod
    def _parse_yandex_xml(xml_text: str, max_results: int) -> list[SearchResult]:
        """Parse Yandex XML search response into SearchResult list."""
        results: list[SearchResult] = []
        try:
            root = ET.fromstring(xml_text)
            ns = ""
            response_el = root.find(f"{ns}response")
            if response_el is None:
                response_el = root

            for doc in response_el.iter("doc"):
                if len(results) >= max_results:
                    break
                url_el = doc.find("url")
                title_el = doc.find("title")
                headline_el = doc.find("headline")
                if url_el is None:
                    continue

                # Strip embedded XML tags (e.g. <hlword>) from title/headline
                def _text(el: ET.Element | None) -> str:
                    if el is None:
                        return ""
                    return "".join(el.itertext()).strip()

                results.append(
                    SearchResult(
                        title=_text(title_el),
                        url=(url_el.text or "").strip(),
                        snippet=_text(headline_el)[:300],
                    )
                )
        except ET.ParseError as e:
            logger.warning(f"Failed to parse Yandex XML response: {e}")
        return results

    async def _search_yandex(
        self, query: str, max_results: int, user: str, key: str
    ) -> list[SearchResult]:
        """Synchronous Yandex XML search."""
        client = await self._get_client()
        params = {
            "user": user,
            "key": key,
            "query": query,
            "l10n": "ru",
            "sortby": "rlv",
            "filter": "none",
            "groupby": f'attr="".mode=flat.groups-on-page={max_results}.docs-in-group=1',
        }
        response = await client.get(
            "https://yandex.com/search/xml",
            params=params,
            headers={"Accept": "application/xml"},
            timeout=15.0,
        )
        response.raise_for_status()
        return self._parse_yandex_xml(response.text, max_results)

    async def _search_yandex_deferred(
        self,
        query: str,
        max_results: int,
        user: str,
        key: str,
        poll_interval: float = 1.5,
        max_polls: int = 10,
    ) -> list[SearchResult]:
        """
        Deferred (async) Yandex XML search — submit job then poll until results arrive.
        Falls back to synchronous search if deferred fails.
        """
        import asyncio

        client = await self._get_client()
        auth_params = {"user": user, "key": key}
        query_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<request>"
            f"<query>{query}</query>"
            "<sortby>rlv</sortby>"
            "<filter-info>"
            '<filtering id="moderate"/>'
            "</filter-info>"
            f'<groupings><groupby attr="" mode="flat" groups-on-page="{max_results}" docs-in-group="1"/></groupings>'
            "</request>"
        )

        try:
            # Step 1: submit
            start_resp = await client.post(
                "https://yandex.com/search/xml/deferred-start",
                params=auth_params,
                content=query_xml,
                headers={"Content-Type": "application/xml"},
                timeout=15.0,
            )
            start_resp.raise_for_status()
            start_root = ET.fromstring(start_resp.text)
            req_id_el = start_root.find(".//req-id") or start_root.find("req-id")
            if req_id_el is None or not req_id_el.text:
                logger.warning("Yandex deferred: no req-id in response, falling back to sync")
                return await self._search_yandex(query, max_results, user, key)
            req_id = req_id_el.text.strip()
            logger.debug(f"Yandex deferred search started: req_id={req_id}")

            # Step 2: poll
            for _ in range(max_polls):
                await asyncio.sleep(poll_interval)
                poll_resp = await client.get(
                    "https://yandex.com/search/xml/deferred",
                    params={**auth_params, "req_id": req_id},
                    timeout=15.0,
                )
                if poll_resp.status_code == 202:
                    # Still in progress
                    continue
                poll_resp.raise_for_status()
                results = self._parse_yandex_xml(poll_resp.text, max_results)
                logger.debug(f"Yandex deferred search done: {len(results)} results")
                return results

            logger.warning("Yandex deferred search timed out, falling back to sync")
            return await self._search_yandex(query, max_results, user, key)

        except Exception as e:
            logger.warning(f"Yandex deferred search failed ({e}), falling back to sync")
            return await self._search_yandex(query, max_results, user, key)

    # -------------------------------------------------------------------------
    # Brave
    # -------------------------------------------------------------------------

    async def _search_brave(self, query: str, max_results: int, api_key: str) -> list[SearchResult]:
        """Search using Brave Search API."""
        client = await self._get_client()
        response = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            timeout=15.0,
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
