"""Sign-in + Organization-scoping tests (Story 1.2, AD-12).

Requires a live PostgreSQL (same convention as `test_scaffold_probe_db.py`).
"""

import uuid

import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(),
    reason="no PostgreSQL reachable at DATABASE_URL — start docker compose to run this test",
)


@pytest.fixture
def client() -> TestClient:
    init_db()
    return TestClient(app)


def test_login_success_sets_cookie_and_returns_user(client: TestClient) -> None:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="correct-horse-battery", org_name="Org A", name="Ada Lovelace")

    response = client.post(
        "/auth/login", json={"email": email, "password": "correct-horse-battery"}
    )

    assert response.status_code == 200
    assert response.json() == {"name": "Ada Lovelace", "email": email}
    assert "session" in response.cookies


def test_login_wrong_password_rejected(client: TestClient) -> None:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="correct-horse-battery", org_name="Org B", name="Bob")

    response = client.post("/auth/login", json={"email": email, "password": "wrong"})

    assert response.status_code == 401
    assert "session" not in response.cookies


def test_me_requires_session(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401


def test_login_then_me_then_logout(client: TestClient) -> None:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name="Org C", name="Cara")

    client.post("/auth/login", json={"email": email, "password": "pw"})
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == email

    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401
