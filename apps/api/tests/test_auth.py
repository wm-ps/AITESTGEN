"""Sign-in + Organization-scoping tests (Story 1.2, AD-12).

Requires a live PostgreSQL (same convention as `test_scaffold_probe_db.py`).
"""

import time
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
    assert response.json() == {"name": "Ada Lovelace", "email": email, "role": "admin"}
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


def _signed_in(client: TestClient, org: str) -> str:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org, name="Dana")
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return email


def test_only_user_activity_slides_the_session(client: TestClient) -> None:
    _signed_in(client, "Org D")

    # A background poll keeps working but doesn't extend the session.
    assert "session" not in client.get("/auth/me").cookies
    assert "session" in client.get("/auth/me", headers={"X-User-Activity": "1"}).cookies


def test_logout_revokes_a_copied_cookie(client: TestClient) -> None:
    _signed_in(client, "Org E")
    copied = client.cookies.get("session")

    client.post("/auth/logout")

    other = TestClient(app, cookies={"session": copied})
    assert other.get("/auth/me").status_code == 401


def test_session_older_than_absolute_limit_rejected(client: TestClient) -> None:
    from api.auth import ABSOLUTE_TIMEOUT, _serializer
    from api.db import engine as db_engine
    from domain import PlatformUser
    from sqlmodel import Session, select

    email = _signed_in(client, "Org F")
    with Session(db_engine) as s:
        user = s.exec(select(PlatformUser).where(PlatformUser.email == email)).one()
        stale = _serializer.dumps([str(user.id), user.session_version, int(time.time()) - ABSOLUTE_TIMEOUT - 1])

    assert TestClient(app, cookies={"session": stale}).get("/auth/me").status_code == 401


def test_old_format_cookie_rejected(client: TestClient) -> None:
    from api.auth import _serializer

    old = _serializer.dumps(str(uuid.uuid4()))
    assert TestClient(app, cookies={"session": old}).get("/auth/me").status_code == 401


def test_account_locks_after_repeated_wrong_passwords(client: TestClient) -> None:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name="Org G", name="Eve")

    for _ in range(5):
        assert client.post("/auth/login", json={"email": email, "password": "wrong"}).status_code == 401

    # Locked: even the right password is refused for now.
    assert client.post("/auth/login", json={"email": email, "password": "pw"}).status_code == 429
