"""Health endpoint test — no external dependencies, always runnable in CI."""

from api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_spec_served_and_includes_domain_schema() -> None:
    spec = client.get("/openapi.json").json()
    assert spec["openapi"].startswith("3.")
    assert "ApplicationRead" in spec["components"]["schemas"]
