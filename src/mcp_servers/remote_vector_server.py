from __future__ import annotations

import hmac
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.core.config import get_settings
from src.mcp_servers.local_search import search_faiss_index


settings = get_settings()
allowed_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
if settings.vector_mcp_public_host:
    allowed_hosts.append(settings.vector_mcp_public_host)
security = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=allowed_hosts, allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"])
mcp = FastMCP("remote-vector-search", host=settings.vector_mcp_host, port=settings.vector_mcp_port, stateless_http=True, json_response=True, transport_security=security)


@mcp.tool()
async def search_faiss(query: str, limit: int = 5) -> dict[str, Any]:
    """Semantically search synchronized LocalHub Board and post data."""
    return await search_faiss_index(query, limit)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "service": "vector-mcp"})


class BearerTokenMiddleware:
    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and str(scope.get("path", "")).rstrip("/") == "/mcp":
            headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
            expected = f"Bearer {self.token}"
            if not hmac.compare_digest(headers.get("authorization", ""), expected):
                response = JSONResponse({"message": "Unauthorized"}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app() -> ASGIApp:
    if not settings.vector_mcp_api_key:
        raise RuntimeError("VECTOR_MCP_API_KEY must be configured")
    return BearerTokenMiddleware(mcp.streamable_http_app(), settings.vector_mcp_api_key)


def run() -> None:
    uvicorn.run(create_app(), host=settings.vector_mcp_host, port=settings.vector_mcp_port, log_level=settings.log_level.lower(), workers=1)


if __name__ == "__main__":
    run()
