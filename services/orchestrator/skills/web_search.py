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

    async def search(
        self, query: str, max_results: int = 5, provider_override: str | None = None
    ) -> tuple[list[SearchResult], str]:
        """
        Search and return (results, provider_used).

        provider_override: if set, try this provider first (skipping enabled check).
        Falls back to the configured order if the override provider fails or returns nothing.
        """
        cfg = self._load_config()
        default = cfg.get("default_provider", "tavily")
        providers_cfg = cfg.get("providers", {})

        all_providers = ["tavily", "yandex", "brave"]

        # Build order: override (if given) → default → rest
        if provider_override and provider_override in all_providers:
            order = [provider_override] + [p for p in all_providers if p != provider_override]
        else:
            order = [default] + [p for p in all_providers if p != default]

        for provider in order:
            p_cfg = providers_cfg.get(provider, {})
            # Allow override to bypass the enabled flag (user explicitly asked for it)
            is_override = provider == provider_override
            if not is_override and not p_cfg.get("enabled", False):
                continue
            try:
                results: list[SearchResult] = []
                if provider == "tavily":
                    key = settings.tavily_api_key
                    if key:
                        results = await self._search_tavily(query, max_results, key)
                elif provider == "yandex":
                    key = settings.yandex_search_key
                    folder_id = settings.yandex_folder_id
                    if key and folder_id:
                        deferred = p_cfg.get("use_deferred", False)
                        if deferred:
                            results = await self._search_yandex_deferred(
                                query, max_results, folder_id, key
                            )
                        else:
                            results = await self._search_yandex(query, max_results, folder_id, key)
                elif provider == "brave":
                    key = settings.brave_search_key
                    if key:
                        results = await self._search_brave(query, max_results, key)

                if results:
                    logger.info(f"web_search: used provider={provider}, got {len(results)} results")
                    return results, provider

            except Exception as e:
                logger.warning(f"Search provider {provider} failed: {e}, trying next")
                continue

        logger.error("All search providers failed or returned no results")
        return [], "none"

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
    # Yandex Search API v2 (Yandex Cloud / AI Studio)
    # Docs: https://aistudio.yandex.ru/docs/ru/search-api/api-ref/
    # Auth: Authorization: Api-Key <AQVN...>
    # Requires: YANDEX_SEARCH_KEY + YANDEX_FOLDER_ID in .env
    # -------------------------------------------------------------------------

    _YANDEX_SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/web/search"
    _YANDEX_SEARCH_ASYNC_URL = "https://searchapi.api.cloud.yandex.net/v2/web/searchAsync"
    _YANDEX_OPERATION_URL = "https://operation.api.cloud.yandex.net/operations"

    @staticmethod
    def _parse_yandex_xml(xml_text: str, max_results: int) -> list[SearchResult]:
        """Parse Yandex XML search response (embedded in v2 rawData field)."""
        results: list[SearchResult] = []
        try:
            root = ET.fromstring(xml_text)
            response_el = root.find("response") or root

            for doc in response_el.iter("doc"):
                if len(results) >= max_results:
                    break
                url_el = doc.find("url")
                title_el = doc.find("title")
                headline_el = doc.find("headline")
                if url_el is None:
                    continue

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

    @staticmethod
    def _parse_yandex_v2_response(data: dict, max_results: int) -> list[SearchResult]:
        """Parse Yandex Search API v2 JSON — rawData is base64-encoded XML."""
        import base64

        raw = data.get("rawData") or data.get("response", {}).get("rawData", "")
        if not raw:
            logger.warning("Yandex v2: no rawData in response, keys: %s", list(data.keys()))
            return []
        try:
            xml_text = base64.b64decode(raw).decode("utf-8", errors="replace")
            return WebSearchSkill._parse_yandex_xml(xml_text, max_results)
        except Exception as e:
            logger.warning(f"Yandex v2: failed to decode rawData: {e}")
            return []

    def _yandex_headers(self, key: str) -> dict[str, str]:
        return {
            "Authorization": f"Api-Key {key}",
            "Content-Type": "application/json",
        }

    def _yandex_body(self, query: str, max_results: int, folder_id: str) -> dict:
        return {
            "folderId": folder_id,
            "query": {
                "searchType": "SEARCH_TYPE_RU",
                "queryText": query,
            },
            "groupingOptions": {
                "groupsOnPage": max_results,
                "docsInGroup": 1,
            },
        }

    async def _search_yandex(
        self, query: str, max_results: int, folder_id: str, key: str
    ) -> list[SearchResult]:
        """Synchronous Yandex Search API v2."""
        client = await self._get_client()
        response = await client.post(
            self._YANDEX_SEARCH_URL,
            headers=self._yandex_headers(key),
            json=self._yandex_body(query, max_results, folder_id),
            timeout=15.0,
        )
        response.raise_for_status()
        return self._parse_yandex_v2_response(response.json(), max_results)

    async def _search_yandex_deferred(
        self,
        query: str,
        max_results: int,
        folder_id: str,
        key: str,
        poll_interval: float = 2.0,
        max_polls: int = 15,
    ) -> list[SearchResult]:
        """
        Async Yandex Search API v2 — submit job then poll operations endpoint.
        Falls back to synchronous search if deferred fails or times out.
        """
        import asyncio

        client = await self._get_client()
        headers = self._yandex_headers(key)
        body = self._yandex_body(query, max_results, folder_id)

        try:
            start_resp = await client.post(
                self._YANDEX_SEARCH_ASYNC_URL,
                headers=headers,
                json=body,
                timeout=15.0,
            )
            start_resp.raise_for_status()
            operation = start_resp.json()
            op_id = operation.get("id")
            if not op_id:
                logger.warning("Yandex deferred: no operation id, falling back to sync")
                return await self._search_yandex(query, max_results, folder_id, key)
            logger.debug(f"Yandex deferred search started: op_id={op_id}")

            for attempt in range(max_polls):
                await asyncio.sleep(poll_interval)
                poll_resp = await client.get(
                    f"{self._YANDEX_OPERATION_URL}/{op_id}",
                    headers=headers,
                    timeout=15.0,
                )
                poll_resp.raise_for_status()
                op = poll_resp.json()
                if not op.get("done", False):
                    logger.debug(f"Yandex deferred: still running (attempt {attempt + 1})")
                    continue
                if "error" in op:
                    logger.warning(f"Yandex deferred: operation error: {op['error']}")
                    return []
                result_data = op.get("response", op)
                results = self._parse_yandex_v2_response(result_data, max_results)
                logger.debug(f"Yandex deferred search done: {len(results)} results")
                return results

            logger.warning("Yandex deferred search timed out, falling back to sync")
            return await self._search_yandex(query, max_results, folder_id, key)

        except Exception as e:
            logger.warning(f"Yandex deferred search failed ({e}), falling back to sync")
            return await self._search_yandex(query, max_results, folder_id, key)

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
