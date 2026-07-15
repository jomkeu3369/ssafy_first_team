from __future__ import annotations

import asyncio
import json
from typing import Any

import faiss
import numpy as np
from langchain_openai import OpenAIEmbeddings
from mcp.server.fastmcp import FastMCP
from sqlalchemy import text

from src.core.config import get_settings
from src.core.database import engine


mcp = FastMCP("local-search")
settings = get_settings()
_faiss_index: Any | None = None
_faiss_documents: list[dict[str, Any]] | None = None
_vector_store_lock = asyncio.Lock()

SEARCHABLE_TABLES: dict[str, dict[str, tuple[str, ...]]] = {
    "regional_contents": {
        "id": ("id", "content_id"),
        "title": ("title", "name"),
        "content": ("content", "description", "overview"),
        "address": ("address", "addr1"),
        "image_url": ("image_url", "first_image"),
        "region": ("region", "district", "sigungu_name"),
    },
    "posts": {
        "id": ("id", "post_id"),
        "title": ("title",),
        "content": ("content", "body"),
        "address": (),
        "image_url": ("image_url",),
        "region": ("region", "district"),
    },
    "qa_documents": {
        "id": ("id", "document_id"),
        "title": ("title", "question"),
        "content": ("content", "answer"),
        "address": (),
        "image_url": (),
        "region": ("region",),
    },
}


def _first_existing(candidates: tuple[str, ...], columns: set[str]) -> str | None:
    return next((name for name in candidates if name in columns), None)


def _select_expression(column: str | None, alias: str) -> str:
    return f'"{column}" AS "{alias}"' if column else f'NULL AS "{alias}"'


def _read_faiss_bundle() -> tuple[Any, list[dict[str, Any]]]:
    index = faiss.read_index(str(settings.faiss_index_dir / "index.faiss"))
    with (settings.faiss_index_dir / "documents.json").open(encoding="utf-8") as file:
        documents = json.load(file)
    if index.ntotal != len(documents):
        msg = "FAISS index and document metadata have different lengths"
        raise ValueError(msg)
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
        return {
            "items": [],
            "notice": "FAISS index does not exist. Run scripts/build_faiss_index.py.",
        }
    if not settings.openai_api_key:
        return {"items": [], "notice": "OPENAI_API_KEY is not configured."}

    index, documents = await _load_vector_store()
    embeddings = OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )
    query_vector = np.asarray([await embeddings.aembed_query(query)], dtype="float32")
    faiss.normalize_L2(query_vector)
    scores, positions = await asyncio.to_thread(index.search, query_vector, limit)
    items = []
    for score, position in zip(scores[0], positions[0], strict=True):
        if position < 0:
            continue
        document = documents[position]
        metadata = document.get("metadata", {})
        items.append(
            {
                "sourceType": metadata.get("source_type", "document"),
                "sourceId": str(metadata.get("source_id", "")),
                "title": metadata.get("title"),
                "content": document["content"],
                "address": metadata.get("address"),
                "imageUrl": metadata.get("image_url"),
                "score": float(score),
            }
        )
    return {"items": items}


async def search_sqlite_database(
    keyword: str,
    content_type: str | None = None,
    region: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    limit = max(1, min(limit, 20))
    requested_tables = (
        [content_type] if content_type in SEARCHABLE_TABLES else list(SEARCHABLE_TABLES)
    )
    items: list[dict[str, Any]] = []

    async with engine.connect() as connection:
        existing = await connection.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table'")
        )
        existing_tables = {row[0] for row in existing}

        for table in requested_tables:
            if table not in existing_tables or len(items) >= limit:
                continue

            pragma = await connection.execute(text(f'PRAGMA table_info("{table}")'))
            columns = {row[1] for row in pragma}
            aliases = SEARCHABLE_TABLES[table]
            selected = {
                key: _first_existing(candidates, columns)
                for key, candidates in aliases.items()
            }
            search_columns = [
                column
                for key in ("title", "content", "address")
                if (column := selected[key])
            ]
            if not search_columns:
                continue

            select_parts = [
                _select_expression(selected[key], key)
                for key in ("id", "title", "content", "address", "image_url")
            ]
            where_parts = [
                "("
                + " OR ".join(
                    f"COALESCE(\"{column}\", '') LIKE :keyword"
                    for column in search_columns
                )
                + ")"
            ]
            parameters: dict[str, Any] = {
                "keyword": f"%{keyword}%",
                "limit": limit - len(items),
            }
            if region and selected["region"]:
                where_parts.append(
                    f"COALESCE(\"{selected['region']}\", '') LIKE :region"
                )
                parameters["region"] = f"%{region}%"

            statement = text(
                f'SELECT {", ".join(select_parts)} FROM "{table}" '
                f"WHERE {' AND '.join(where_parts)} LIMIT :limit"
            )
            result = await connection.execute(statement, parameters)
            for row in result.mappings():
                items.append(
                    {
                        "sourceType": table,
                        "sourceId": str(row["id"] or ""),
                        "title": row["title"],
                        "content": row["content"],
                        "address": row["address"],
                        "imageUrl": row["image_url"],
                    }
                )

    return {"items": items}


@mcp.tool()
async def search_faiss(query: str, limit: int = 5) -> dict[str, Any]:
    """Semantically search the trusted local FAISS knowledge index."""
    return await search_faiss_index(query, limit)


@mcp.tool()
async def search_sqlite(
    keyword: str,
    content_type: str | None = None,
    region: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Search allowlisted LocalHub SQLite content; arbitrary SQL is not accepted."""
    return await search_sqlite_database(keyword, content_type, region, limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
