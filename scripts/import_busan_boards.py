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

from src.core.database import AsyncSessionLocal
from src.models import Board


DEFAULT_SOURCE_DIR = Path.home() / "Desktop" / "data2" / "부산"
SOURCE_PATTERN = "부산_*.json"
MAX_DESCRIPTION_LENGTH = 1_000


@dataclass(frozen=True, slots=True)
class CleanBoard:
    name: str
    category: str
    description: str | None


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


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
            boards.append(
                CleanBoard(
                    name=name,
                    category=category,
                    description=build_description(item),
                )
            )

    return boards, skipped


async def import_boards(boards: list[CleanBoard], update_existing: bool) -> tuple[int, int, int]:
    async with AsyncSessionLocal() as session:
        try:
            existing_rows = (await session.scalars(select(Board))).all()
        except OperationalError as exc:
            raise RuntimeError(
                "Board table was not found. Run the manual migration before this script."
            ) from exc

        existing = {(row.name, row.category): row for row in existing_rows}
        next_id = (await session.scalar(select(func.max(Board.board_id))) or 0) + 1
        inserted = 0
        updated = 0
        unchanged = 0

        for item in boards:
            row = existing.get((item.name, item.category))
            if row is None:
                row = Board(
                    board_id=next_id,
                    name=item.name,
                    category=item.category,
                    description=item.description,
                )
                session.add(row)
                existing[(item.name, item.category)] = row
                next_id += 1
                inserted += 1
            elif update_existing and row.description != item.description:
                row.description = item.description
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
