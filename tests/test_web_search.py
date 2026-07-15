import pytest

from src.mcp_servers import tavily_search


class FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"answer": "검색 요약", "results": [{"title": "공식 자료", "url": "https://example.com", "content": "검색 내용"}]}


class FakeClient:
    def __init__(self, timeout: float):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def post(self, url: str, *, headers: dict, json: dict) -> FakeResponse:
        assert url == tavily_search.TAVILY_SEARCH_URL
        assert headers["Authorization"] == "Bearer tvly-test"
        assert json["max_results"] == 5
        assert json["include_answer"] == "basic"
        return FakeResponse()


@pytest.mark.asyncio
async def test_tavily_search_returns_existing_mcp_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tavily_search.settings, "tavily_api_key", "tvly-test")
    monkeypatch.setattr(tavily_search.httpx, "AsyncClient", FakeClient)

    result = await tavily_search.search_tavily_web("부산 축제", limit=20)

    assert result == {"answer": "검색 요약", "citations": [{"title": "공식 자료", "url": "https://example.com"}]}


@pytest.mark.asyncio
async def test_tavily_search_reports_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tavily_search.settings, "tavily_api_key", None)

    result = await tavily_search.search_tavily_web("부산 축제")

    assert result["answer"] == ""
    assert result["citations"] == []
    assert result["notice"] == "TAVILY_API_KEY is not configured."
