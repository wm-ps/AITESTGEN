"""Application settings: each application has its own test-case generation
settings. Until it saves its own it uses the organisation's (no change from
before); saving changes that application only; everyone on the app may read
them, only admins change them. Explorer limits are organisation-wide only
(Settings → Explorer limits)."""

import uuid

from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application, ApplicationMember, PlatformUser, generation_settings_for
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def _client(role: str = "super_admin") -> TestClient:
    init_db()
    email = f"user-{uuid.uuid4()}@example.com"
    seed(
        email=email, password="pw", org_name=f"Org AppSettings {uuid.uuid4()}", name="T", role=role
    )
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client


def _new_app(client: TestClient, name: str) -> str:
    created = client.post(
        "/applications",
        json={
            "name": name,
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa",
            "password": "irrelevant",
            "discovery_required": False,
        },
    )
    assert created.status_code in (200, 201), created.text
    return created.json()["id"]


def _row(app_id: str) -> Application:
    with Session(engine) as session:
        return session.exec(
            select(Application).where(Application.external_id == uuid.UUID(app_id))
        ).one()


def test_an_application_uses_the_organisation_values_until_it_saves_its_own() -> None:
    client = _client()
    first, second = _new_app(client, "Settings A"), _new_app(client, "Settings B")
    org_generation = client.get("/settings").json()

    generation = client.get(f"/applications/{first}/generation-settings").json()
    assert generation["max_heal_attempts"] == org_generation["max_heal_attempts"]
    saved = client.put(
        f"/applications/{first}/generation-settings",
        json={**generation, "max_heal_attempts": 5, "screenshot_capture": "all"},
    )
    assert saved.status_code == 200, saved.text

    # This application only: the other one and the organisation are unchanged.
    other = client.get(f"/applications/{second}/generation-settings").json()
    assert other["max_heal_attempts"] == org_generation["max_heal_attempts"]
    assert (
        client.get("/settings").json()["max_heal_attempts"] == org_generation["max_heal_attempts"]
    )
    with Session(engine) as session:  # what the workers read
        own = generation_settings_for(session, _row(first).id)
        assert own.max_heal_attempts == 5 and own.screenshot_capture == "all"


def test_explorer_limits_are_organisation_wide_only() -> None:
    client = _client()
    app_id = _new_app(client, "Settings Limits")
    assert client.get(f"/explorer/applications/{app_id}/settings").status_code in (404, 405)
    limits = client.get("/explorer/settings").json()
    bad = client.put(
        "/explorer/settings",
        json={**limits, "question_wait_minutes": 60, "mission_time_limit_minutes": 60},
    )
    assert bad.status_code == 422


def test_members_read_the_settings_but_only_admins_change_them() -> None:
    client = _client()
    app_id = _new_app(client, "Settings Members")
    limits = client.get("/explorer/settings").json()  # read while still an admin
    with Session(engine) as session:  # the same user, now a plain user who only contributes
        user = session.exec(
            select(PlatformUser).where(PlatformUser.organization_id == _row(app_id).organization_id)
        ).one()
        user.role = "standard_user"
        session.add(user)
        grant = session.exec(select(ApplicationMember).where(ApplicationMember.user_id == user.id)).one()
        grant.role = "contributor"
        session.add(grant)
        session.commit()

    generation = client.get(f"/applications/{app_id}/generation-settings")
    assert generation.status_code == 200
    put = client.put(f"/applications/{app_id}/generation-settings", json=generation.json())
    assert put.status_code == 403
    assert client.put("/explorer/settings", json=limits).status_code == 403
