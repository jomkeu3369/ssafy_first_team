import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.database import engine, ensure_database_compatibility


def _column_names(sync_connection) -> set[str]:
    return {column["name"] for column in inspect(sync_connection).get_columns("Board")}


@pytest.mark.asyncio
async def test_sqlite_foreign_keys_are_enabled() -> None:
    async with engine.connect() as connection:
        enabled = await connection.scalar(text("PRAGMA foreign_keys"))

    assert enabled == 1


@pytest.mark.asyncio
async def test_database_compatibility_adds_board_image_column_once() -> None:
    target_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with target_engine.begin() as connection:
        await connection.execute(text('CREATE TABLE "Board" ("boardId" BIGINT PRIMARY KEY, name VARCHAR NOT NULL, category VARCHAR NOT NULL, description VARCHAR)'))

    assert await ensure_database_compatibility(target_engine) is True
    assert await ensure_database_compatibility(target_engine) is False

    async with target_engine.connect() as connection:
        columns = await connection.run_sync(_column_names)
    assert "image" in columns
    await target_engine.dispose()


@pytest.mark.asyncio
async def test_database_compatibility_skips_missing_board_table() -> None:
    target_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    assert await ensure_database_compatibility(target_engine) is False
    await target_engine.dispose()
