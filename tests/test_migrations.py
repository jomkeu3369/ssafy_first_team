from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.migrations import run_database_migrations
from src.models import Base


def _database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


def _columns(sync_connection, table: str) -> set[str]:
    return {column["name"] for column in inspect(sync_connection).get_columns(table)}


@pytest.mark.asyncio
async def test_migrations_create_new_database_to_head(tmp_path: Path) -> None:
    database_path = tmp_path / "new.db"
    database_url = _database_url(database_path)
    target_engine = create_async_engine(database_url)

    await run_database_migrations(database_url, target_engine, seed_path=None)

    async with target_engine.connect() as connection:
        version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        board_columns = await connection.run_sync(_columns, "Board")
        post_columns = await connection.run_sync(_columns, "post")
    assert version == "7c1b0a4d9e21"
    assert {"nameKr", "nameEn", "categoryKr", "categoryEn", "descriptionKr", "descriptionEn", "addressEn", "eventPlaceEn"} <= board_columns
    assert {"titleKr", "titleEn", "contentKr", "contentEn", "createdAt", "updatedAt"} <= post_columns
    await target_engine.dispose()


@pytest.mark.asyncio
async def test_migrations_stamp_legacy_database_without_deleting_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "existing.db"
    database_url = _database_url(database_path)
    target_engine = create_async_engine(database_url)
    async with target_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text('INSERT INTO "Board" ("boardId", name, "nameEn", category, description, "descriptionEn") VALUES (7, \'보존할 데이터\', \'보존할 데이터\', \'관광지\', \'주소: 부산\', \'Address: 부산\')'))

    await run_database_migrations(database_url, target_engine, seed_path=None)
    await run_database_migrations(database_url, target_engine, seed_path=None)

    async with target_engine.connect() as connection:
        version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        row = (await connection.execute(text('SELECT "boardId", name, "nameKr", "nameEn", "categoryKr", "categoryEn", "descriptionKr", "descriptionEn" FROM "Board"'))).one()
    assert version == "7c1b0a4d9e21"
    assert tuple(row) == (7, "보존할 데이터", "보존할 데이터", None, "관광지", "Attractions", "주소: 부산", None)
    await target_engine.dispose()


@pytest.mark.asyncio
async def test_first_persistent_disk_start_copies_seed_only_once(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.db"
    target_path = tmp_path / "persistent" / "localhub.db"
    seed_engine = create_async_engine(_database_url(seed_path))
    async with seed_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text('INSERT INTO "Board" ("boardId", name, category) VALUES (1, \'초기 데이터\', \'관광지\')'))
    await seed_engine.dispose()

    target_engine = create_async_engine(_database_url(target_path))
    await run_database_migrations(_database_url(target_path), target_engine, seed_path=seed_path)
    async with target_engine.begin() as connection:
        await connection.execute(text('UPDATE "Board" SET name = \'운영 데이터\' WHERE "boardId" = 1'))
    await run_database_migrations(_database_url(target_path), target_engine, seed_path=seed_path)

    async with target_engine.connect() as connection:
        name = await connection.scalar(text('SELECT name FROM "Board" WHERE "boardId" = 1'))
    assert name == "운영 데이터"
    await target_engine.dispose()
