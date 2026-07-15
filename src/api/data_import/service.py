import asyncio
import json
import re
import secrets
from dataclasses import dataclass
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data_import.schema import ImportResponse
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


_import_lock = asyncio.Lock()


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
            boards.append(CleanBoard(name=name, category=category, description=_build_description(item)))
            categories[category] = categories.get(category, 0) + 1
    return boards, skipped, categories


def _new_board_id(occupied: set[int]) -> int:
    board_id = secrets.randbelow(2**63 - 1) + 1
    while board_id in occupied:
        board_id = secrets.randbelow(2**63 - 1) + 1
    occupied.add(board_id)
    return board_id


async def import_boards(db: AsyncSession, files: list[UploadFile], update_existing: bool) -> ImportResponse:
    boards, skipped, categories = await clean_uploads(files)
    async with _import_lock:
        existing_rows = list((await db.scalars(select(Board))).all())
        existing = {(row.name, row.category): row for row in existing_rows}
        occupied = {row.board_id for row in existing_rows}
        inserted = 0
        updated = 0
        unchanged = 0
        for item in boards:
            row = existing.get((item.name, item.category))
            if row is None:
                row = Board(board_id=_new_board_id(occupied), name=item.name, category=item.category, description=item.description)
                db.add(row)
                existing[(item.name, item.category)] = row
                inserted += 1
            elif update_existing and row.description != item.description:
                row.description = item.description
                updated += 1
            else:
                unchanged += 1
        await db.commit()
    return ImportResponse(source_count=len(files), inserted_count=inserted, updated_count=updated, unchanged_count=unchanged, skipped_count=skipped, categories=categories)
