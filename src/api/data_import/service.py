import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data_import.schema import FaissIndexResponse, FaissIndexStatusResponse, ImportResponse
from src.core.config import get_settings
from src.mcp_servers.faiss_store import ensure_vector_store, vector_store_status
from src.models.board import Board


MAX_FILE_COUNT = 10
MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_DESCRIPTION_LENGTH = 1000
ALLOWED_CATEGORIES = {"관광지", "레포츠", "문화시설", "쇼핑", "숙박", "여행코스", "축제공연행사"}


class InvalidImportFileError(Exception):
    pass


class ImportFileTooLargeError(Exception):
    pass


class TooManyImportFilesError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CleanBoard:
    name: str
    category: str
    description: str | None
    image: str | None
    source_content_id: str | None
    address: str | None
    event_start_date: str | None
    event_end_date: str | None
    event_place: str | None


_import_lock = asyncio.Lock()
settings = get_settings()


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _build_description(item: dict[str, Any]) -> str | None:
    address = " ".join(value for value in (_clean_text(item.get("addr1")), _clean_text(item.get("addr2"))) if value)
    event_dates = " ~ ".join(value for value in (_clean_text(item.get("eventstartdate")), _clean_text(item.get("eventenddate"))) if value)
    fields = (("주소", address), ("전화", _clean_text(item.get("tel"))), ("우편번호", _clean_text(item.get("zipcode"))), ("행사기간", event_dates), ("행사장소", _clean_text(item.get("eventplace"))), ("이용시간", _clean_text(item.get("playtime"))))
    description = " | ".join(f"{label}: {value}" for label, value in fields if value)
    return description[:MAX_DESCRIPTION_LENGTH] or None


async def _read_payload(file: UploadFile) -> dict[str, Any]:
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise ImportFileTooLargeError
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidImportFileError from exc
    if not isinstance(payload, dict):
        raise InvalidImportFileError
    return payload


async def clean_uploads(files: list[UploadFile]) -> tuple[list[CleanBoard], int, dict[str, int]]:
    if not files or len(files) > MAX_FILE_COUNT:
        raise TooManyImportFilesError

    boards: list[CleanBoard] = []
    categories: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    skipped = 0
    for file in files:
        payload = await _read_payload(file)
        category = _clean_text(payload.get("contentType"))
        items = payload.get("items")
        if category not in ALLOWED_CATEGORIES or not isinstance(items, list):
            raise InvalidImportFileError
        for item in items:
            if not isinstance(item, dict):
                skipped += 1
                continue
            name = _clean_text(item.get("title"))[:100]
            key = (name, category)
            if not name or key in seen:
                skipped += 1
                continue
            seen.add(key)
            image = _clean_text(item.get("firstimage") or item.get("firstimage2"))[:2000] or None
            address = " ".join(value for value in (_clean_text(item.get("addr1")), _clean_text(item.get("addr2"))) if value)[:500] or None
            boards.append(CleanBoard(name=name, category=category, description=_build_description(item), image=image, source_content_id=_clean_text(item.get("contentid"))[:100] or None, address=address, event_start_date=_clean_text(item.get("eventstartdate"))[:8] or None, event_end_date=_clean_text(item.get("eventenddate"))[:8] or None, event_place=_clean_text(item.get("eventplace"))[:500] or None))
            categories[category] = categories.get(category, 0) + 1
    return boards, skipped, categories


async def import_boards(db: AsyncSession, files: list[UploadFile], update_existing: bool) -> ImportResponse:
    boards, skipped, categories = await clean_uploads(files)
    async with _import_lock:
        existing_rows = list((await db.scalars(select(Board))).all())
        existing = {(row.name, row.category): row for row in existing_rows}
        occupied = {row.board_id for row in existing_rows}
        next_board_id = 1
        while next_board_id in occupied:
            next_board_id += 1
        inserted = 0
        updated = 0
        unchanged = 0
        for item in boards:
            row = existing.get((item.name, item.category))
            if row is None:
                row = Board(board_id=next_board_id, name=item.name, category=item.category, description=item.description, image=item.image, source_content_id=item.source_content_id, address=item.address, event_start_date=item.event_start_date, event_end_date=item.event_end_date, event_place=item.event_place)
                db.add(row)
                existing[(item.name, item.category)] = row
                occupied.add(next_board_id)
                next_board_id += 1
                while next_board_id in occupied:
                    next_board_id += 1
                inserted += 1
            elif update_existing and (row.description != item.description or row.image != item.image or row.source_content_id != item.source_content_id or row.address != item.address or row.event_start_date != item.event_start_date or row.event_end_date != item.event_end_date or row.event_place != item.event_place):
                row.description = item.description
                row.image = item.image
                row.source_content_id = item.source_content_id
                row.address = item.address
                row.event_start_date = item.event_start_date
                row.event_end_date = item.event_end_date
                row.event_place = item.event_place
                updated += 1
            else:
                unchanged += 1
        await db.commit()
    return ImportResponse(source_count=len(files), inserted_count=inserted, updated_count=updated, unchanged_count=unchanged, skipped_count=skipped, categories=categories)


async def rebuild_faiss_index() -> FaissIndexResponse:
    bundle = await ensure_vector_store(force=True)
    return FaissIndexResponse(indexed_count=len(bundle.documents), fingerprint=bundle.fingerprint, embedding_model=settings.openai_embedding_model, rebuilt=bundle.rebuilt)


async def get_faiss_index_status() -> FaissIndexStatusResponse:
    current = await vector_store_status()
    return FaissIndexStatusResponse(ready=current.ready, stale=current.stale, document_count=current.document_count, indexed_count=current.indexed_count, fingerprint=current.fingerprint, embedding_model=current.embedding_model, built_at=current.built_at)
