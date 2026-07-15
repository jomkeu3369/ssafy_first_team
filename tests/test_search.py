import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.search.router import router
from src.core.database import get_db_session
from src.models import Base
from src.models.board import Board
from src.models.media import Media
from src.models.post import Post
from src.models.tag import Tag


async def _app_with_database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        board = Board(board_id=1, name="해운대 해수욕장", category="관광지", description="부산 대표 해변", image="https://example.com/board.jpg")
        post = Post(post_id=2, board_id=1, title="해운대 야경 후기", author="client", content="밤바다 산책", password="hash", view_count=0, like_count=0)
        tag = Tag(tag_id=9, name="후기")
        post.tags = [tag]
        session.add_all([board, post, Media(media_id=3, post_id=2, image_url="https://example.com/post.jpg", sequence=0)])
        await session.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    return app, engine


@pytest.mark.asyncio
async def test_integrated_search_returns_boards_posts_images_and_pagination() -> None:
    app, engine = await _app_with_database()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/search", params={"q": "해운대", "page": 1, "size": 20})
        paged = await client.get("/api/v1/search", params={"q": "해운대", "page": 2, "size": 1})
        invalid = await client.get("/api/v1/search", params={"q": ""})

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["items"] == [{"resultType": "BOARD", "resultId": 1, "boardId": 1, "title": "해운대 해수욕장", "description": "부산 대표 해변", "image": "https://example.com/board.jpg", "category": "관광지"}, {"resultType": "POST", "resultId": 2, "boardId": 1, "title": "해운대 야경 후기", "description": "밤바다 산책", "image": "https://example.com/post.jpg", "category": None}]
    assert paged.status_code == 200
    assert paged.json()["total"] == 2
    assert paged.json()["items"][0]["resultType"] == "POST"
    assert invalid.status_code == 422
    await engine.dispose()
