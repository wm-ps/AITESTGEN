"""The app's discovery record follows its Explorer run: stopped -> failed
(with the reason), paused -> paused, resumed -> running. It never keeps
saying "running" after the run ended."""

import uuid

from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application, DiscoveryRun
from explorer_core import ExplorerRun
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select


def _discovery(application_id: uuid.UUID) -> DiscoveryRun:
    with Session(engine) as session:
        return session.exec(
            select(DiscoveryRun)
            .where(DiscoveryRun.application_id == application_id, DiscoveryRun.source == "crawler")
            .order_by(col(DiscoveryRun.created_at).desc())
        ).first()


def test_discovery_record_follows_stop_pause_and_resume() -> None:
    init_db()
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name="Org Discovery Mirror", name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    created = client.post(
        "/applications",
        json={
            "name": "Discovery Mirror App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    ).json()
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(created["id"]))
        ).one()
        for other in session.exec(
            select(ExplorerRun).where(ExplorerRun.application_id == application.id)
        ).all():
            other.status = "tested"
            session.add(other)
        run = ExplorerRun(application_id=application.id, status="exploring")
        session.add(run)
        session.commit()
        run_id, app_id = run.external_id, application.id

    assert client.post(f"/explorer/runs/{run_id}/pause").status_code == 200
    assert _discovery(app_id).status == "paused"

    assert client.post(f"/explorer/runs/{run_id}/resume").status_code == 200
    assert _discovery(app_id).status == "running"

    assert client.post(f"/explorer/runs/{run_id}/stop").status_code == 200
    record = _discovery(app_id)
    assert record.status == "failed"
    assert record.failure_reason == "Explorer was stopped before it finished"
