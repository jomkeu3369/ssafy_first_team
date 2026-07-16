import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.database import engine, ensure_database_compatibility
from src.models import Base


def _column_names(sync_connection, table: str = "Board") -> set[str]:
    return {column["name"] for column in inspect(sync_connection).get_columns(table)}


@pytest.mark.asyncio
async def test_sqlite_foreign_keys_are_enabled() -> None:
    async with engine.connect() as connection:
        enabled = await connection.scalar(text("PRAGMA foreign_keys"))

    assert enabled == 1


@pytest.mark.asyncio
async def test_database_compatibility_adds_board_tourism_columns_once() -> None:
    target_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with target_engine.begin() as connection:
        await connection.execute(text('CREATE TABLE "Board" ("boardId" BIGINT PRIMARY KEY, name VARCHAR NOT NULL, category VARCHAR NOT NULL, description VARCHAR)'))

    assert await ensure_database_compatibility(target_engine) is True
    assert await ensure_database_compatibility(target_engine) is False

    async with target_engine.connect() as connection:
        columns = await connection.run_sync(_column_names)
    assert {"image", "contentId", "address", "eventStartDate", "eventEndDate", "eventPlace"} <= columns
    await target_engine.dispose()


@pytest.mark.asyncio
async def test_database_compatibility_skips_missing_board_table() -> None:
    target_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    assert await ensure_database_compatibility(target_engine) is False
    await target_engine.dispose()


@pytest.mark.asyncio
async def test_database_compatibility_adds_post_translation_columns_once() -> None:
    target_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with target_engine.begin() as connection:
        await connection.execute(text('CREATE TABLE post ("postId" BIGINT PRIMARY KEY, "boardId" BIGINT NOT NULL, title VARCHAR NOT NULL, author VARCHAR NOT NULL, content TEXT NOT NULL, password VARCHAR NOT NULL, "viewCount" INTEGER NOT NULL, "likeCount" INTEGER NOT NULL)'))

    assert await ensure_database_compatibility(target_engine) is True
    assert await ensure_database_compatibility(target_engine) is False
    async with target_engine.connect() as connection:
        columns = await connection.run_sync(_column_names, "post")
    assert {"titleKr", "titleEn", "contentKr", "contentEn"} <= columns
    await target_engine.dispose()


@pytest.mark.asyncio
async def test_database_compatibility_keeps_normal_sequence_gaps() -> None:
    target_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with target_engine.begin() as connection:
        await connection.execute(text('CREATE TABLE "Board" ("boardId" BIGINT PRIMARY KEY, name VARCHAR NOT NULL, category VARCHAR NOT NULL, description VARCHAR, image VARCHAR, "contentId" VARCHAR, address VARCHAR, "eventStartDate" VARCHAR, "eventEndDate" VARCHAR, "eventPlace" VARCHAR)'))
        await connection.execute(text('INSERT INTO "Board" ("boardId", name, category) VALUES (1, \'첫 번째\', \'FREE\'), (3, \'세 번째\', \'FREE\')'))

    assert await ensure_database_compatibility(target_engine) is False
    async with target_engine.connect() as connection:
        board_ids = list((await connection.execute(text('SELECT "boardId" FROM "Board" ORDER BY "boardId"'))).scalars())
    assert board_ids == [1, 3]
    await target_engine.dispose()


@pytest.mark.asyncio
async def test_database_compatibility_compacts_ids_and_preserves_relations() -> None:
    target_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with target_engine.begin() as connection:
        await connection.execute(text("PRAGMA foreign_keys=ON"))
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text('INSERT INTO "Board" ("boardId", name, category, description, image) VALUES (0, \'전체 자유게시판\', \'FREE\', NULL, NULL), (5376364174985097000, \'해운대\', \'관광지\', NULL, NULL)'))
        await connection.execute(text('INSERT INTO post ("postId", "boardId", title, author, content, password, "viewCount", "likeCount") VALUES (4376364174985097000, 5376364174985097000, \'후기\', \'client\', \'내용\', \'hash\', 0, 0)'))
        await connection.execute(text('INSERT INTO comment ("commentId", "postId", "parentId", author, content, password) VALUES (3376364174985097000, 4376364174985097000, NULL, \'client\', \'부모\', \'hash\'), (3376364174985097001, 4376364174985097000, 3376364174985097000, \'client\', \'자식\', \'hash\')'))
        await connection.execute(text('INSERT INTO media ("mediaId", "postId", "imageUrl", sequence) VALUES (2376364174985097000, 4376364174985097000, \'https://example.com/image.jpg\', 0)'))
        await connection.execute(text('INSERT INTO "Tag" ("tagId", name) VALUES (1, \'관광지\'), (1376364174985097000, \'야경\')'))
        await connection.execute(text('INSERT INTO "Post_Tags" ("postId", "tagId") VALUES (4376364174985097000, 1376364174985097000)'))
        await connection.execute(text('INSERT INTO "Post_Likes" ("postId", "clientId") VALUES (4376364174985097000, \'client-id\')'))

    assert await ensure_database_compatibility(target_engine) is True
    async with target_engine.connect() as connection:
        board_ids = list((await connection.execute(text('SELECT "boardId" FROM "Board" ORDER BY "boardId"'))).scalars())
        post_row = (await connection.execute(text('SELECT "postId", "boardId" FROM post'))).one()
        comment_rows = (await connection.execute(text('SELECT "commentId", "postId", "parentId" FROM comment ORDER BY "commentId"'))).all()
        media_row = (await connection.execute(text('SELECT "mediaId", "postId" FROM media'))).one()
        tag_ids = list((await connection.execute(text('SELECT "tagId" FROM "Tag" ORDER BY "tagId"'))).scalars())
        post_tag_row = (await connection.execute(text('SELECT "postId", "tagId" FROM "Post_Tags"'))).one()
        like_post_id = await connection.scalar(text('SELECT "postId" FROM "Post_Likes"'))

    assert board_ids == [0, 1]
    assert tuple(post_row) == (1, 1)
    assert [tuple(row) for row in comment_rows] == [(1, 1, None), (2, 1, 1)]
    assert tuple(media_row) == (1, 1)
    assert tag_ids == [1, 10]
    assert tuple(post_tag_row) == (1, 10)
    assert like_post_id == 1
    assert await ensure_database_compatibility(target_engine) is False
    await target_engine.dispose()
