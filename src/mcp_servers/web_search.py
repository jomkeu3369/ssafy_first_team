from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from openai import AsyncOpenAI

from src.core.config import get_settings


mcp = FastMCP("web-search")
settings = get_settings()


def _collect_citations(value: Any) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    seen: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            url = node.get("url")
            if node.get("type") == "url_citation" and url and url not in seen:
                seen.add(url)
                citations.append({"title": node.get("title") or url, "url": url})
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return citations


async def search_openai_web(query: str, limit: int = 3) -> dict[str, Any]:
    model = settings.effective_web_search_model
    if not settings.openai_api_key or not model:
        return {
            "answer": "",
            "citations": [],
            "notice": "OPENAI_API_KEY and OPENAI_MODEL are required.",
        }

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.responses.create(
        model=model,
        tools=[{"type": "web_search"}],
        input=(
            f"Search the web for the following request. Return at most "
            f"{max(1, min(limit, 5))} useful sources and a concise factual summary.\n"
            f"Request: {query}"
        ),
    )
    dumped = response.model_dump(mode="json")
    return {
        "answer": response.output_text,
        "citations": _collect_citations(dumped),
    }


@mcp.tool()
async def search_web(query: str, limit: int = 3) -> dict[str, Any]:
    """Search current public web information and return source URLs."""
    return await search_openai_web(query, limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
