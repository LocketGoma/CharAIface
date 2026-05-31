from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.app.services.cloud_auth_manager import (
    CloudAuthManager,
    CloudCredentialConfig,
)


@dataclass(frozen=True)
class WebSearchItem:
    title: str
    url: str
    content: str = ""
    score: float | None = None


@dataclass(frozen=True)
class WebSearchResult:
    provider: str
    query: str
    results: list[WebSearchItem] = field(default_factory=list)
    answer: str = ""
    warning: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WebSearchConfig:
    enabled: bool
    provider: str
    auth_mode: str
    credential_id: str
    api_key_env: str | None = None
    base_url: str = ""
    max_results: int = 5
    timeout_seconds: float = 20.0
    country_code: str = ""
    location: str = ""
    tavily_country: str = ""


class WebSearchError(RuntimeError):
    pass


WEB_SEARCH_PROVIDER_HANDLERS = {
    "tavily": "_search_tavily",
    "firecrawl": "_search_firecrawl",
}


class WebSearchService:
    DEFAULT_TAVILY_BASE_URL = "https://api.tavily.com"
    DEFAULT_FIRECRAWL_BASE_URL = "https://api.firecrawl.dev/v2"

    def search(self, query: str, config: WebSearchConfig) -> WebSearchResult:
        query = str(query or "").strip()
        if not query:
            raise WebSearchError("Search query is empty.")

        if not config.enabled:
            raise WebSearchError("Web search is disabled.")

        provider = (config.provider or "none").strip().lower()
        if provider in {"", "none"}:
            raise WebSearchError("Web search provider is not configured.")

        api_key = self._resolve_api_key(config)
        if not api_key:
            raise WebSearchError("Web search API key was not found.")

        handler_name = WEB_SEARCH_PROVIDER_HANDLERS.get(provider)
        if handler_name is None:
            raise WebSearchError(f"Unsupported web search provider: {provider}")
        return getattr(self, handler_name)(query=query, api_key=api_key, config=config)

    def _resolve_api_key(self, config: WebSearchConfig) -> str | None:
        credential_config = CloudCredentialConfig(
            provider=config.provider,
            auth_mode=config.auth_mode,
            credential_id=config.credential_id,
            api_key_env=config.api_key_env,
        )
        return CloudAuthManager.get_api_key(credential_config)

    def _search_tavily(
        self,
        query: str,
        api_key: str,
        config: WebSearchConfig,
    ) -> WebSearchResult:
        base_url = (config.base_url or self.DEFAULT_TAVILY_BASE_URL).rstrip("/")
        max_results = self._clamp_max_results(config.max_results)
        payload = {
            "query": query,
            "search_depth": "basic",
            "topic": "general",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }
        tavily_country = str(config.tavily_country or "").strip().lower()
        if tavily_country:
            payload["country"] = tavily_country

        response = httpx.post(
            f"{base_url}/search",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=max(3.0, float(config.timeout_seconds)),
        )
        response.raise_for_status()
        data = response.json()

        items: list[WebSearchItem] = []
        for item in data.get("results") or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            content = str(item.get("content") or item.get("raw_content") or "").strip()
            score = item.get("score")
            if not url:
                continue
            items.append(
                WebSearchItem(
                    title=title or url,
                    url=url,
                    content=self._compact_text(content),
                    score=float(score) if isinstance(score, (int, float)) else None,
                )
            )

        return WebSearchResult(
            provider="tavily",
            query=str(data.get("query") or query),
            results=items,
            answer=str(data.get("answer") or "").strip(),
            raw=data,
        )

    def _search_firecrawl(
        self,
        query: str,
        api_key: str,
        config: WebSearchConfig,
    ) -> WebSearchResult:
        base_url = (config.base_url or self.DEFAULT_FIRECRAWL_BASE_URL).rstrip("/")
        max_results = self._clamp_max_results(config.max_results)
        payload = {
            "query": query,
            "limit": max_results,
            "sources": ["web"],
            "timeout": int(max(3.0, float(config.timeout_seconds)) * 1000),
            "ignoreInvalidURLs": True,
        }
        country_code = str(config.country_code or "").strip().upper()
        location = str(config.location or "").strip()
        if country_code:
            payload["country"] = country_code
        if location:
            payload["location"] = location

        response = httpx.post(
            f"{base_url}/search",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=max(3.0, float(config.timeout_seconds)) + 5.0,
        )
        response.raise_for_status()
        data = response.json()

        raw_results = data.get("data") or {}
        if isinstance(raw_results, dict):
            result_items = raw_results.get("web") or []
        elif isinstance(raw_results, list):
            result_items = raw_results
        else:
            result_items = []

        items: list[WebSearchItem] = []
        for item in result_items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            content = str(
                item.get("description")
                or item.get("markdown")
                or item.get("content")
                or ""
            ).strip()
            if not url:
                continue
            items.append(
                WebSearchItem(
                    title=title or url,
                    url=url,
                    content=self._compact_text(content),
                )
            )

        return WebSearchResult(
            provider="firecrawl",
            query=query,
            results=items,
            warning=str(data.get("warning") or "").strip(),
            raw=data,
        )

    def _clamp_max_results(self, max_results: int) -> int:
        try:
            value = int(max_results)
        except (TypeError, ValueError):
            value = 5
        return max(1, min(10, value))

    def _compact_text(self, text: str, limit: int = 700) -> str:
        compact = " ".join(str(text or "").split())
        if len(compact) > limit:
            return compact[: limit - 3].rstrip() + "..."
        return compact
