import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.data_import import router as router_module
from src.api.data_import import service as import_service
from src.api.data_import.router import router
from src.api.data_import.translation import TranslatedBoard, get_board_translator
from src.api.tourism.router import router as tourism_router
from src.core.database import get_db_session
from src.models import Base
from src.models.board import Board


async def _app_with_database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(tourism_router, prefix="/api/v1")

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    return app, engine, session_factory


def _upload(name: str, category: str, address: str, image: str = "https://example.com/image.jpg", content_id: str = "content-1", event_start_date: str = "", event_end_date: str = "", event_place: str = "") -> tuple[str, tuple[str, bytes, str]]:
    payload = {"contentType": category, "items": [{"title": name, "addr1": address, "firstimage": image, "contentid": content_id, "eventstartdate": event_start_date, "eventenddate": event_end_date, "eventplace": event_place}, {"title": name, "addr1": address}, {"title": ""}]}
    return "files", (f"부산_{category}.json", json.dumps(payload, ensure_ascii=False).encode(), "application/json")


def test_import_openapi_exposes_multiple_binary_files() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    specification = app.openapi()
    operation = specification["paths"]["/api/v1/admin/data-import/boards"]["post"]
    request_schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    schema_name = request_schema["$ref"].rsplit("/", 1)[-1]
    files_schema = specification["components"]["schemas"][schema_name]["properties"]["files"]

    assert files_schema["type"] == "array"
    assert files_schema["items"] == {"type": "string", "format": "binary"}


@pytest.mark.asyncio
async def test_protected_import_inserts_updates_and_skips_duplicates() -> None:
    app, engine, session_factory = await _app_with_database()
    original_key = router_module.settings.data_import_api_key
    router_module.settings.data_import_api_key = "test-import-secret"
    transport = ASGITransport(app=app)
    headers = {"X-Import-Key": "test-import-secret"}
    files = [_upload("해운대 해수욕장", "관광지", "부산 해운대구", content_id="place-1"), _upload("부산 불꽃축제", "축제공연행사", "부산 수영구", content_id="festival-1", event_start_date="20261001", event_end_date="20261010", event_place="광안리")]

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            denied = await client.post("/api/v1/admin/data-import/boards", files=files)
            inserted = await client.post("/api/v1/admin/data-import/boards", headers=headers, files=files)
            unchanged = await client.post("/api/v1/admin/data-import/boards", headers=headers, files=files)
            updated = await client.post("/api/v1/admin/data-import/boards", headers=headers, params={"updateExisting": "true"}, files=[_upload("해운대 해수욕장", "관광지", "부산 해운대구 우동", "https://example.com/updated.jpg", "place-1")])
            festivals = await client.get("/api/v1/tourism/festivals")
            festival_detail = await client.get("/api/v1/tourism/festivals/festival-1")
    finally:
        router_module.settings.data_import_api_key = original_key

    assert denied.status_code == 401
    assert inserted.status_code == 200
    assert inserted.json() == {"sourceCount": 2, "insertedCount": 2, "updatedCount": 0, "unchangedCount": 0, "skippedCount": 4, "categories": {"관광지": 1, "축제공연행사": 1}}
    assert unchanged.json()["insertedCount"] == 0
    assert unchanged.json()["unchangedCount"] == 2
    assert updated.json()["updatedCount"] == 1
    assert festivals.json()["total"] == 1
    assert festivals.json()["items"][0]["contentId"] == "festival-1"
    assert festival_detail.json()["boardId"] == 2
    assert festival_detail.json()["startDate"] == "2026-10-01"

    async with session_factory() as session:
        assert await session.scalar(select(func.count(Board.board_id))) == 2
        assert list((await session.scalars(select(Board.board_id).order_by(Board.board_id))).all()) == [1, 2]
        board = (await session.scalars(select(Board).where(Board.name == "해운대 해수욕장"))).one()
        assert board.description == "주소: 부산 해운대구 우동"
        assert board.name_kr == "해운대 해수욕장"
        assert board.category_kr == "관광지"
        assert board.category_en == "Attractions"
        assert board.description_kr == "주소: 부산 해운대구 우동"
        assert board.image == "https://example.com/updated.jpg"
        assert board.source_content_id == "place-1"
        assert board.address == "부산 해운대구 우동"
        festival = (await session.scalars(select(Board).where(Board.name == "부산 불꽃축제"))).one()
        assert festival.event_start_date == "20261001"
        assert festival.event_end_date == "20261010"
        assert festival.event_place == "광안리"
    await engine.dispose()


@pytest.mark.asyncio
async def test_import_rejects_unknown_content_type() -> None:
    app, engine, _session_factory = await _app_with_database()
    original_key = router_module.settings.data_import_api_key
    router_module.settings.data_import_api_key = "test-import-secret"
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/admin/data-import/boards", headers={"X-Import-Key": "test-import-secret"}, files=[_upload("잘못된 데이터", "UNKNOWN", "부산")])
    finally:
        router_module.settings.data_import_api_key = original_key

    assert response.status_code == 400
    assert response.json() == {"message": "부산 관광 JSON 형식이 올바르지 않습니다."}
    await engine.dispose()


@pytest.mark.asyncio
async def test_board_translation_backfill_persists_real_english_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    app, engine, session_factory = await _app_with_database()

    class FakeTranslator:
        async def translate(self, boards: list[Board]) -> list[TranslatedBoard]:
            names = {"해운대 해수욕장": "Haeundae Beach", "부산 불꽃축제": "Busan Fireworks Festival"}
            return [TranslatedBoard(board_id=board.board_id, name_en=names[board.name], description_en="English description", address_en="Busan, South Korea", event_place_en="Gwangalli Beach" if board.event_place else None) for board in boards]

    app.dependency_overrides[get_board_translator] = FakeTranslator
    monkeypatch.setattr(router_module.settings, "data_import_api_key", "test-import-secret")
    monkeypatch.setattr(router_module.settings, "openai_api_key", "openai-test")
    headers = {"X-Import-Key": "test-import-secret"}
    files = [_upload("해운대 해수욕장", "관광지", "부산 해운대구", content_id="place-1"), _upload("부산 불꽃축제", "축제공연행사", "부산 수영구", content_id="festival-1", event_place="광안리")]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/admin/data-import/boards", headers=headers, files=files)
        before = await client.get("/api/v1/tourism/festivals/festival-1")
        translated = await client.post("/api/v1/admin/data-import/board-translations", headers=headers, params={"limit": 100})
        attraction = await client.get("/api/v1/tourism/attractions/place-1")
        festival = await client.get("/api/v1/tourism/festivals/festival-1")

    assert before.json()["nameEn"] == ""
    assert before.json()["placeEn"] == ""
    assert translated.status_code == 200
    assert translated.json() == {"requestedCount": 100, "translatedCount": 2, "remainingCount": 0}
    assert attraction.json()["nameEn"] == "Haeundae Beach"
    assert attraction.json()["addressEn"] == "Busan, South Korea"
    assert festival.json()["nameEn"] == "Busan Fireworks Festival"
    assert festival.json()["placeEn"] == "Gwangalli Beach"
    assert all(not any("가" <= character <= "힣" for character in value) for value in (festival.json()["nameEn"], festival.json()["placeEn"], festival.json()["summaryEn"]))
    async with session_factory() as session:
        board = (await session.scalars(select(Board).where(Board.name == "부산 불꽃축제"))).one()
        assert board.name_en == "Busan Fireworks Festival"
        assert board.event_place_en == "Gwangalli Beach"
    await engine.dispose()


@pytest.mark.asyncio
async def test_protected_faiss_rebuild_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    app, engine, _session_factory = await _app_with_database()
    monkeypatch.setattr(router_module.settings, "data_import_api_key", "test-import-secret")
    monkeypatch.setattr(router_module.settings, "openai_api_key", "openai-test")

    async def fake_rebuild():
        return SimpleNamespace(indexed_count=1755, fingerprint="fingerprint", embedding_model="embedding-test", rebuilt=True)

    async def fake_status():
        return SimpleNamespace(ready=True, stale=False, document_count=1755, indexed_count=1755, fingerprint="fingerprint", embedding_model="embedding-test", built_at="2026-07-15T00:00:00+00:00")

    monkeypatch.setattr(import_service, "rebuild_faiss_index", fake_rebuild)
    monkeypatch.setattr(import_service, "get_faiss_index_status", fake_status)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post("/api/v1/admin/data-import/faiss")
        rebuilt = await client.post("/api/v1/admin/data-import/faiss", headers={"X-Import-Key": "test-import-secret"})
        current = await client.get("/api/v1/admin/data-import/faiss", headers={"X-Import-Key": "test-import-secret"})

    assert denied.status_code == 401
    assert rebuilt.status_code == 200
    assert rebuilt.json() == {"indexedCount": 1755, "fingerprint": "fingerprint", "embeddingModel": "embedding-test", "rebuilt": True}
    assert current.json()["ready"] is True
    assert current.json()["stale"] is False
    assert current.json()["documentCount"] == 1755
    await engine.dispose()
