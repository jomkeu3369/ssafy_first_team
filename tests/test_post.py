from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.post.passwords import hash_password, verify_password
from src.api.post.router import router
from src.core.database import get_db_session
from src.models import Base
from src.models.board import Board
from src.models.post import Post


async def _app_with_database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(Board(board_id=0, name="전체 자유게시판", category="FREE"))
        await session.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    return app, engine, session_factory


def test_password_hash_is_salted_and_verifiable() -> None:
    first = hash_password("1234")
    second = hash_password("1234")
    assert first != second
    assert first.startswith("scrypt$")
    assert verify_password("1234", first)
    assert not verify_password("9999", first)


@pytest.mark.asyncio
async def test_post_api_crud_search_view_and_password_verify() -> None:
    app, engine, session_factory = await _app_with_database()
    transport = ASGITransport(app=app)
    client_id = str(uuid4())
    spoofed_author = str(uuid4())
    headers = {"X-Client-Id": client_id}
    create_payload = {"title": "해운대 야경", "content": "달맞이길 전망대 후기", "password": "1234", "author": spoofed_author, "tags": [{"tagId": 1, "name": "관광지", "category": "ATTRACTION"}], "media": [{"mediaId": 12, "imageUrl": "https://example.com/night.jpg"}]}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/v1/boards/0/posts", headers=headers, json=create_payload)
        post_id = created.json()["postId"]
        detail = await client.get(f"/api/v1/posts/{post_id}", headers=headers)
        duplicate_view = await client.get(f"/api/v1/posts/{post_id}", headers=headers)
        searched = await client.get("/api/v1/boards/0/posts", params={"keyword": "관광지", "sort": "latest", "page": 1, "size": 10})
        verified = await client.post(f"/api/v1/posts/{post_id}/password/verify", headers=headers, json={"password": "1234"})
        denied = await client.put(f"/api/v1/posts/{post_id}", json={**create_payload, "title": "실패", "password": "9999"})
        updated = await client.put(f"/api/v1/posts/{post_id}", json={**create_payload, "title": "수정된 제목"})
        wrong_delete = await client.request("DELETE", f"/api/v1/posts/{post_id}", json={"password": "9999"})
        deleted = await client.request("DELETE", f"/api/v1/posts/{post_id}", json={"password": "1234"})
        missing = await client.get(f"/api/v1/posts/{post_id}", headers=headers)

    assert created.status_code == 201
    assert created.json()["author"] == client_id
    assert "password" not in created.json()
    assert created.json()["tags"] == [{"tagId": 1, "name": "관광지", "category": "ATTRACTION"}]
    assert created.json()["media"] == [{"mediaId": 12, "imageUrl": "https://example.com/night.jpg"}]
    assert detail.status_code == 200 and detail.json()["viewCount"] == 1
    assert duplicate_view.json()["viewCount"] == 1
    assert searched.status_code == 200
    assert searched.json()["total"] == 1
    assert searched.json()["items"][0]["postId"] == post_id
    assert verified.status_code == 200 and verified.json() == {"verified": True}
    assert denied.status_code == 401 and denied.json() == {"message": "비밀번호가 일치하지 않습니다."}
    assert updated.status_code == 200 and updated.json()["title"] == "수정된 제목"
    assert wrong_delete.status_code == 401
    assert deleted.status_code == 204
    assert missing.status_code == 404 and missing.json() == {"message": "게시글을 찾을 수 없습니다."}

    async with session_factory() as session:
        assert await session.get(Post, post_id) is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_post_api_rejects_missing_board_and_bad_tag_category() -> None:
    app, engine, _session_factory = await _app_with_database()
    transport = ASGITransport(app=app)
    headers = {"X-Client-Id": str(uuid4())}
    payload = {"title": "제목", "content": "내용", "password": "1234", "tags": [{"tagId": 1, "name": "관광지", "category": "WRONG"}], "media": []}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing_board = await client.post("/api/v1/boards/999/posts", headers=headers, json=payload)
        bad_tag = await client.post("/api/v1/boards/0/posts", headers=headers, json=payload)

    assert missing_board.status_code == 404
    assert bad_tag.status_code == 400
    assert bad_tag.json() == {"message": "태그 정보가 올바르지 않습니다."}
    await engine.dispose()
