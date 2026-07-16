import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "localhub.db"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.data_import.service import translate_missing_boards  # noqa: E402
from src.api.data_import.translation import BoardTranslator  # noqa: E402
from src.api.localization import BOARD_CATEGORY_EN, BOARD_CATEGORY_KR  # noqa: E402
from src.core.config import get_settings  # noqa: E402
from src.models.board import Board  # noqa: E402


REQUIRED_COLUMNS = {"boardId", "name", "nameKr", "nameEn", "category", "categoryKr", "categoryEn", "description", "descriptionKr", "descriptionEn", "address", "addressEn", "eventPlace", "eventPlaceEn"}


@dataclass(frozen=True, slots=True)
class TranslationSummary:
    translated_count: int
    remaining_count: int
    normalized_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Translate missing English fields directly in a local SQLite Board table.")
    parser.add_argument("--database-path", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--batch-limit", type=int, choices=range(1, 101), default=100, metavar="1-100")
    parser.add_argument("--max-records", type=int, default=0, help="Maximum records to translate. Use 0 for all records.")
    parser.add_argument("--no-backup", action="store_true", help="Skip the automatic SQLite backup.")
    return parser.parse_args()


def validate_database(database_path: Path) -> None:
    if not database_path.is_file():
        raise SystemExit(f"Database file was not found: {database_path}")
    with sqlite3.connect(database_path) as connection:
        table_exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'Board'").fetchone()
        if table_exists is None:
            raise SystemExit("The Board table does not exist. Apply the Alembic migrations first.")
        columns = {row[1] for row in connection.execute('PRAGMA table_info("Board")')}
    missing = sorted(REQUIRED_COLUMNS - columns)
    if missing:
        raise SystemExit(f"The Board table is missing translation columns: {', '.join(missing)}. Apply the Alembic migrations first.")


def backup_database(database_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = database_path.with_name(f"{database_path.stem}.backup-{timestamp}{database_path.suffix}")
    with sqlite3.connect(database_path) as source, sqlite3.connect(backup_path) as destination:
        source.backup(destination)
    return backup_path


async def normalize_board_fields(session) -> int:
    boards = list((await session.scalars(select(Board))).all())
    changed_count = 0
    for board in boards:
        changed = False
        values = (("name_kr", board.name), ("category_kr", BOARD_CATEGORY_KR.get(board.category, board.category)), ("category_en", BOARD_CATEGORY_EN.get(board.category, board.category)), ("description_kr", board.description))
        for attribute, value in values:
            if not getattr(board, attribute) and value:
                setattr(board, attribute, value)
                changed = True
        if changed:
            changed_count += 1
    if changed_count:
        await session.commit()
    return changed_count


async def translate_local_boards(database_path: Path, translator: BoardTranslator, batch_limit: int, max_records: int) -> TranslationSummary:
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    total_translated = 0
    remaining_count = 0
    normalized_count = 0
    try:
        async with session_factory() as session:
            normalized_count = await normalize_board_fields(session)
            while True:
                available = batch_limit if max_records == 0 else min(batch_limit, max_records - total_translated)
                if available <= 0:
                    break
                result = await translate_missing_boards(session, translator, available)
                total_translated += result.translated_count
                remaining_count = result.remaining_count
                print(f"Translated: {result.translated_count} / Remaining: {remaining_count} / Total: {total_translated}")
                if remaining_count == 0:
                    break
                if result.translated_count == 0:
                    raise RuntimeError("No progress was made. Check OPENAI_API_KEY, OPENAI_MODEL, and the source data.")
                if max_records and total_translated >= max_records:
                    break
    finally:
        await engine.dispose()
    return TranslationSummary(translated_count=total_translated, remaining_count=remaining_count, normalized_count=normalized_count)


async def run(args: argparse.Namespace) -> None:
    if args.max_records < 0:
        raise SystemExit("--max-records must be 0 or greater.")
    database_path = args.database_path.expanduser().resolve()
    validate_database(database_path)
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_model:
        raise SystemExit("OPENAI_API_KEY and OPENAI_MODEL must be configured in .env or environment variables.")
    if not args.no_backup:
        backup_path = backup_database(database_path)
        print(f"Backup: {backup_path}")
    summary = await translate_local_boards(database_path, BoardTranslator(settings), args.batch_limit, args.max_records)
    print(f"Board translation completed. Translated: {summary.translated_count} / Remaining: {summary.remaining_count} / Normalized: {summary.normalized_count}")


def main() -> None:
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        raise SystemExit("Translation was cancelled.") from None
    except Exception as exc:
        raise SystemExit(f"Local Board translation failed: {exc}") from exc


if __name__ == "__main__":
    main()
