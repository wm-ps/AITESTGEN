"""Settings → Explorer limits: read and saved by admins only, missions must
get more time than the question wait, and a run shows its AI spend and the
limit that paused it."""

import uuid

from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application
from explorer_core import ExplorerRun, ExplorerSettings
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def _client(role: str = "admin") -> tuple[TestClient, str]:
    init_db()
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=f"Org Limits {uuid.uuid4()}", name="T", role=role)
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client, email


def _restore(before: dict[str, object]) -> None:
    with Session(engine) as session:
        settings = session.get(ExplorerSettings, 1)
        assert settings is not None
        for key, value in before.items():
            setattr(settings, key, value)
        session.add(settings)
        session.commit()


def test_admins_read_and_save_the_limits() -> None:
    client, _ = _client()
    before = client.get("/explorer/settings").json()
    try:
        assert before["question_wait_minutes"] is not None
        changed = {**before, "ai_budget_usd": 12.5, "run_time_limit_minutes": 240}
        saved = client.put("/explorer/settings", json=changed)
        assert saved.status_code == 200, saved.text
        assert client.get("/explorer/settings").json()["ai_budget_usd"] == 12.5
        # Unlimited question wait needs unlimited mission time too.
        bad = client.put(
            "/explorer/settings",
            json={**before, "question_wait_minutes": None, "mission_time_limit_minutes": 75},
        )
        assert bad.status_code == 422
        bad = client.put(
            "/explorer/settings",
            json={**before, "question_wait_minutes": 60, "mission_time_limit_minutes": 60},
        )
        assert bad.status_code == 422
        unlimited = client.put(
            "/explorer/settings",
            json={**before, "question_wait_minutes": None, "mission_time_limit_minutes": None},
        )
        assert unlimited.status_code == 200
    finally:
        _restore(before)


def test_only_admins_see_the_limits() -> None:
    client, _ = _client(role="viewer")
    assert client.get("/explorer/settings").status_code == 403


def test_a_run_shows_its_spend_and_the_limit_that_paused_it() -> None:
    client, _ = _client()
    created = client.post(
        "/applications",
        json={
            "name": "Limits App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa",
            "password": "irrelevant",
            "discovery_required": False,
        },
    ).json()
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(created["id"]))
        ).one()
        run = ExplorerRun(
            application_id=application.id,
            status="paused",
            ai_spent_usd=5.123456,
            limits={"ai_budget_usd": 5.0, "reached": "ai_budget"},
        )
        session.add(run)
        session.commit()
        run_id = run.external_id
    shown = client.get(f"/explorer/runs/{run_id}").json()
    assert shown["ai_spent_usd"] == 5.1235
    assert shown["ai_budget_usd"] == 5.0
    assert shown["limit_reached"] == "ai_budget"
    # Nothing explored yet (App Summary never confirmed): nothing to write from.
    assert client.post(f"/explorer/runs/{run_id}/wrap-up").status_code == 409
