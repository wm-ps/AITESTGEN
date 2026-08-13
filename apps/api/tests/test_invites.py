"""Invite-only Sign-up tests — admin sends, invitee accepts, no self-service.

Requires a live PostgreSQL (same convention as test_auth.py).
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


def _admin_client(org_name: str) -> TestClient:
    init_db()
    email = f"admin-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org_name, name="Admin")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client


def _invite_link_token(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []

    def _fake_send(to_email: str, org_name: str, token: str) -> None:
        captured.append(token)

    monkeypatch.setattr("api.main.send_invite_email", _fake_send)
    return captured


def test_admin_can_send_and_invitee_can_accept(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _invite_link_token(monkeypatch)
    admin = _admin_client("Org Invite Accept")
    email = f"invitee-{uuid.uuid4()}@example.com"

    response = admin.post("/invites", json={"email": email, "role": "member"})
    assert response.status_code == 201
    assert captured, "invite email should have been sent"
    token = captured[0]

    accept_client = TestClient(app)
    accept_response = accept_client.post(
        "/invites/accept", json={"token": token, "name": "New Person", "password": "pw123456"}
    )
    assert accept_response.status_code == 200
    body = accept_response.json()
    assert body == {"name": "New Person", "email": email, "role": "member"}
    assert "session" in accept_response.cookies


def test_accepting_twice_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _invite_link_token(monkeypatch)
    admin = _admin_client("Org Invite Reuse")
    email = f"invitee-{uuid.uuid4()}@example.com"
    admin.post("/invites", json={"email": email, "role": "member"})
    token = captured[0]

    client = TestClient(app)
    client.post("/invites/accept", json={"token": token, "name": "A", "password": "pw123456"})
    second = client.post("/invites/accept", json={"token": token, "name": "B", "password": "pw123456"})
    assert second.status_code == 400


def test_unknown_token_rejected() -> None:
    init_db()
    client = TestClient(app)
    response = client.post(
        "/invites/accept", json={"token": "not-a-real-token", "name": "A", "password": "pw123456"}
    )
    assert response.status_code == 400


def test_non_admin_cannot_send_invite(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _invite_link_token(monkeypatch)
    admin = _admin_client("Org Invite Member Role")
    member_email = f"member-{uuid.uuid4()}@example.com"
    admin.post("/invites", json={"email": member_email, "role": "member"})
    token = captured[0]

    member_client = TestClient(app)
    member_client.post(
        "/invites/accept", json={"token": token, "name": "Member", "password": "pw123456"}
    )

    response = member_client.post("/invites", json={"email": "someone@example.com"})
    assert response.status_code == 403


def test_revoke_invite_prevents_acceptance(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _invite_link_token(monkeypatch)
    admin = _admin_client("Org Invite Revoke")
    email = f"invitee-{uuid.uuid4()}@example.com"
    admin.post("/invites", json={"email": email, "role": "member"})
    token = captured[0]

    pending = admin.get("/invites").json()
    invite_id = next(i["id"] for i in pending if i["email"] == email)
    assert admin.delete(f"/invites/{invite_id}").status_code == 204

    client = TestClient(app)
    response = client.post(
        "/invites/accept", json={"token": token, "name": "A", "password": "pw123456"}
    )
    assert response.status_code == 400
