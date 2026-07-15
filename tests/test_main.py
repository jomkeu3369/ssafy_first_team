from fastapi.testclient import TestClient

from main import app


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
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:5173"
    )
