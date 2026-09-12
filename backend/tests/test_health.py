"""System endpoint tests (PRD 0, sections 22 and 29).

These need no database: the liveness and version endpoints do not touch one.
"""

from fastapi.testclient import TestClient

from app.core.config import API_VERSION, MINIMUM_APP_VERSION, SERVICE_NAME
from app.main import app

client = TestClient(app)


def test_health_returns_200_and_documented_body() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": SERVICE_NAME}


def test_version_returns_documented_body() -> None:
    response = client.get("/api/v1/version")

    assert response.status_code == 200
    assert response.json() == {
        "api_version": API_VERSION,
        "minimum_app_version": MINIMUM_APP_VERSION,
    }


def test_unknown_route_returns_404() -> None:
    assert client.get("/api/v1/does-not-exist").status_code == 404
