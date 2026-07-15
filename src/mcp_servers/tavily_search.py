from __future__ import annotations

from typing import Any

import httpx

from src.core.config import get_settings


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
settings = get_settings()


def _search_result(payload: dict[str, Any]) -> dict[str, Any]:
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    citations = [{"title": item.get("title") or item.get("url"), "url": item.get("url")} for item in results if isinstance(item, dict) and item.get("url")]
    fallback_answer = "\n\n".join(str(item.get("content", "")).strip() for item in results if isinstance(item, dict) and item.get("content"))
    return {"answer": str(payload.get("answer") or fallback_answer), "citations": citations}


async def search_tavily_web(query: str, limit: int = 3) -> dict[str, Any]:
    if not settings.tavily_api_key:
        return {"answer": "", "citations": [], "notice": "TAVILY_API_KEY is not configured."}

    max_results = max(1, min(limit, 5))
    request = {"query": query, "search_depth": "basic", "max_results": max_results, "topic": "general", "include_answer": "basic", "include_raw_content": False, "include_images": False, "safe_search": True}
    headers = {"Authorization": f"Bearer {settings.tavily_api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(TAVILY_SEARCH_URL, headers=headers, json=request)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {"answer": "", "citations": [], "notice": f"Tavily search returned HTTP {exc.response.status_code}."}
    except httpx.RequestError:
        return {"answer": "", "citations": [], "notice": "Tavily search request failed."}

    return _search_result(response.json())
