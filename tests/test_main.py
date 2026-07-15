from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from main import app
from src.agent.service import AgentService


@pytest.fixture(autouse=True)
def disable_real_agent_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def skip_start(_service: AgentService) -> None:
        return None

    monkeypatch.setattr(AgentService, "start", skip_start)


def test_health_and_documentation_settings() -> None:
    with TestClient(app) as client:
        health_response = client.get("/health")
        docs_response = client.get("/docs")
        redoc_response = client.get("/redoc")

    assert health_response.status_code == 200
    assert health_response.json() == {
        "status": "healthy",
        "database": "connected",
    }
    assert docs_response.status_code == 200
    assert redoc_response.status_code == 404


def test_cors_preflight() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Client-Id",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ("http://localhost:5173")


def test_chat_is_unavailable_without_agent_configuration() -> None:
    with TestClient(app) as client:
        client.app.state.agent_service = None
        response = client.post("/api/v1/chat", headers={"X-Client-Id": str(uuid4())}, json={"message": "안녕하세요"})

    assert response.status_code == 503
