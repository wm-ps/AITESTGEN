"""Application settings: each application has its own Explorer limits and
test-case generation settings. Until it saves its own it uses the
organisation's (no change from before); saving changes that application
only; everyone on the app may read them, only admins change them."""

import uuid

from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application, PlatformUser, generation_settings_for
from explorer_core.limits import snapshot
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def _client(role: str = "admin") -> TestClient:
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
    org_limits = client.get("/explorer/settings").json()
    org_generation = client.get("/settings").json()

    limits = client.get(f"/explorer/applications/{first}/settings")
    assert limits.status_code == 200 and limits.json() == org_limits
    generation = client.get(f"/applications/{first}/generation-settings").json()
    assert generation["max_heal_attempts"] == org_generation["max_heal_attempts"]

    saved = client.put(
        f"/explorer/applications/{first}/settings", json={**org_limits, "max_missions": 7}
    )
    assert saved.status_code == 200, saved.text
    saved = client.put(
        f"/applications/{first}/generation-settings",
        json={**generation, "max_heal_attempts": 5, "screenshot_capture": "all"},
    )
    assert saved.status_code == 200, saved.text

    # This application only: the other one and the organisation are unchanged.
    assert client.get(f"/explorer/applications/{first}/settings").json()["max_missions"] == 7
    assert client.get(f"/explorer/applications/{second}/settings").json() == org_limits
    assert client.get("/explorer/settings").json() == org_limits
    other = client.get(f"/applications/{second}/generation-settings").json()
    assert other["max_heal_attempts"] == org_generation["max_heal_attempts"]
    assert (
        client.get("/settings").json()["max_heal_attempts"] == org_generation["max_heal_attempts"]
    )

    # What a run and the workers read.
    with Session(engine) as session:
        assert snapshot(session, _row(first).explorer_limits)["max_missions"] == 7
        assert snapshot(session, _row(second).explorer_limits) == org_limits
        own = generation_settings_for(session, _row(first).id)
        assert own.max_heal_attempts == 5 and own.screenshot_capture == "all"


def test_the_limits_rules_still_apply_per_application() -> None:
    client = _client()
    app_id = _new_app(client, "Settings Rules")
    limits = client.get(f"/explorer/applications/{app_id}/settings").json()
    bad = client.put(
        f"/explorer/applications/{app_id}/settings",
        json={**limits, "question_wait_minutes": 60, "mission_time_limit_minutes": 60},
    )
    assert bad.status_code == 422


def test_members_read_the_settings_but_only_admins_change_them() -> None:
    client = _client()
    app_id = _new_app(client, "Settings Members")
    with Session(engine) as session:  # the same user, now a member of the org
        user = session.exec(
            select(PlatformUser).where(PlatformUser.organization_id == _row(app_id).organization_id)
        ).one()
        user.role = "member"
        session.add(user)
        session.commit()

    limits = client.get(f"/explorer/applications/{app_id}/settings")
    assert limits.status_code == 200
    generation = client.get(f"/applications/{app_id}/generation-settings")
    assert generation.status_code == 200
    put = client.put(f"/explorer/applications/{app_id}/settings", json=limits.json())
    assert put.status_code == 403
    put = client.put(f"/applications/{app_id}/generation-settings", json=generation.json())
    assert put.status_code == 403
