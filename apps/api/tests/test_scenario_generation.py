"""Scenario generation trigger + Review Scenarios endpoints (Story 4.1).

Requires PostgreSQL + Vault + Temporal reachable, same skip-cleanly
convention as `test_onboarding.py`. `Scenario` rows are seeded directly
against the DB for the read/curation/test-data endpoints — the AI-backed
`ScenarioGenerationActivity` itself is covered in
`apps/workers/generation/tests/test_scenario_generation_activity.py` with a
fake `AIProvider`. The trigger endpoint here only verifies a `GenerationWorkflow`
actually starts (and is idempotent) — it doesn't wait for a worker to
process it, since no generation worker is guaranteed to be running during a
pytest run (same reasoning as `conftest.py`'s discovery-workflow cleanup).
"""

import asyncio
import uuid

import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from api.temporal_client import get_temporal_client
from domain import DiscoveryRun, Journey, Page, Scenario
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


def _add_candidate_journey(application: dict, name: str = "Checkout") -> Journey:
    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        page = Page(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            url="https://staging.example.com/checkout",
            title="Checkout",
        )
        session.add(page)
        session.flush()
        journey = Journey(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            name=name,
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.commit()
        session.refresh(journey)
        return journey


def _add_scenario(
    journey: Journey,
    name: str = "Guest checkout",
    scenario_type: str = "happy",
    test_data: list[dict] | None = None,
) -> str:
    with Session(engine) as session:
        scenario = Scenario(
            journey_id=journey.id,
            type=scenario_type,
            name=name,
            steps=["Add item to cart", "Submit payment"],
            expected_result="Order confirmation is shown",
            test_data=test_data
            if test_data is not None
            else [{"name": "username", "mandatory": True, "value": None}],
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


def test_generate_scenarios_starts_one_workflow_per_candidate_journey() -> None:
    init_db()
    client = _signed_in_client("Org Scenario Generation")
    application = _create_application(client, "Generation App")
    journey = _add_candidate_journey(application)

    response = client.post(f"/applications/{application['id']}/generate-scenarios")
    assert response.status_code == 202
    assert response.json() == {"journeys_triggered": 1}

    workflow_id = f"generation-{journey.external_id}-{journey.attempt}"

    async def _describe() -> str:
        temporal_client = await get_temporal_client()
        description = await temporal_client.get_workflow_handle(workflow_id).describe()
        return description.task_queue

    try:
        assert asyncio.run(_describe()) == GENERATION_TASK_QUEUE
    finally:
        asyncio.run(_terminate(workflow_id))


def test_generate_scenarios_is_idempotent_for_journeys_with_existing_scenarios() -> None:
    init_db()
    client = _signed_in_client("Org Scenario Generation Idempotent")
    application = _create_application(client, "Idempotent App")
    journey = _add_candidate_journey(application)
    _add_scenario(journey)

    response = client.post(f"/applications/{application['id']}/generate-scenarios")
    assert response.status_code == 202
    # Already has current-attempt Scenarios — skipped, not re-triggered.
    assert response.json() == {"journeys_triggered": 0}


def test_generate_scenarios_starting_twice_only_triggers_once() -> None:
    init_db()
    client = _signed_in_client("Org Scenario Generation Twice")
    application = _create_application(client, "Twice App")
    journey = _add_candidate_journey(application)
    workflow_id = f"generation-{journey.external_id}-{journey.attempt}"

    try:
        first = client.post(f"/applications/{application['id']}/generate-scenarios")
        assert first.json() == {"journeys_triggered": 1}

        # Second call races before any Scenario row exists yet — Temporal's
        # WorkflowAlreadyStartedError is the layer that catches this, not the
        # Scenario-existence check (which only helps once rows are written).
        second = client.post(f"/applications/{application['id']}/generate-scenarios")
        assert second.json() == {"journeys_triggered": 0}
    finally:
        asyncio.run(_terminate(workflow_id))


def test_list_scenarios_returns_journey_scoped_current_scenarios() -> None:
    init_db()
    client = _signed_in_client("Org Scenario List")
    application = _create_application(client, "List App")
    journey = _add_candidate_journey(application)
    _add_scenario(journey, name="Guest checkout", scenario_type="happy")

    response = client.get(f"/applications/{application['id']}/scenarios")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Guest checkout"
    assert body[0]["journey_name"] == "Checkout"
    assert body[0]["type"] == "happy"
    assert body[0]["test_data_complete"] is False


def test_list_scenarios_is_organization_scoped() -> None:
    init_db()
    client_a = _signed_in_client("Org Scenario List A")
    client_b = _signed_in_client("Org Scenario List B")
    application = _create_application(client_a, "Org A Scenario App")
    journey = _add_candidate_journey(application)
    _add_scenario(journey)

    response = client_b.get(f"/applications/{application['id']}/scenarios")
    assert response.status_code == 404


def test_rename_scenario_updates_name() -> None:
    init_db()
    client = _signed_in_client("Org Scenario Rename")
    application = _create_application(client, "Rename App")
    journey = _add_candidate_journey(application)
    scenario_id = _add_scenario(journey, name="Old Name")

    response = client.patch(f"/scenarios/{scenario_id}", json={"name": "New Name"})
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


def test_delete_scenario_removes_it_from_the_list() -> None:
    init_db()
    client = _signed_in_client("Org Scenario Delete")
    application = _create_application(client, "Delete App")
    journey = _add_candidate_journey(application)
    scenario_id = _add_scenario(journey)

    assert client.delete(f"/scenarios/{scenario_id}").status_code == 204
    response = client.get(f"/applications/{application['id']}/scenarios")
    assert response.json() == []


def test_scenario_curation_is_organization_scoped() -> None:
    init_db()
    client_a = _signed_in_client("Org Scenario Curation A")
    client_b = _signed_in_client("Org Scenario Curation B")
    application = _create_application(client_a, "Org A Curation App")
    journey = _add_candidate_journey(application)
    scenario_id = _add_scenario(journey)

    assert client_b.patch(f"/scenarios/{scenario_id}", json={"name": "Hijacked"}).status_code == 404
    assert client_b.delete(f"/scenarios/{scenario_id}").status_code == 404


def test_update_test_data_sets_value_and_flips_complete_once_all_mandatory_filled() -> None:
    init_db()
    client = _signed_in_client("Org Scenario Test Data")
    application = _create_application(client, "Test Data App")
    journey = _add_candidate_journey(application)
    scenario_id = _add_scenario(
        journey,
        test_data=[
            {"name": "username", "mandatory": True, "value": None},
            {"name": "promo_code", "mandatory": False, "value": None},
        ],
    )

    response = client.patch(
        f"/scenarios/{scenario_id}/test-data", json={"name": "username", "value": "qa-user"}
    )
    assert response.status_code == 200
    body = response.json()
    field = next(f for f in body["test_data"] if f["name"] == "username")
    assert field["value"] == "qa-user"
    # Only mandatory field is now filled — non-mandatory promo_code stays blank.
    assert body["test_data_complete"] is True


def test_update_test_data_rejects_unknown_field_name() -> None:
    init_db()
    client = _signed_in_client("Org Scenario Test Data Unknown")
    application = _create_application(client, "Test Data Unknown App")
    journey = _add_candidate_journey(application)
    scenario_id = _add_scenario(journey)

    response = client.patch(
        f"/scenarios/{scenario_id}/test-data", json={"name": "nonexistent", "value": "x"}
    )
    assert response.status_code == 422
