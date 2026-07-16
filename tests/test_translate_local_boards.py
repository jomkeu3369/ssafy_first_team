import sqlite3

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from scripts.translate_local_boards import backup_database, translate_local_boards, validate_database
from src.api.data_import.translation import TranslatedBoard
from src.models import Base
from src.models.board import Board


@pytest.mark.asyncio
async def test_translate_local_boards_updates_selected_records_and_creates_backup(tmp_path) -> None:
    database_path = tmp_path / "localhub.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        session.add_all([Board(board_id=1, name="첫 장소", category="관광지", description="첫 설명"), Board(board_id=2, name="둘째 장소", category="관광지", description="둘째 설명")])
        await session.commit()
    await engine.dispose()

    class FakeTranslator:
        async def translate(self, boards: list[Board]) -> list[TranslatedBoard]:
            return [TranslatedBoard(board_id=board.board_id, name_en=f"Place {board.board_id}", description_en=f"Description {board.board_id}", address_en=None, event_place_en=None) for board in boards]

    validate_database(database_path)
    backup_path = backup_database(database_path)
    summary = await translate_local_boards(database_path, FakeTranslator(), 100, 1)

    assert backup_path.is_file()
    assert summary.translated_count == 1
    assert summary.remaining_count == 1
    assert summary.normalized_count == 2
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute('SELECT "nameEn", "categoryEn" FROM "Board" ORDER BY "boardId"').fetchall()
    assert rows == [("Place 1", "Attractions"), (None, "Attractions")]
