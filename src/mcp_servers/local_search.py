from __future__ import annotations

import asyncio
import json
from typing import Any

import faiss
import numpy as np
from langchain_openai import OpenAIEmbeddings
from mcp.server.fastmcp import FastMCP

from src.core.config import get_settings
from src.mcp_servers.sqlite_search import search_sqlite_database


mcp = FastMCP("local-search")
settings = get_settings()
_faiss_index: Any | None = None
_faiss_documents: list[dict[str, Any]] | None = None
_vector_store_lock = asyncio.Lock()


def _read_faiss_bundle() -> tuple[Any, list[dict[str, Any]]]:
    index = faiss.read_index(str(settings.faiss_index_dir / "index.faiss"))
    with (settings.faiss_index_dir / "documents.json").open(encoding="utf-8") as file:
        documents = json.load(file)
    if index.ntotal != len(documents):
        raise ValueError("FAISS index and document metadata have different lengths")
    return index, documents


async def _load_vector_store() -> tuple[Any, list[dict[str, Any]]]:
    global _faiss_documents, _faiss_index
    if _faiss_index is not None and _faiss_documents is not None:
        return _faiss_index, _faiss_documents
    async with _vector_store_lock:
        if _faiss_index is None or _faiss_documents is None:
            _faiss_index, _faiss_documents = await asyncio.to_thread(_read_faiss_bundle)
    return _faiss_index, _faiss_documents


async def search_faiss_index(query: str, limit: int = 5) -> dict[str, Any]:
    limit = max(1, min(limit, 10))
    index_path = settings.faiss_index_dir / "index.faiss"
    documents_path = settings.faiss_index_dir / "documents.json"
    if not index_path.exists() or not documents_path.exists():
        return {"items": [], "notice": "FAISS index does not exist. Run scripts/build_faiss_index.py."}
    if not settings.openai_api_key:
        return {"items": [], "notice": "OPENAI_API_KEY is not configured."}

    index, documents = await _load_vector_store()
    embeddings = OpenAIEmbeddings(model=settings.openai_embedding_model, api_key=settings.openai_api_key)
    query_vector = np.asarray([await embeddings.aembed_query(query)], dtype="float32")
    faiss.normalize_L2(query_vector)
    scores, positions = await asyncio.to_thread(index.search, query_vector, limit)
    items = []
    for score, position in zip(scores[0], positions[0], strict=True):
        if position < 0:
            continue
        document = documents[position]
        metadata = document.get("metadata", {})
        items.append({"sourceType": metadata.get("source_type", "document"), "sourceId": str(metadata.get("source_id", "")), "title": metadata.get("title"), "content": document["content"], "address": metadata.get("address"), "imageUrl": metadata.get("image_url"), "score": float(score)})
    return {"items": items}


@mcp.tool()
async def search_faiss(query: str, limit: int = 5) -> dict[str, Any]:
    """Semantically search the trusted local FAISS knowledge index."""
    return await search_faiss_index(query, limit)


@mcp.tool()
async def search_sqlite(keyword: str, content_type: str | None = None, region: str | None = None, limit: int = 5) -> dict[str, Any]:
    """Search LocalHub Board and post tables. Use first for stored places, boards, and community posts."""
    return await search_sqlite_database(keyword, content_type, region, limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
