from __future__ import annotations

from typing import Any

import faiss
import numpy as np
from langchain_openai import OpenAIEmbeddings
from mcp.server.fastmcp import FastMCP

from src.core.config import get_settings
from src.mcp_servers.faiss_store import VectorStoreError, ensure_vector_store
from src.mcp_servers.sqlite_search import search_sqlite_database


mcp = FastMCP("local-search")
settings = get_settings()


async def search_faiss_index(query: str, limit: int = 5) -> dict[str, Any]:
    limit = max(1, min(limit, 10))
    if not settings.openai_api_key:
        return {"items": [], "notice": "OPENAI_API_KEY is not configured."}

    try:
        bundle = await ensure_vector_store()
    except VectorStoreError:
        return {"items": [], "notice": "FAISS index could not be prepared."}
    embeddings = OpenAIEmbeddings(model=settings.openai_embedding_model, api_key=settings.openai_api_key)
    query_vector = np.asarray([await embeddings.aembed_query(query)], dtype="float32")
    faiss.normalize_L2(query_vector)
    scores, positions = bundle.index.search(query_vector, limit)
    items = []
    for score, position in zip(scores[0], positions[0], strict=True):
        if position < 0:
            continue
        document = bundle.documents[position]
        metadata = document.get("metadata", {})
        items.append({"sourceType": metadata.get("source_type", "document"), "sourceId": str(metadata.get("source_id", "")), "title": metadata.get("title"), "content": document["content"], "address": metadata.get("address"), "imageUrl": metadata.get("image_url"), "score": float(score)})
    return {"items": items, "indexRebuilt": bundle.rebuilt}


@mcp.tool()
async def search_faiss(query: str, limit: int = 5) -> dict[str, Any]:
    """Semantically search Board and post data, automatically preparing the FAISS index when stale."""
    return await search_faiss_index(query, limit)


@mcp.tool()
async def search_sqlite(keyword: str, content_type: str | None = None, region: str | None = None, limit: int = 5) -> dict[str, Any]:
    """Search LocalHub Board and post tables. Use first for stored places, boards, and community posts."""
    return await search_sqlite_database(keyword, content_type, region, limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
