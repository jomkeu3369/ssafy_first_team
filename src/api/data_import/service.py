import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from fastapi import UploadFile
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data_import.schema import BoardTranslationResponse, FaissIndexResponse, FaissIndexStatusResponse, ImportResponse
from src.api.data_import.translation import BoardTranslator
from src.api.comment.translation import CommentTranslator
from src.api.data_import.schema import CommentTranslationResponse
from src.api.localization import BOARD_CATEGORY_EN
from src.core.config import get_settings
from src.mcp_servers.faiss_store import ensure_vector_store, vector_store_status
from src.models.board import Board
from src.models.comment import Comment


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
    name_en: str | None
    category: str
    description: str | None
    description_en: str | None
    image: str | None
    source_content_id: str | None
    address: str | None
    address_en: str | None
    event_start_date: str | None
    event_end_date: str | None
    event_place: str | None
    event_place_en: str | None


_import_lock = asyncio.Lock()
_translation_lock = asyncio.Lock()
settings = get_settings()


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _english_text(value: Any, limit: int) -> str | None:
    cleaned = _clean_text(value)[:limit]
    if not cleaned or re.search(r"[\uac00-\ud7a3]", cleaned):
        return None
    return cleaned


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
            address_en = " ".join(value for value in (_english_text(item.get("addr1En") or item.get("addr1_en"), 800), _english_text(item.get("addr2En") or item.get("addr2_en"), 200)) if value)[:1000] or None
            boards.append(CleanBoard(name=name, name_en=_english_text(item.get("titleEn") or item.get("title_en") or item.get("engtitle"), 200), category=category, description=_build_description(item), description_en=_english_text(item.get("descriptionEn") or item.get("description_en") or item.get("overviewEn"), 2000), image=image, source_content_id=_clean_text(item.get("contentid"))[:100] or None, address=address, address_en=address_en, event_start_date=_clean_text(item.get("eventstartdate"))[:8] or None, event_end_date=_clean_text(item.get("eventenddate"))[:8] or None, event_place=_clean_text(item.get("eventplace"))[:500] or None, event_place_en=_english_text(item.get("eventplaceEn") or item.get("eventplace_en"), 1000)))
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
                row = Board(board_id=next_board_id, name=item.name, name_kr=item.name, name_en=item.name_en, category=item.category, category_kr=item.category, category_en=BOARD_CATEGORY_EN[item.category], description=item.description, description_kr=item.description, description_en=item.description_en, image=item.image, source_content_id=item.source_content_id, address=item.address, address_en=item.address_en, event_start_date=item.event_start_date, event_end_date=item.event_end_date, event_place=item.event_place, event_place_en=item.event_place_en)
                db.add(row)
                existing[(item.name, item.category)] = row
                occupied.add(next_board_id)
                next_board_id += 1
                while next_board_id in occupied:
                    next_board_id += 1
                inserted += 1
            elif update_existing and _update_board(row, item):
                updated += 1
            else:
                unchanged += 1
        await db.commit()
    return ImportResponse(source_count=len(files), inserted_count=inserted, updated_count=updated, unchanged_count=unchanged, skipped_count=skipped, categories=categories)


def _update_board(row: Board, item: CleanBoard) -> bool:
    changed = False
    localized_values = (("name_kr", item.name), ("category_kr", item.category), ("category_en", BOARD_CATEGORY_EN[item.category]), ("description_kr", item.description))
    for attribute, value in localized_values:
        if getattr(row, attribute) != value:
            setattr(row, attribute, value)
            changed = True
    values = (("image", item.image), ("source_content_id", item.source_content_id), ("event_start_date", item.event_start_date), ("event_end_date", item.event_end_date))
    for attribute, value in values:
        if getattr(row, attribute) != value:
            setattr(row, attribute, value)
            changed = True
    translated_values = (("description", "description_en", item.description, item.description_en), ("address", "address_en", item.address, item.address_en), ("event_place", "event_place_en", item.event_place, item.event_place_en))
    for source_attribute, english_attribute, source_value, english_value in translated_values:
        if getattr(row, source_attribute) != source_value:
            setattr(row, source_attribute, source_value)
            setattr(row, english_attribute, english_value)
            changed = True
        elif english_value and getattr(row, english_attribute) != english_value:
            setattr(row, english_attribute, english_value)
            changed = True
    if item.name_en and row.name_en != item.name_en:
        row.name_en = item.name_en
        changed = True
    return changed


def _needs_translation():
    return or_(Board.name_en.is_(None), Board.name_en == "", and_(Board.description_kr.is_not(None), or_(Board.description_en.is_(None), Board.description_en == "")), and_(Board.address.is_not(None), or_(Board.address_en.is_(None), Board.address_en == "")), and_(Board.event_place.is_not(None), or_(Board.event_place_en.is_(None), Board.event_place_en == "")))


async def translate_missing_boards(db: AsyncSession, translator: BoardTranslator, limit: int) -> BoardTranslationResponse:
    async with _translation_lock:
        boards = list((await db.scalars(select(Board).where(_needs_translation()).order_by(Board.board_id).limit(limit))).all())
        try:
            batches = [boards[start:start + 20] for start in range(0, len(boards), 20)]
            translated_batches = await asyncio.gather(*(translator.translate(batch) for batch in batches))
            for batch, translations in zip(batches, translated_batches, strict=True):
                for board, translated in zip(batch, translations, strict=True):
                    board.name_en = translated.name_en
                    board.description_en = translated.description_en
                    board.address_en = translated.address_en
                    board.event_place_en = translated.event_place_en
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        remaining = await db.scalar(select(func.count(Board.board_id)).where(_needs_translation())) or 0
    return BoardTranslationResponse(requested_count=limit, translated_count=len(boards), remaining_count=remaining)


async def translate_missing_comments(db: AsyncSession, translator: CommentTranslator, limit: int) -> CommentTranslationResponse:
    missing_filter = and_(Comment.content_kr.is_not(None), or_(Comment.content_en.is_(None), Comment.content_en == ""))
    comments = list((await db.scalars(select(Comment).where(missing_filter).order_by(Comment.comment_id).limit(limit))).all())
    try:
        for start in range(0, len(comments), 5):
            batch = comments[start:start + 5]
            translations = await asyncio.gather(*(translator.translate(comment.content_kr or comment.content) for comment in batch))
            for comment, translated in zip(batch, translations, strict=True):
                comment.content_kr = translated.content_kr
                comment.content_en = translated.content_en
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    remaining = await db.scalar(select(func.count(Comment.comment_id)).where(missing_filter)) or 0
    return CommentTranslationResponse(requested_count=limit, translated_count=len(comments), remaining_count=remaining)


async def rebuild_faiss_index() -> FaissIndexResponse:
    bundle = await ensure_vector_store(force=True)
    return FaissIndexResponse(indexed_count=len(bundle.documents), fingerprint=bundle.fingerprint, embedding_model=settings.openai_embedding_model, rebuilt=bundle.rebuilt)


async def get_faiss_index_status() -> FaissIndexStatusResponse:
    current = await vector_store_status()
    return FaissIndexStatusResponse(ready=current.ready, stale=current.stale, document_count=current.document_count, indexed_count=current.indexed_count, fingerprint=current.fingerprint, embedding_model=current.embedding_model, built_at=current.built_at)
