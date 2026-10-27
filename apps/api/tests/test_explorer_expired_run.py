"""An expired Explorer run (App Summary not confirmed in time) is over: it
can't be confirmed or resumed, and it doesn't block a new run."""

import uuid

from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application
from explorer_core import ACTIVE_RUN_STATUSES, ExplorerRun
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def test_expired_run_cannot_be_confirmed_or_resumed() -> None:
    init_db()
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name="Org Expired Run", name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    created = client.post(
        "/applications",
        json={
            "name": "Expired Run App",
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
        run = ExplorerRun(application_id=application.id, status="expired")
        session.add(run)
        session.commit()
        run_id = run.external_id

    for action in ("confirm", "resume"):
        response = client.post(f"/explorer/runs/{run_id}/{action}")
        assert response.status_code == 409
        assert "expired" in response.json()["detail"]
    assert "expired" not in ACTIVE_RUN_STATUSES  # frees the app for a new run
