from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from src.mcp_servers.tavily_search import search_tavily_web


mcp = FastMCP("web-search")


@mcp.tool()
async def search_web(query: str, limit: int = 3) -> dict[str, Any]:
    """Search current public web information with Tavily and return source URLs."""
    return await search_tavily_web(query, limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
