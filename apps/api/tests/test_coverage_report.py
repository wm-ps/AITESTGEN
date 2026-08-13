"""Coverage Report & Run Diagnostics (Story 2.22 Tasks 2-6).

Same skip-cleanly convention as `test_discovery_progress.py`.
"""

import uuid

import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Action, BlockedTask, DiagnosticRecord, DiscoveryError, DiscoveryRun, Form, Page
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


def test_report_aggregates_all_five_coverage_categories() -> None:
    init_db()
    client = _signed_in_client("Org Coverage Report")
    application = _create_application(client, "Coverage App")

    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        run_id = discovery_run.id
        app_id = discovery_run.application_id

        page = Page(
            application_id=app_id,
            discovery_run_id=run_id,
            url="https://staging.example.com/orders",
            title="Orders",
        )
        session.add(page)
        session.flush()
        session.add(
            Action(
                application_id=app_id,
                discovery_run_id=run_id,
                page_id=page.id,
                description="Submit",
            )
        )
        session.add(
            Form(
                application_id=app_id,
                discovery_run_id=run_id,
                page_id=page.id,
                action_url="/orders",
            )
        )
        session.add(
            BlockedTask(
                application_id=app_id,
                discovery_run_id=run_id,
                aggregation_key="*:text:policy-number",
                required_description="Active Policy Number",
                required_type="data",
            )
        )
        session.add(
            DiagnosticRecord(
                discovery_run_id=run_id,
                kind="safety_verdict",
                payload={
                    "verdict": "DESTRUCTIVE",
                    "url": "/admin/delete-account",
                    "label": "Delete",
                },
            )
        )
        session.add(
            DiagnosticRecord(
                discovery_run_id=run_id,
                kind="unreached",
                payload={"url": "/orders", "reason": "return_failed"},
            )
        )
        session.commit()

    response = client.get(f"/discovery-runs/{application['discovery_run_id']}/report")
    assert response.status_code == 200
    body = response.json()

    assert body["coverage"]["reached"] == {"pages": 1, "actions": 1, "forms": 1}
    assert len(body["coverage"]["blocked"]) == 1
    assert body["coverage"]["blocked"][0]["aggregation_key"] == "*:text:policy-number"
    assert len(body["coverage"]["skipped_for_safety"]) == 1
    assert len(body["coverage"]["unreached"]) == 1
    # AC 4: renders whatever's available rather than failing outright — the
    # Errored category's producer (Story 2.18) may not exist yet.
    assert isinstance(body["coverage"]["errored"]["items"], list)
    assert isinstance(body["diagnostics"], dict)


def test_report_errored_section_lights_up_once_discovery_error_rows_exist() -> None:
    """Story 2.18 landed after this story — closes the loop on AC 4: the
    Errored category, which degraded to `available=False` via a lazy
    import before Story 2.18 existed, now reports real rows with no edit to
    `coverage_report.py` required."""
    init_db()
    client = _signed_in_client("Org Errored Section")
    application = _create_application(client, "Errored Section App")

    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        session.add(
            DiscoveryError(
                application_id=discovery_run.application_id,
                discovery_run_id=discovery_run.id,
                error_code="DISC-003",
                message="Target application unresponsive after 3 attempts.",
                retry_count=3,
            )
        )
        session.commit()

    response = client.get(f"/discovery-runs/{application['discovery_run_id']}/report")
    assert response.status_code == 200
    errored = response.json()["coverage"]["errored"]
    assert errored["available"] is True
    assert len(errored["items"]) == 1
    assert errored["items"][0]["error_code"] == "DISC-003"


def test_report_is_organization_scoped() -> None:
    init_db()
    client_a = _signed_in_client("Org Report A")
    client_b = _signed_in_client("Org Report B")
    application = _create_application(client_a, "Org A Report App")

    response = client_b.get(f"/discovery-runs/{application['discovery_run_id']}/report")
    assert response.status_code == 404


def test_complete_status_never_travels_without_coverage_counts() -> None:
    """AC 2: `status=complete` must never be presented alone."""
    init_db()
    client = _signed_in_client("Org Qualified Status")
    application = _create_application(client, "Qualified Status App")

    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        discovery_run.status = "complete"
        session.add(discovery_run)
        session.commit()

    response = client.get(f"/applications/{application['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["discovery_status"] == "complete"
    assert body["discovery_coverage_summary"] is not None
    assert set(body["discovery_coverage_summary"]) == {
        "reached_pages",
        "reached_actions",
        "reached_forms",
        "blocked",
        "skipped_for_safety",
        "unreached",
        "errored",
    }


def test_running_status_has_no_coverage_summary() -> None:
    init_db()
    client = _signed_in_client("Org Running Status")
    application = _create_application(client, "Running Status App")

    response = client.get(f"/applications/{application['id']}")
    assert response.status_code == 200
    assert response.json()["discovery_coverage_summary"] is None
