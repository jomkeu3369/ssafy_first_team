import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.mcp_servers import sqlite_search


@pytest.mark.asyncio
async def test_sqlite_search_uses_real_board_and_post_table_names(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.execute(text('CREATE TABLE "Board" ("boardId" BIGINT PRIMARY KEY, name VARCHAR NOT NULL, category VARCHAR NOT NULL, description VARCHAR)'))
        await connection.execute(text('CREATE TABLE post ("postId" BIGINT PRIMARY KEY, title VARCHAR NOT NULL, content TEXT NOT NULL)'))
        await connection.execute(text('INSERT INTO "Board" ("boardId", name, category, description) VALUES (1, \'해운대 해수욕장\', \'관광지\', \'부산 해운대구 대표 해변\')'))
        await connection.execute(text('INSERT INTO post ("postId", title, content) VALUES (2, \'광안리 후기\', \'야경이 아름다웠습니다\')'))

    monkeypatch.setattr(sqlite_search, "engine", engine)
    boards = await sqlite_search.search_sqlite_database("해운대", content_type="regional_contents")
    posts = await sqlite_search.search_sqlite_database("야경", content_type="posts")

    assert boards["items"] == [{"sourceType": "Board", "sourceId": "1", "title": "해운대 해수욕장", "content": "부산 해운대구 대표 해변", "address": None, "imageUrl": None, "category": "관광지"}]
    assert posts["items"] == [{"sourceType": "post", "sourceId": "2", "title": "광안리 후기", "content": "야경이 아름다웠습니다", "address": None, "imageUrl": None, "category": None}]
    await engine.dispose()
