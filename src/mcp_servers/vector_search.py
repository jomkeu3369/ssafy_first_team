from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from src.mcp_servers.local_search import search_faiss_index


mcp = FastMCP("vector-search")


@mcp.tool()
async def search_faiss(query: str, limit: int = 5) -> dict[str, Any]:
    """Semantically search synchronized LocalHub Board and post data."""
    return await search_faiss_index(query, limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
