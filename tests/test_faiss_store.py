import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.mcp_servers import faiss_store
from src.models import Base
from src.models.board import Board
from src.models.post import Post


class FakeEmbeddings:
    calls = 0
    embedded_documents = 0

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self.api_key = api_key

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        FakeEmbeddings.calls += 1
        FakeEmbeddings.embedded_documents += len(texts)
        return [[float(position + 1), float(len(content) % 7 + 1)] for position, content in enumerate(texts)]


@pytest.mark.asyncio
async def test_faiss_store_builds_from_database_and_rebuilds_after_change(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    target_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with target_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(target_engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(Board(board_id=1, name="송도 해수욕장", category="관광지", description="바다 산책과 해상 케이블카", address="부산 서구", image="https://example.com/songdo.jpg"))
        session.add(Post(post_id=1, board_id=1, title="송도 가족 여행 후기", author="client", content="아이와 케이블카를 탔어요", password="hash", view_count=0, like_count=0))
        await session.commit()

    monkeypatch.setattr(faiss_store.settings, "openai_api_key", "openai-test")
    monkeypatch.setattr(faiss_store.settings, "openai_embedding_model", "embedding-test")
    monkeypatch.setattr(faiss_store.settings, "faiss_index_dir", tmp_path)
    monkeypatch.setattr(faiss_store, "_embeddings_class", lambda: FakeEmbeddings)
    monkeypatch.setattr(faiss_store, "_cached_bundle", None)
    monkeypatch.setattr(faiss_store, "_cached_embedding_model", None)
    FakeEmbeddings.calls = 0
    FakeEmbeddings.embedded_documents = 0

    first = await faiss_store.ensure_vector_store(target_engine=target_engine)
    reused = await faiss_store.ensure_vector_store(target_engine=target_engine)

    assert first.rebuilt is True
    assert reused.rebuilt is False
    assert reused.index is first.index
    assert first.index.ntotal == 2
    assert [item["metadata"]["source_type"] for item in first.documents] == ["Board", "post"]
    assert "바다 산책" in first.documents[0]["content"]
    assert FakeEmbeddings.calls == 1
    assert FakeEmbeddings.embedded_documents == 2
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["documentCount"] == 2
    ready = await faiss_store.vector_store_status(target_engine)
    assert ready.ready is True
    assert ready.stale is False
    assert ready.document_count == 2

    async with session_factory() as session:
        board = await session.get(Board, 1)
        board.description = "노을과 바다 산책이 좋은 관광지"
        await session.commit()

    rebuilt = await faiss_store.ensure_vector_store(target_engine=target_engine)

    assert rebuilt.rebuilt is True
    assert rebuilt.fingerprint != first.fingerprint
    assert "노을" in rebuilt.documents[0]["content"]
    assert FakeEmbeddings.calls == 2
    assert FakeEmbeddings.embedded_documents == 3
    await target_engine.dispose()
