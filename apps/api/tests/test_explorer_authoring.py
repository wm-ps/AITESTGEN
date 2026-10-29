"""Authoring runs (a user's request, carried out by Explorer): the request is
required, they wait for any active run, and pausing or stopping one never
touches the app's discovery record (that follows Explorer's own runs)."""

import uuid

from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application, DiscoveryRun
from explorer_core import ExplorerRun, run_workflow_name
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select


def _setup() -> tuple[TestClient, str, uuid.UUID]:
    init_db()
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name="Org Authoring", name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    created = client.post(
        "/applications",
        json={
            "name": "Authoring App",
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
        session.commit()
        return client, created["id"], application.id


def _discovery_status(application_id: uuid.UUID) -> str | None:
    with Session(engine) as session:
        record = session.exec(
            select(DiscoveryRun)
            .where(DiscoveryRun.application_id == application_id, DiscoveryRun.source == "crawler")
            .order_by(col(DiscoveryRun.created_at).desc())
        ).first()
        return record.status if record else None


def test_a_request_is_required_and_waits_for_an_active_run() -> None:
    client, app_external, app_id = _setup()
    assert (
        client.post(
            f"/explorer/applications/{app_external}/author", json={"prompt": "  "}
        ).status_code
        == 422
    )
    with Session(engine) as session:
        session.add(ExplorerRun(application_id=app_id, status="exploring"))
        session.commit()
    reply = client.post(
        f"/explorer/applications/{app_external}/author", json={"prompt": "Search policy POL-1"}
    )
    assert reply.status_code == 409


def test_pausing_or_stopping_an_authoring_run_leaves_discovery_alone() -> None:
    client, _, app_id = _setup()
    before = _discovery_status(app_id)
    with Session(engine) as session:
        run = ExplorerRun(application_id=app_id, status="exploring", prompt="Search policy POL-1")
        session.add(run)
        session.commit()
        run_id = run.external_id
        assert run_workflow_name(run) == "AuthoringRunWorkflow"
    assert client.post(f"/explorer/runs/{run_id}/pause").status_code == 200
    assert _discovery_status(app_id) == before
    with Session(engine) as session:
        row = session.exec(select(ExplorerRun).where(ExplorerRun.external_id == run_id)).one()
        row.status = "exploring"
        session.add(row)
        session.commit()
    assert client.post(f"/explorer/runs/{run_id}/stop").status_code == 200
    assert _discovery_status(app_id) == before


def test_an_authoring_run_never_stands_in_for_the_apps_exploration() -> None:
    client, app_external, app_id = _setup()
    with Session(engine) as session:
        for run in session.exec(
            select(ExplorerRun).where(ExplorerRun.application_id == app_id)
        ).all():
            session.delete(run)
        session.add(ExplorerRun(application_id=app_id, status="tested", prompt="Check Brad Smith"))
        session.commit()
    # Authoring alone doesn't make Explorer this app's discovery.
    assert client.get(f"/applications/{app_external}").json()["discovery_engine"] == "crawler"

    with Session(engine) as session:
        explored = ExplorerRun(application_id=app_id, status="tested")
        session.add(explored)
        session.commit()
        explored_id = str(explored.external_id)
        session.add(ExplorerRun(application_id=app_id, status="tested", prompt="Check Eric Lin"))
        session.commit()
    # A finished authoring run doesn't hide the latest exploration…
    assert (
        client.get(f"/explorer/applications/{app_external}/runs/latest").json()["id"] == explored_id
    )
    with Session(engine) as session:
        session.add(ExplorerRun(application_id=app_id, status="paused", prompt="Check Sally"))
        session.commit()
    # …but one that can still be resumed shows.
    assert (
        client.get(f"/explorer/applications/{app_external}/runs/latest").json()["prompt"]
        == "Check Sally"
    )
