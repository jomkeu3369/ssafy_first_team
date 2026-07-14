import pytest
from sqlalchemy import text

from app.core.database import engine


@pytest.mark.asyncio
async def test_sqlite_foreign_keys_are_enabled() -> None:
    async with engine.connect() as connection:
        enabled = await connection.scalar(text("PRAGMA foreign_keys"))

    assert enabled == 1

    await engine.dispose()
