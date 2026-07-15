import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.board.crud import BoardAlreadyExistsError, create_board, get_board, get_boards
from src.api.board.router import router
from src.api.board.schema import BoardCreate, BoardResponse
from src.core.database import get_db_session
from src.models import Base
from src.models.board import Board
from src.models.media import Media
from src.models.post import Post


async def _database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_create_board_and_reject_duplicate() -> None:
    engine, session_factory = await _database()
    payload = BoardCreate(name="  테스트 게시판  ", category="HAEUNDAE", description="설명")

    async with session_factory() as session:
        board = await create_board(session, payload)
        assert 0 < board.board_id < 2**63
        assert board.name == "테스트 게시판"
        assert BoardResponse.model_validate(board).model_dump(by_alias=True)["boardId"] == board.board_id

    async with session_factory() as session:
        with pytest.raises(BoardAlreadyExistsError):
            await create_board(session, payload)

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_boards_and_detail_include_derived_fields() -> None:
    engine, session_factory = await _database()
    async with session_factory() as session:
        session.add_all([Board(board_id=0, name="전체 자유게시판", category="FREE"), Board(board_id=1, name="해운대 게시판", category="HAEUNDAE")])
        session.add_all([Post(post_id=10, board_id=1, title="이전 글", author="client", content="내용", password="hash", view_count=0, like_count=0), Post(post_id=11, board_id=1, title="최신 글", author="client", content="내용", password="hash", view_count=0, like_count=0)])
        session.add(Media(media_id=1, post_id=11, image_url="https://example.com/image.jpg", sequence=1))
        await session.commit()

        boards = await get_boards(session)
        detail = await get_board(session, 1)
        free_board = await get_board(session, 0)
        missing = await get_board(session, 999)

    assert len(boards) == 2
    assert detail is not None
    assert detail.recent_post_count == 2
    assert detail.recent_excerpt == "최신 글"
    assert detail.image == "https://example.com/image.jpg"
    assert detail.last_activity_at is None
    assert free_board is not None and free_board.board_id == 0
    assert missing is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_board_api_matches_spec() -> None:
    engine, session_factory = await _database()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    payload = {"name": "해운대 게시판", "category": "HAEUNDAE", "description": "설명"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/v1/boards", json=payload)
        duplicate = await client.post("/api/v1/boards", json=payload)
        listed = await client.get("/api/v1/boards")
        detail = await client.get(f"/api/v1/boards/{created.json()['boardId']}")
        missing = await client.get("/api/v1/boards/999")

    assert created.status_code == 201
    assert set(created.json()) == {"boardId", "name", "category", "description", "image", "recentPostCount", "lastActivityAt", "recentExcerpt"}
    assert duplicate.status_code == 409
    assert duplicate.json() == {"message": "같은 이름과 카테고리의 게시판이 이미 존재합니다."}
    assert listed.status_code == 200 and listed.json() == [created.json()]
    assert detail.status_code == 200 and detail.json() == created.json()
    assert missing.status_code == 404
    assert missing.json() == {"message": "게시판을 찾을 수 없습니다."}
    await engine.dispose()
