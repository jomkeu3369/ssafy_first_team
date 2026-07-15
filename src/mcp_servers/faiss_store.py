from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import faiss
import numpy as np
from langchain_openai import OpenAIEmbeddings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.core.config import get_settings
from src.core.database import engine


INDEX_FILE = "index.faiss"
DOCUMENTS_FILE = "documents.json"
MANIFEST_FILE = "manifest.json"
MAX_DOCUMENT_CHARACTERS = 6000
settings = get_settings()
_build_lock = asyncio.Lock()


@dataclass(frozen=True, slots=True)
class VectorStoreBundle:
    index: Any
    documents: list[dict[str, Any]]
    fingerprint: str
    rebuilt: bool


@dataclass(frozen=True, slots=True)
class VectorStoreStatus:
    ready: bool
    stale: bool
    document_count: int
    indexed_count: int
    fingerprint: str
    embedding_model: str | None
    built_at: str | None


_cached_bundle: VectorStoreBundle | None = None
_cached_embedding_model: str | None = None


class VectorStoreError(Exception):
    pass


def _document(content: str, source_type: str, source_id: Any, title: str, address: str | None, image_url: str | None, category: str | None) -> dict[str, Any]:
    return {"content": content[:MAX_DOCUMENT_CHARACTERS], "metadata": {"source_type": source_type, "source_id": str(source_id), "title": title, "address": address, "image_url": image_url, "category": category}}


async def load_search_documents(target_engine: AsyncEngine = engine) -> tuple[list[dict[str, Any]], str]:
    documents: list[dict[str, Any]] = []
    async with target_engine.connect() as connection:
        tables = {row[0] for row in await connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))}
        if "Board" in tables:
            board_rows = await connection.execute(text('SELECT "boardId", name, category, description, image, address, "eventStartDate", "eventEndDate", "eventPlace" FROM "Board" ORDER BY "boardId"'))
            for row in board_rows.mappings():
                fields = [f"장소명: {row['name']}", f"카테고리: {row['category']}"]
                fields.extend(f"{label}: {row[key]}" for label, key in (("주소", "address"), ("설명", "description"), ("행사 시작일", "eventStartDate"), ("행사 종료일", "eventEndDate"), ("행사 장소", "eventPlace")) if row[key])
                documents.append(_document("\n".join(fields), "Board", row["boardId"], row["name"], row["address"], row["image"], row["category"]))
        if "post" in tables:
            tags_expression = '(SELECT GROUP_CONCAT(t.name, ", ") FROM "Post_Tags" pt JOIN "Tag" t ON t."tagId" = pt."tagId" WHERE pt."postId" = p."postId")' if {"Post_Tags", "Tag"} <= tables else "NULL"
            post_rows = await connection.execute(text(f'SELECT p."postId", p.title, p.content, b.name AS board_name, b.category, {tags_expression} AS tags FROM post p JOIN "Board" b ON b."boardId" = p."boardId" ORDER BY p."postId"'))
            for row in post_rows.mappings():
                fields = [f"게시글 제목: {row['title']}", f"게시판: {row['board_name']}", f"카테고리: {row['category']}", f"본문: {row['content']}"]
                if row["tags"]:
                    fields.append(f"태그: {row['tags']}")
                documents.append(_document("\n".join(fields), "post", row["postId"], row["title"], None, None, row["category"]))

    serialized = json.dumps(documents, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return documents, hashlib.sha256(serialized.encode()).hexdigest()


def _paths(index_dir: Path) -> tuple[Path, Path, Path]:
    return index_dir / INDEX_FILE, index_dir / DOCUMENTS_FILE, index_dir / MANIFEST_FILE


async def vector_store_status(target_engine: AsyncEngine = engine) -> VectorStoreStatus:
    documents, fingerprint = await load_search_documents(target_engine)
    index_path, documents_path, manifest_path = _paths(settings.faiss_index_dir)
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
    ready = index_path.exists() and documents_path.exists() and manifest.get("fingerprint") == fingerprint and manifest.get("embeddingModel") == settings.openai_embedding_model and manifest.get("documentCount") == len(documents)
    return VectorStoreStatus(ready=ready, stale=not ready, document_count=len(documents), indexed_count=int(manifest.get("documentCount") or 0), fingerprint=fingerprint, embedding_model=manifest.get("embeddingModel"), built_at=manifest.get("builtAt"))


def _load_existing(index_dir: Path, fingerprint: str, embedding_model: str) -> VectorStoreBundle | None:
    index_path, documents_path, manifest_path = _paths(index_dir)
    if not index_path.exists() or not documents_path.exists() or not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("fingerprint") != fingerprint or manifest.get("embeddingModel") != embedding_model:
            return None
        index = faiss.read_index(str(index_path))
        documents = json.loads(documents_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if index.ntotal != len(documents) or len(documents) != manifest.get("documentCount"):
        return None
    return VectorStoreBundle(index=index, documents=documents, fingerprint=fingerprint, rebuilt=False)


def _document_key(document: dict[str, Any]) -> str:
    serialized = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def _load_reusable_vectors(index_dir: Path, embedding_model: str) -> dict[str, np.ndarray]:
    index_path, documents_path, manifest_path = _paths(index_dir)
    if not index_path.exists() or not documents_path.exists() or not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("embeddingModel") != embedding_model:
            return {}
        index = faiss.read_index(str(index_path))
        documents = json.loads(documents_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    if index.ntotal != len(documents):
        return {}
    return {_document_key(document): index.reconstruct(position) for position, document in enumerate(documents)}


async def _document_vectors(documents: list[dict[str, Any]], reusable: dict[str, np.ndarray]) -> np.ndarray:
    keys = [_document_key(document) for document in documents]
    missing_positions = [position for position, key in enumerate(keys) if key not in reusable]
    new_vectors: np.ndarray | None = None
    if missing_positions:
        embeddings = OpenAIEmbeddings(model=settings.openai_embedding_model, api_key=settings.openai_api_key)
        contents = [documents[position]["content"] for position in missing_positions]
        new_vectors = np.asarray(await embeddings.aembed_documents(contents), dtype="float32")
        if new_vectors.ndim != 2 or new_vectors.shape[0] != len(missing_positions) or new_vectors.shape[1] == 0:
            raise VectorStoreError("Embedding response has an invalid shape")
    dimension = new_vectors.shape[1] if new_vectors is not None else next(iter(reusable.values())).shape[0]
    vectors = np.empty((len(documents), dimension), dtype="float32")
    new_position = 0
    for position, key in enumerate(keys):
        if key in reusable:
            vector = reusable[key]
            if vector.shape[0] != dimension:
                raise VectorStoreError("Reusable embedding dimension does not match")
            vectors[position] = vector
        else:
            vectors[position] = new_vectors[new_position]
            new_position += 1
    return vectors


def _write_bundle(index_dir: Path, index: Any, documents: list[dict[str, Any]], fingerprint: str, embedding_model: str) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    temporary_index = index_dir / f".{token}.{INDEX_FILE}"
    temporary_documents = index_dir / f".{token}.{DOCUMENTS_FILE}"
    temporary_manifest = index_dir / f".{token}.{MANIFEST_FILE}"
    index_path, documents_path, manifest_path = _paths(index_dir)
    manifest = {"fingerprint": fingerprint, "embeddingModel": embedding_model, "documentCount": len(documents), "builtAt": datetime.now(UTC).isoformat()}
    try:
        faiss.write_index(index, str(temporary_index))
        temporary_documents.write_text(json.dumps(documents, ensure_ascii=False), encoding="utf-8")
        temporary_manifest.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary_index, index_path)
        os.replace(temporary_documents, documents_path)
        os.replace(temporary_manifest, manifest_path)
    finally:
        for path in (temporary_index, temporary_documents, temporary_manifest):
            path.unlink(missing_ok=True)


def _cache(bundle: VectorStoreBundle, embedding_model: str) -> VectorStoreBundle:
    global _cached_bundle, _cached_embedding_model
    _cached_bundle = bundle
    _cached_embedding_model = embedding_model
    return bundle


def _cached(fingerprint: str, embedding_model: str) -> VectorStoreBundle | None:
    if _cached_bundle is None or _cached_bundle.fingerprint != fingerprint or _cached_embedding_model != embedding_model:
        return None
    return VectorStoreBundle(index=_cached_bundle.index, documents=_cached_bundle.documents, fingerprint=fingerprint, rebuilt=False)


async def _ensure_vector_store(force: bool, target_engine: AsyncEngine) -> VectorStoreBundle:
    if not settings.openai_api_key:
        raise VectorStoreError("OPENAI_API_KEY is not configured")
    documents, fingerprint = await load_search_documents(target_engine)
    if not documents:
        raise VectorStoreError("No Board or post documents are available")
    if not force and (cached := _cached(fingerprint, settings.openai_embedding_model)) is not None:
        return cached
    if not force and (existing := await asyncio.to_thread(_load_existing, settings.faiss_index_dir, fingerprint, settings.openai_embedding_model)) is not None:
        return _cache(existing, settings.openai_embedding_model)

    async with _build_lock:
        documents, fingerprint = await load_search_documents(target_engine)
        if not force and (cached := _cached(fingerprint, settings.openai_embedding_model)) is not None:
            return cached
        if not force and (existing := await asyncio.to_thread(_load_existing, settings.faiss_index_dir, fingerprint, settings.openai_embedding_model)) is not None:
            return _cache(existing, settings.openai_embedding_model)
        
        reusable = {} if force else await asyncio.to_thread(_load_reusable_vectors, settings.faiss_index_dir, settings.openai_embedding_model)
        vectors = await _document_vectors(documents, reusable)
        
        faiss.normalize_L2(vectors)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        
        await asyncio.to_thread(_write_bundle, settings.faiss_index_dir, index, documents, fingerprint, settings.openai_embedding_model)
        return _cache(VectorStoreBundle(index=index, documents=documents, fingerprint=fingerprint, rebuilt=True), settings.openai_embedding_model)


async def ensure_vector_store(force: bool = False, target_engine: AsyncEngine = engine) -> VectorStoreBundle:
    try:
        return await _ensure_vector_store(force, target_engine)
    except VectorStoreError:
        raise
    except Exception as exc:
        raise VectorStoreError("FAISS vector store could not be prepared") from exc
