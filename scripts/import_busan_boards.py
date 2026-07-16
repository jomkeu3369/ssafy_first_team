from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from src.api.localization import BOARD_CATEGORY_EN
from src.core.database import AsyncSessionLocal
from src.core.ids import MAX_PUBLIC_ID
from src.models import Board


DEFAULT_SOURCE_DIR = Path.home() / "Desktop" / "data2" / "부산"
SOURCE_PATTERN = "부산_*.json"
MAX_DESCRIPTION_LENGTH = 1_000


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


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def english_text(value: Any, limit: int) -> str | None:
    cleaned = clean_text(value)[:limit]
    if not cleaned or re.search(r"[\uac00-\ud7a3]", cleaned):
        return None
    return cleaned


def build_description(item: dict[str, Any]) -> str | None:
    address = " ".join(
        value for value in (clean_text(item.get("addr1")), clean_text(item.get("addr2"))) if value
    )
    start_date = clean_text(item.get("eventstartdate"))
    end_date = clean_text(item.get("eventenddate"))
    event_dates = " ~ ".join(value for value in (start_date, end_date) if value)

    fields = (
        ("주소", address),
        ("전화", clean_text(item.get("tel"))),
        ("우편번호", clean_text(item.get("zipcode"))),
        ("행사기간", event_dates),
        ("행사장소", clean_text(item.get("eventplace"))),
        ("이용시간", clean_text(item.get("playtime"))),
    )
    description = " | ".join(f"{label}: {value}" for label, value in fields if value)
    return description[:MAX_DESCRIPTION_LENGTH] or None


def load_boards(source_paths: list[Path]) -> tuple[list[CleanBoard], int]:
    boards: list[CleanBoard] = []
    seen: set[tuple[str, str]] = set()
    skipped = 0

    for source_path in source_paths:
        with source_path.open(encoding="utf-8-sig") as file:
            payload = json.load(file)

        category = clean_text(payload.get("contentType"))
        items = payload.get("items")
        if not category or not isinstance(items, list):
            raise ValueError(
                f"Invalid source format: {source_path} "
                "(contentType and items[] are required)"
            )

        for item in items:
            if not isinstance(item, dict):
                skipped += 1
                continue
            name = clean_text(item.get("title"))
            key = (name, category)
            if not name or key in seen:
                skipped += 1
                continue
            seen.add(key)
            address = " ".join(value for value in (clean_text(item.get("addr1")), clean_text(item.get("addr2"))) if value)[:500] or None
            address_en = " ".join(value for value in (english_text(item.get("addr1En") or item.get("addr1_en"), 800), english_text(item.get("addr2En") or item.get("addr2_en"), 200)) if value)[:1000] or None
            boards.append(
                CleanBoard(
                    name=name,
                    name_en=english_text(item.get("titleEn") or item.get("title_en") or item.get("engtitle"), 200),
                    category=category,
                    description=build_description(item),
                    description_en=english_text(item.get("descriptionEn") or item.get("description_en") or item.get("overviewEn"), 2000),
                    image=clean_text(item.get("firstimage") or item.get("firstimage2"))[:2000] or None,
                    source_content_id=clean_text(item.get("contentid"))[:100] or None,
                    address=address,
                    address_en=address_en,
                    event_start_date=clean_text(item.get("eventstartdate"))[:8] or None,
                    event_end_date=clean_text(item.get("eventenddate"))[:8] or None,
                    event_place=clean_text(item.get("eventplace"))[:500] or None,
                    event_place_en=english_text(item.get("eventplaceEn") or item.get("eventplace_en"), 1000)
                )
            )

    return boards, skipped


def update_board(row: Board, item: CleanBoard) -> bool:
    changed = False
    localized_values = (("name_kr", item.name), ("category_kr", item.category), ("category_en", BOARD_CATEGORY_EN.get(item.category, item.category)), ("description_kr", item.description))
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


async def import_boards(boards: list[CleanBoard], update_existing: bool) -> tuple[int, int, int]:
    async with AsyncSessionLocal() as session:
        try:
            existing_rows = (await session.scalars(select(Board))).all()
        except OperationalError as exc:
            raise RuntimeError(
                "Board table was not found. Run the manual migration before this script."
            ) from exc

        existing = {(row.name, row.category): row for row in existing_rows}
        next_id = (await session.scalar(select(func.max(Board.board_id)).where(Board.board_id > 0, Board.board_id <= MAX_PUBLIC_ID)) or 0) + 1
        inserted = 0
        updated = 0
        unchanged = 0

        for item in boards:
            row = existing.get((item.name, item.category))
            if row is None:
                row = Board(
                    board_id=next_id,
                    name=item.name,
                    name_kr=item.name,
                    name_en=item.name_en,
                    category=item.category,
                    category_kr=item.category,
                    category_en=BOARD_CATEGORY_EN.get(item.category, item.category),
                    description=item.description,
                    description_kr=item.description,
                    description_en=item.description_en,
                    image=item.image,
                    source_content_id=item.source_content_id,
                    address=item.address,
                    address_en=item.address_en,
                    event_start_date=item.event_start_date,
                    event_end_date=item.event_end_date,
                    event_place=item.event_place,
                    event_place_en=item.event_place_en
                )
                session.add(row)
                existing[(item.name, item.category)] = row
                next_id += 1
                inserted += 1
            elif update_existing and update_board(row, item):
                updated += 1
            else:
                unchanged += 1

        await session.commit()
        return inserted, updated, unchanged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean 부산 tourism JSON files and import them into Board."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=f"JSON directory (default: {DEFAULT_SOURCE_DIR})",
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Update descriptions for rows with the same name and category.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and summarize JSON files without writing to the database.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_paths = sorted(args.source_dir.glob(SOURCE_PATTERN))
    if not source_paths:
        raise FileNotFoundError(
            f"No files matching {SOURCE_PATTERN!r} were found in {args.source_dir}"
        )

    boards, skipped = load_boards(source_paths)
    categories: dict[str, int] = {}
    for board in boards:
        categories[board.category] = categories.get(board.category, 0) + 1

    print(f"Sources: {len(source_paths)} files")
    print(f"Clean rows: {len(boards)}, skipped/duplicate rows: {skipped}")
    print("Categories: " + ", ".join(f"{name}={count}" for name, count in categories.items()))
    if args.dry_run:
        print("Dry run completed; the database was not changed.")
        return

    inserted, updated, unchanged = asyncio.run(
        import_boards(boards, update_existing=args.update_existing)
    )
    print(f"Committed: inserted={inserted}, updated={updated}, unchanged={unchanged}")


if __name__ == "__main__":
    main()
