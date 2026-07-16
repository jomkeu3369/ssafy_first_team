import hashlib
import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, Request, Response
from langchain_mcp_adapters.client import MultiServerMCPClient
from starlette.responses import JSONResponse

from src.mcp_servers import faiss_store
from src.mcp_servers import remote_vector_server
from src.mcp_servers.remote_vector_server import BearerTokenMiddleware


@pytest.mark.asyncio
async def test_bearer_middleware_protects_only_mcp_endpoint() -> None:
    async def downstream(scope, receive, send):
        response = JSONResponse({"ok": True})
        await response(scope, receive, send)

    transport = ASGITransport(app=BearerTokenMiddleware(downstream, "mcp-secret"))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post("/mcp/")
        allowed = await client.post("/mcp", headers={"Authorization": "Bearer mcp-secret"})
        health = await client.get("/health")

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert health.status_code == 200


@pytest.mark.asyncio
async def test_streamable_http_server_exposes_vector_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(remote_vector_server.settings, "vector_mcp_api_key", "mcp-secret")
    app = remote_vector_server.create_app()

    def client_factory(headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=ASGITransport(app=app), headers=headers, timeout=timeout, auth=auth)

    connection = {"transport": "streamable_http", "url": "http://localhost:8001/mcp", "headers": {"Authorization": "Bearer mcp-secret", "Host": "localhost:8001"}, "httpx_client_factory": client_factory}
    client = MultiServerMCPClient({"vector": connection})
    async with app.app.router.lifespan_context(app.app):
        tools = await client.get_tools(server_name="vector")

    assert [tool.name for tool in tools] == ["search_faiss"]


@pytest.mark.asyncio
async def test_remote_documents_are_authenticated_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    documents = [{"content": "Busan beach", "metadata": {"source_type": "Board", "source_id": "1"}}]
    serialized = json.dumps(documents, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
    requests: list[Request] = []
    async_client_class = httpx.AsyncClient

    def handler(request: Request) -> Response:
        requests.append(request)
        return Response(200, json={"documents": documents, "fingerprint": fingerprint})

    def client_factory(timeout: float) -> httpx.AsyncClient:
        return async_client_class(transport=httpx.MockTransport(handler), timeout=timeout)

    monkeypatch.setattr(faiss_store.settings, "vector_source_url", "https://render.example.com/search-documents")
    monkeypatch.setattr(faiss_store.settings, "vector_source_api_key", "sync-secret")
    monkeypatch.setattr(faiss_store.settings, "vector_source_cache_seconds", 300)
    monkeypatch.setattr(faiss_store.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(faiss_store, "_remote_source_cache", None)

    first = await faiss_store.load_remote_search_documents()
    second = await faiss_store.load_remote_search_documents()

    assert first == second == (documents, fingerprint)
    assert len(requests) == 1
    assert requests[0].headers["X-MCP-Sync-Key"] == "sync-secret"
