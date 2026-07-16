from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from src.mcp_servers.sqlite_search import search_sqlite_database


mcp = FastMCP("database-search")


@mcp.tool()
async def search_sqlite(keyword: str, content_type: str | None = None, region: str | None = None, limit: int = 5) -> dict[str, Any]:
    """Search LocalHub Board and post tables. Use first for stored places, boards, and community posts."""
    return await search_sqlite_database(keyword, content_type, region, limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
