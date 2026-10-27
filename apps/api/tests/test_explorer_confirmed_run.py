"""Right after Confirm (status "confirmed") a run is still running: it can be
stopped, and a second run can't start alongside it."""

import uuid

from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application
from explorer_core import ExplorerRun
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def test_a_confirmed_run_counts_as_running() -> None:
    init_db()
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name="Org Confirmed Run", name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    created = client.post(
        "/applications",
        json={
            "name": "Confirmed Run App",
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
        # Onboarding may have started a run; only the confirmed one matters here.
        for other in session.exec(
            select(ExplorerRun).where(ExplorerRun.application_id == application.id)
        ).all():
            other.status = "stopped"
            session.add(other)
        run = ExplorerRun(application_id=application.id, status="confirmed")
        session.add(run)
        session.commit()
        run_id = run.external_id

    started = client.post(f"/explorer/applications/{created['id']}/runs", json={})
    assert started.status_code == 409  # one run at a time
    stopped = client.post(f"/explorer/runs/{run_id}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
