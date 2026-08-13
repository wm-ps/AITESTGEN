"""Save-as-Project — Cross-Session Pause & Resume (Story 2.17).

Same skip-cleanly convention as `test_discovery_progress.py` — real
Postgres + Vault + Temporal.
"""

import uuid

import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import DiscoveryRun, Page
from fastapi.testclient import TestClient
from hvac.exceptions import VaultError
from secrets_client.vault_client import VAULT_ADDR, VAULT_TOKEN
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


def _vault_available() -> bool:
    try:
        return hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN).sys.is_initialized()
    except (VaultError, OSError):
        return False


def _temporal_available() -> bool:
    import asyncio

    from api.temporal_client import get_temporal_client

    async def _check() -> bool:
        try:
            await get_temporal_client()
            return True
        except Exception:
            return False

    return asyncio.run(_check())


pytestmark = pytest.mark.skipif(
    not (_db_available() and _vault_available() and _temporal_available()),
    reason="requires PostgreSQL + Vault + Temporal reachable — start docker compose",
)


def _signed_in_client(org_name: str) -> TestClient:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org_name, name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client


def _create_application(client: TestClient, name: str) -> dict:
    response = client.post(
        "/applications",
        json={
            "name": name,
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_pause_sets_status_paused_and_touches_no_other_table() -> None:
    init_db()
    client = _signed_in_client("Org Pause")
    application = _create_application(client, "Pause App")

    with Session(engine) as session:
        before = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        before_id = before.id

    response = client.post(f"/applications/{application['id']}/pause-discovery")
    assert response.status_code == 200
    assert response.json()["discovery_status"] == "paused"

    with Session(engine) as session:
        runs = session.exec(
            select(DiscoveryRun).where(DiscoveryRun.application_id == before.application_id)
        ).all()
    # AC 1/3: pausing sets status on the existing row — no new DiscoveryRun,
    # no new table.
    assert len(runs) == 1
    assert runs[0].id == before_id
    assert runs[0].status == "paused"


def test_pause_a_non_running_run_is_rejected() -> None:
    init_db()
    client = _signed_in_client("Org Pause Reject")
    application = _create_application(client, "Pause Reject App")

    first = client.post(f"/applications/{application['id']}/pause-discovery")
    assert first.status_code == 200

    second = client.post(f"/applications/{application['id']}/pause-discovery")
    assert second.status_code == 409


def test_resume_starts_a_fresh_discovery_run_scoped_by_application_id() -> None:
    """AC 2/3: resume re-authenticates fresh (a new DiscoveryRun, new
    workflow) and every read involved (canonical Pages, open BlockedTasks)
    is filtered by `application_id`, not a new grouping mechanism."""
    init_db()
    client = _signed_in_client("Org Resume")
    application = _create_application(client, "Resume App")

    with Session(engine) as session:
        paused_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        application_pk = paused_run.application_id
        # A confirmed canonical Page from the "paused" run — resume must not
        # duplicate or lose it.
        session.add(
            Page(
                application_id=application_pk,
                discovery_run_id=paused_run.id,
                url="https://staging.example.com/orders",
                title="Orders",
            )
        )
        session.commit()

    pause_response = client.post(f"/applications/{application['id']}/pause-discovery")
    assert pause_response.status_code == 200

    resume_response = client.post(f"/applications/{application['id']}/resume-discovery")
    assert resume_response.status_code == 201
    resumed = resume_response.json()
    assert resumed["discovery_status"] == "running"
    assert resumed["discovery_run_id"] != application["discovery_run_id"]

    with Session(engine) as session:
        runs = session.exec(
            select(DiscoveryRun).where(DiscoveryRun.application_id == application_pk)
        ).all()
        pages = session.exec(select(Page).where(Page.application_id == application_pk)).all()

    # AC 3: no new "Project" grouping column/table — still exactly
    # `application_id`-scoped rows, just two DiscoveryRuns for it now.
    assert len(runs) == 2
    assert {r.status for r in runs} == {"paused", "running"}
    assert len(pages) == 1, "the confirmed Page from before pause must survive resume untouched"

    # GET /applications/{id} must reflect the latest (resumed) run, not the
    # first-ever one.
    get_response = client.get(f"/applications/{application['id']}")
    assert get_response.json()["discovery_run_id"] == resumed["discovery_run_id"]


def test_resume_a_non_paused_run_is_rejected() -> None:
    init_db()
    client = _signed_in_client("Org Resume Reject")
    application = _create_application(client, "Resume Reject App")

    response = client.post(f"/applications/{application['id']}/resume-discovery")
    assert response.status_code == 409


def test_pause_resume_are_organization_scoped() -> None:
    init_db()
    client_a = _signed_in_client("Org Pause Resume A")
    client_b = _signed_in_client("Org Pause Resume B")
    application = _create_application(client_a, "Org A Pause App")

    assert client_b.post(f"/applications/{application['id']}/pause-discovery").status_code == 404
    assert (
        client_b.post(f"/applications/{application['id']}/resume-discovery").status_code == 404
    )


def test_application_not_found_across_org() -> None:
    # Sanity check the Application lookup itself raises before any status
    # check runs, for both new endpoints.
    init_db()
    client = _signed_in_client("Org Pause Resume 404")
    assert client.post(f"/applications/{uuid.uuid4()}/pause-discovery").status_code == 404
    assert client.post(f"/applications/{uuid.uuid4()}/resume-discovery").status_code == 404
