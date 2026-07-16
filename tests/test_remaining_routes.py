import json
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.like.router import router as like_router
from src.api.media import router as media_router_module
from src.api.media.router import router as media_router
from src.api.realtime.manager import manager
from src.api.realtime.router import router as realtime_router
from src.api.tag.router import router as tag_router
from src.api.tourism.router import router as tourism_router
from src.api.tourism.service import get_festivals
from src.core.database import get_db_session
from src.models import Base
from src.models.board import Board
from src.models.post import Post
from src.models.tag import Tag


async def _database_app():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(Board(board_id=0, name="자유 게시판", category="FREE"))
        session.add(Post(post_id=0, board_id=0, title="게시글", author=str(uuid4()), content="본문", password="unused", view_count=0, like_count=0))
        session.add(Tag(tag_id=10, name="사용자 태그"))
        await session.commit()

    app = FastAPI()
    app.include_router(tag_router, prefix="/api/v1")
    app.include_router(like_router, prefix="/api/v1")

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    return app, engine


@pytest.mark.asyncio
async def test_tags_and_persistent_idempotent_likes() -> None:
    app, engine = await _database_app()
    transport = ASGITransport(app=app)
    first_headers = {"X-Client-Id": str(uuid4())}
    second_headers = {"X-Client-Id": str(uuid4())}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tags = await client.get("/api/v1/tags")
        created_tag = await client.post("/api/v1/tags", json={"name": "야경"})
        duplicate_tag = await client.post("/api/v1/tags", json={"name": "야경"})
        default_tag = await client.post("/api/v1/tags", json={"name": "관광지"})
        first = await client.post("/api/v1/posts/0/likes", headers=first_headers)
        duplicate = await client.post("/api/v1/posts/0/likes", headers=first_headers)
        second = await client.post("/api/v1/posts/0/likes", headers=second_headers)
        mine = await client.get("/api/v1/posts/0/likes/me", headers=first_headers)
        removed = await client.delete("/api/v1/posts/0/likes", headers=first_headers)

    assert tags.status_code == 200
    assert tags.json()["total"] == 10
    assert tags.json()["items"][0] == {"tagId": 1, "name": "관광지", "nameEn": "Attraction", "category": "ATTRACTION"}
    assert tags.json()["items"][-1] == {"tagId": 10, "name": "사용자 태그", "nameEn": "사용자 태그", "category": "CUSTOM"}
    assert created_tag.status_code == 201
    assert created_tag.json() == {"tagId": 11, "name": "야경", "nameEn": "야경", "category": "CUSTOM"}
    assert duplicate_tag.status_code == 409
    assert default_tag.status_code == 409
    assert first.json() == {"liked": True, "likeCount": 1}
    assert duplicate.json() == {"liked": True, "likeCount": 1}
    assert second.json() == {"liked": True, "likeCount": 2}
    assert mine.json() == {"liked": True, "likeCount": 2}
    assert removed.json() == {"liked": False, "likeCount": 1}
    await engine.dispose()


@pytest.mark.asyncio
async def test_media_upload_validates_and_saves_image(tmp_path: Path) -> None:
    original_media_dir = media_router_module.settings.media_dir
    media_router_module.settings.media_dir = tmp_path
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(media_router, prefix="/api/v1")

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    png = b"\x89PNG\r\n\x1a\n" + b"image-data"

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            uploaded = await client.post("/api/v1/media", files={"file": ("sample.png", png, "image/png")})
            second = await client.post("/api/v1/media", files={"file": ("second.png", png, "image/png")})
            invalid = await client.post("/api/v1/media", files={"file": ("fake.png", b"not-image", "image/png")})
    finally:
        media_router_module.settings.media_dir = original_media_dir

    assert uploaded.status_code == 201
    assert uploaded.json()["mediaId"] == 1
    assert uploaded.json()["imageUrl"].startswith("http://test/media/")
    assert second.json()["mediaId"] == 2
    assert len(list(tmp_path.glob("*.png"))) == 2
    assert invalid.status_code == 400
    await engine.dispose()


def _write_tourism_files(data_dir: Path) -> None:
    attraction = {"items": [{"contentid": "place-1", "title": "송도 해수욕장", "addr1": "부산 서구", "firstimage": "https://example.com/place.jpg"}]}
    festival = {"items": [{"contentid": "festival-1", "title": "부산 테스트 축제", "eventplace": "광안리", "eventstartdate": "20260701", "eventenddate": "20260731", "firstimage": "https://example.com/festival.jpg"}]}
    (data_dir / "부산_관광지.json").write_text(json.dumps(attraction, ensure_ascii=False), encoding="utf-8")
    (data_dir / "부산_축제공연행사.json").write_text(json.dumps(festival, ensure_ascii=False), encoding="utf-8")


@pytest.mark.asyncio
async def test_tourism_list_detail_and_date_status(tmp_path: Path) -> None:
    _write_tourism_files(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all([Board(board_id=1, name="송도 해수욕장", name_en="Songdo Beach", category="관광지", source_content_id="place-1", address="부산 서구", address_en="Seo-gu, Busan", image="https://example.com/place.jpg"), Board(board_id=2, name="부산 테스트 축제", name_en="Busan Test Festival", category="축제공연행사", source_content_id="festival-1", event_place="광안리", event_place_en="Gwangalli Beach", event_start_date="20260701", event_end_date="20260731", image="https://example.com/festival.jpg")])
        await session.commit()
    app = FastAPI()
    app.include_router(tourism_router, prefix="/api/v1")

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        attractions = await client.get("/api/v1/tourism/attractions")
        attraction = await client.get("/api/v1/tourism/attractions/place-1")
        festival = await client.get("/api/v1/tourism/festivals/festival-1")
        missing = await client.get("/api/v1/tourism/attractions/missing")

    assert attractions.status_code == 200
    assert attractions.json()["total"] == 1
    assert attractions.json()["items"][0]["category"] == "BEACH"
    assert attractions.json()["items"][0]["boardId"] == 1
    assert attractions.json()["items"][0]["nameEn"] == "Songdo Beach"
    assert attractions.json()["items"][0]["addressEn"] == "Seo-gu, Busan"
    assert attraction.json()["contentId"] == "place-1"
    assert attraction.json()["boardId"] == 1
    assert festival.json()["startDate"] == "2026-07-01"
    assert festival.json()["boardId"] == 2
    assert festival.json()["summaryEn"].endswith("in Busan.")
    assert missing.status_code == 404
    assert get_festivals(tmp_path, today=date(2026, 7, 15))[0].status == "ONGOING"
    await engine.dispose()


def test_websocket_counts_unique_clients_with_camel_case() -> None:
    app = FastAPI()
    app.include_router(realtime_router, prefix="/api/v1")
    client_id = str(uuid4())

    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/ws?clientId={client_id}") as first:
            assert first.receive_json() == {"event": "presence.updated", "data": {"connectedCount": 1}}
            with client.websocket_connect(f"/api/v1/ws?clientId={client_id}") as second:
                assert first.receive_json() == {"event": "presence.updated", "data": {"connectedCount": 1}}
                assert second.receive_json() == {"event": "presence.updated", "data": {"connectedCount": 1}}
                manager_event = {"event": "post.created", "data": {"postId": 1, "boardId": 0, "title": "새 게시글", "createdAt": "2026-07-16T12:00:00+09:00"}}
                client.portal.call(manager.broadcast, manager_event)
                assert first.receive_json() == manager_event
                assert second.receive_json() == manager_event
            assert first.receive_json() == {"event": "presence.updated", "data": {"connectedCount": 1}}
            with client.websocket_connect(f"/api/v1/ws?clientId={uuid4()}") as third:
                assert first.receive_json() == {"event": "presence.updated", "data": {"connectedCount": 2}}
                assert third.receive_json() == {"event": "presence.updated", "data": {"connectedCount": 2}}

    assert manager.connected_count == 0
