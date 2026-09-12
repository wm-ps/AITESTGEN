"""Vantage V2 Team members page — list the org roster, remove a member.

Requires a live PostgreSQL (same convention as test_invites.py).
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


def _admin_client(org_name: str) -> tuple[TestClient, str]:
    init_db()
    email = f"admin-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org_name, name="Admin")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client, email


def _invite_link_token(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []

    def _fake_send(to_email: str, token: str) -> None:
        captured.append(token)

    monkeypatch.setattr("api.main.send_invite_email", _fake_send)
    return captured


def _add_member(admin: TestClient, monkeypatch: pytest.MonkeyPatch, *, role: str = "member") -> str:
    captured = _invite_link_token(monkeypatch)
    email = f"member-{uuid.uuid4()}@example.com"
    admin.post("/invites", json={"email": email, "role": role})
    token = captured[-1]
    TestClient(app).post(
        "/invites/accept", json={"token": token, "name": "Teammate", "password": "pw123456"}
    )
    return email


def test_list_team_includes_admin_and_invited_members(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, admin_email = _admin_client("Org Team List")
    member_email = _add_member(admin, monkeypatch)

    response = admin.get("/team")

    assert response.status_code == 200
    emails = {m["email"] for m in response.json()}
    assert admin_email in emails
    assert member_email in emails


def test_list_team_requires_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, _ = _admin_client("Org Team List Non Admin")
    member_email = _add_member(admin, monkeypatch)

    member_client = TestClient(app)
    member_client.post("/auth/login", json={"email": member_email, "password": "pw123456"})
    response = member_client.get("/team")

    assert response.status_code == 403


def test_admin_can_remove_a_member(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, _ = _admin_client("Org Team Remove")
    member_email = _add_member(admin, monkeypatch)

    response = admin.delete(f"/team/{member_email}")

    assert response.status_code == 204
    remaining = {m["email"] for m in admin.get("/team").json()}
    assert member_email not in remaining


def test_admin_cannot_remove_themselves(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, admin_email = _admin_client("Org Team Remove Self")

    response = admin.delete(f"/team/{admin_email}")

    assert response.status_code == 422


def test_admin_can_remove_another_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, _ = _admin_client("Org Team Remove Other Admin")
    second_admin_email = _add_member(admin, monkeypatch, role="admin")

    response = admin.delete(f"/team/{second_admin_email}")

    assert response.status_code == 204
    remaining = {m["email"] for m in admin.get("/team").json()}
    assert second_admin_email not in remaining


def test_removing_unknown_member_404s(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, _ = _admin_client("Org Team Remove Unknown")

    response = admin.delete("/team/not-a-real-member@example.com")

    assert response.status_code == 404
