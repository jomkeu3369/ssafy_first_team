from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.comment.crud import DELETED_COMMENT_CONTENT
from src.api.comment.router import router
from src.api.comment.translation import TranslatedComment, get_comment_translator
from src.core.database import get_db_session
from src.models import Base
from src.models.board import Board
from src.models.comment import Comment
from src.models.post import Post


async def _app_with_database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(Board(board_id=1, name="자유 게시판", category="FREE"))
        session.add(Post(post_id=1, board_id=1, title="테스트", author=str(uuid4()), content="본문", password="unused", view_count=0, like_count=0))
        await session.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_session():
        async with session_factory() as session:
            yield session

    class FakeTranslator:
        async def translate(self, content: str) -> TranslatedComment:
            if any("가" <= character <= "힣" for character in content):
                return TranslatedComment(content_kr=content, content_en=f"EN: {content}")
            return TranslatedComment(content_kr=f"KR: {content}", content_en=content)

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_comment_translator] = FakeTranslator
    return app, engine, session_factory


@pytest.mark.asyncio
async def test_comment_api_builds_two_level_tree_and_uses_header_author() -> None:
    app, engine, session_factory = await _app_with_database()
    transport = ASGITransport(app=app)
    client_id = str(uuid4())
    headers = {"X-Client-Id": client_id}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        parent = await client.post("/api/v1/posts/1/comments", headers=headers, json={"content": "부모 댓글", "password": "1234", "author": str(uuid4())})
        parent_id = parent.json()["commentId"]
        child = await client.post("/api/v1/posts/1/comments", headers=headers, json={"parentId": parent_id, "content": "대댓글", "password": "5678"})
        child_id = child.json()["commentId"]
        too_deep = await client.post("/api/v1/posts/1/comments", headers=headers, json={"parentId": child_id, "content": "3단계", "password": "9999"})
        comments = await client.get("/api/v1/posts/1/comments")

    assert parent.status_code == 201
    assert parent_id == 1
    assert parent.json()["author"] == client_id
    assert parent.json()["contentKr"] == "부모 댓글"
    assert parent.json()["contentEn"] == "EN: 부모 댓글"
    assert "password" not in parent.json()
    assert child.status_code == 201
    assert child_id == 2
    assert too_deep.status_code == 400
    assert comments.status_code == 200
    assert comments.json()["total"] == 1
    assert comments.json()["items"][0]["children"][0]["commentId"] == child_id
    assert comments.json()["items"][0]["children"][0]["children"] == []

    async with session_factory() as session:
        stored = await session.get(Comment, parent_id)
        assert stored is not None and stored.password.startswith("scrypt$")
    await engine.dispose()


@pytest.mark.asyncio
async def test_comment_update_password_and_soft_delete_parent() -> None:
    app, engine, _session_factory = await _app_with_database()
    transport = ASGITransport(app=app)
    headers = {"X-Client-Id": str(uuid4())}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        parent = await client.post("/api/v1/posts/1/comments", headers=headers, json={"content": "원문", "password": "1234"})
        parent_id = parent.json()["commentId"]
        child = await client.post("/api/v1/posts/1/comments", headers=headers, json={"parentId": parent_id, "content": "답글", "password": "5678"})
        child_id = child.json()["commentId"]
        denied = await client.put(f"/api/v1/comments/{parent_id}", json={"content": "실패", "password": "0000"})
        updated = await client.put(f"/api/v1/comments/{parent_id}", json={"content": "수정", "password": "1234"})
        soft_deleted = await client.request("DELETE", f"/api/v1/comments/{parent_id}", json={"password": "1234"})
        after_soft_delete = await client.get("/api/v1/posts/1/comments")
        hard_deleted = await client.request("DELETE", f"/api/v1/comments/{child_id}", json={"password": "5678"})
        after_hard_delete = await client.get("/api/v1/posts/1/comments")

    assert denied.status_code == 401
    assert updated.status_code == 200 and updated.json()["content"] == "수정"
    assert updated.json()["contentKr"] == "수정"
    assert updated.json()["contentEn"] == "EN: 수정"
    assert soft_deleted.status_code == 204
    assert after_soft_delete.json()["items"][0]["content"] == DELETED_COMMENT_CONTENT
    assert after_soft_delete.json()["items"][0]["contentKr"] == DELETED_COMMENT_CONTENT
    assert after_soft_delete.json()["items"][0]["contentEn"] == "This comment has been deleted."
    assert after_soft_delete.json()["items"][0]["children"][0]["commentId"] == child_id
    assert hard_deleted.status_code == 204
    assert after_hard_delete.json()["items"][0]["children"] == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_comment_api_rejects_missing_post_and_parent() -> None:
    app, engine, _session_factory = await _app_with_database()
    transport = ASGITransport(app=app)
    headers = {"X-Client-Id": str(uuid4())}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing_post = await client.post("/api/v1/posts/999/comments", headers=headers, json={"content": "댓글", "password": "1234"})
        missing_parent = await client.post("/api/v1/posts/1/comments", headers=headers, json={"parentId": 999, "content": "댓글", "password": "1234"})

    assert missing_post.status_code == 404
    assert missing_parent.status_code == 404
    await engine.dispose()
