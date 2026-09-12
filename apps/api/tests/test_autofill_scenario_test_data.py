"""Scenarios tab "Auto-generate" (test data) — Vantage V2.

Same skip-cleanly convention as test_scenario_generation.py: verifies the
AutofillScenarioTestDataWorkflow actually starts (and the unavailable/404
paths), without waiting for a worker to process it — no generation worker
is guaranteed to be running during a pytest run.
"""

import asyncio
import uuid

import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from api.temporal_client import get_temporal_client
from domain import DiscoveryRun, Journey, Scenario
from fastapi.testclient import TestClient
from hvac.exceptions import VaultError
from secrets_client.vault_client import VAULT_ADDR, VAULT_TOKEN
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import GENERATION_TASK_QUEUE


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


def _add_scenario(application: dict) -> str:
    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        journey = Journey(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            name="Checkout",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()
        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name="Guest checkout",
            steps=["Add item to cart", "Submit payment"],
            expected_result="Order confirmation is shown",
            test_data=[{"name": "username", "mandatory": True, "value": None}],
            generation_run_id=journey.attempt,
        )
        session.add(scenario)
        session.commit()
        session.refresh(scenario)
        return str(scenario.external_id)


async def _terminate(workflow_id: str) -> None:
    try:
        client = await get_temporal_client()
        await client.get_workflow_handle(workflow_id).terminate(
            reason="pytest cleanup: dev Temporal server is shared, leaked workflows pile up"
        )
    except Exception:
        pass


def test_autofill_starts_a_workflow_on_the_generation_queue() -> None:
    init_db()
    client = _signed_in_client("Org Autofill Test Data")
    application = _create_application(client, "Autofill App")
    scenario_id = _add_scenario(application)

    response = client.post(f"/scenarios/{scenario_id}/test-data/auto-fill")
    assert response.status_code == 202
    assert response.json() == {"started": True}

    workflow_id = f"autofill-{scenario_id}"

    async def _describe() -> str:
        temporal_client = await get_temporal_client()
        description = await temporal_client.get_workflow_handle(workflow_id).describe()
        return description.task_queue

    try:
        assert asyncio.run(_describe()) == GENERATION_TASK_QUEUE
    finally:
        asyncio.run(_terminate(workflow_id))


def test_get_autofill_status_reports_running_right_after_starting() -> None:
    init_db()
    client = _signed_in_client("Org Autofill Status Running")
    application = _create_application(client, "Autofill Status App")
    scenario_id = _add_scenario(application)
    client.post(f"/scenarios/{scenario_id}/test-data/auto-fill")

    try:
        response = client.get(f"/scenarios/{scenario_id}/test-data/auto-fill")
        assert response.status_code == 200
        # No worker is guaranteed to be running during a pytest run, so this
        # is "running" (Temporal accepted it) not "complete".
        assert response.json()["status"] == "running"
    finally:
        asyncio.run(_terminate(f"autofill-{scenario_id}"))


def test_autofill_reports_unavailable_when_generation_queue_has_no_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api import main as api_main

    async def _no_pollers(client: object, task_queue: str) -> bool:
        return False

    monkeypatch.setattr(api_main, "has_pollers", _no_pollers)

    init_db()
    client = _signed_in_client("Org Autofill Worker Down")
    application = _create_application(client, "No Worker App")
    scenario_id = _add_scenario(application)

    response = client.post(f"/scenarios/{scenario_id}/test-data/auto-fill")

    assert response.status_code == 503
    assert response.json()["detail"] == "GENERATION_UNAVAILABLE"


def test_get_autofill_status_404s_when_never_started() -> None:
    init_db()
    client = _signed_in_client("Org Autofill Never Started")
    application = _create_application(client, "Never Started App")
    scenario_id = _add_scenario(application)

    response = client.get(f"/scenarios/{scenario_id}/test-data/auto-fill")

    assert response.status_code == 404
    assert response.json()["detail"] == "AUTOFILL_REQUEST_NOT_FOUND"
