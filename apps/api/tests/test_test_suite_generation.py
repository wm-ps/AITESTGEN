"""Generate Suite trigger + Test Suite results endpoints (Story 4.2).

Requires PostgreSQL + Vault + Temporal reachable, same skip-cleanly
convention as `test_scenario_generation.py`. `Scenario`/`TestSuite`/
`TestAsset` rows are seeded directly against the DB for the read endpoint —
the AI-backed `PlaywrightGenerationActivity` itself is covered in
`apps/workers/generation/tests/test_playwright_generation_activity.py` with a
fake `AIProvider`. The trigger endpoint here only verifies a
`SuiteGenerationWorkflow` actually starts (and is idempotent, Journey-scoped)
— it doesn't wait for a worker to process it.
"""

import asyncio
import uuid

import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from api.temporal_client import get_temporal_client
from domain import DiscoveryRun, Journey, Scenario, TestAsset, TestSuite
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


def _add_scenario(journey: Journey, name: str = "Guest checkout") -> Scenario:
    with Session(engine) as session:
        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name=name,
            steps=["Add item to cart", "Submit payment"],
            expected_result="Order confirmation is shown",
            test_data=[{"name": "username", "mandatory": True, "value": "qa-user"}],
            generation_run_id=journey.attempt,
        )
        session.add(scenario)
        session.commit()
        session.refresh(scenario)
        return scenario


def _add_test_suite_with_asset(journey: Journey, scenario: Scenario) -> None:
    with Session(engine) as session:
        test_suite = TestSuite(
            journey_id=journey.id,
            name=f"{journey.name} Test Suite",
            generation_run_id=journey.attempt,
        )
        session.add(test_suite)
        session.flush()
        session.add(
            TestAsset(
                scenario_id=scenario.id,
                test_suite_id=test_suite.id,
                code="import { test, expect } from '@playwright/test'\n\ntest('test_guest_checkout', async ({ page }) => {})\n",
            )
        )
        session.commit()


async def _terminate(workflow_id: str) -> None:
    try:
        client = await get_temporal_client()
        await client.get_workflow_handle(workflow_id).terminate(
            reason="pytest cleanup: dev Temporal server is shared, leaked workflows pile up"
        )
    except Exception:
        pass


def test_generate_suite_starts_one_workflow_per_candidate_journey_with_scenarios() -> None:
    init_db()
    client = _signed_in_client("Org Suite Generation")
    application = _create_application(client, "Suite Generation App")
    journey_with_scenarios = _add_candidate_journey(application, "Checkout")
    _add_scenario(journey_with_scenarios)
    # A Journey with zero Scenarios never gets a workflow triggered (nothing
    # to generate), but it must still get a terminal "incomplete" TestSuite
    # row of its own — otherwise the results screen's expected-journey count
    # includes it while `list_test_suites` can never return a matching row,
    # and the frontend spins on the loader forever.
    _add_candidate_journey(application, "Sign up")

    response = client.post(f"/applications/{application['id']}/generate-suite")
    assert response.status_code == 202
    assert response.json() == {"suites_triggered": 1}

    suites = client.get(f"/applications/{application['id']}/test-suites").json()
    sign_up_suite = next(s for s in suites if s["journey_name"] == "Sign up")
    assert sign_up_suite["status"] == "incomplete"
    assert sign_up_suite["test_cases"] == []

    workflow_id = f"suite-{journey_with_scenarios.external_id}-{journey_with_scenarios.attempt}"

    async def _describe() -> str:
        temporal_client = await get_temporal_client()
        description = await temporal_client.get_workflow_handle(workflow_id).describe()
        return description.task_queue

    try:
        assert asyncio.run(_describe()) == GENERATION_TASK_QUEUE
    finally:
        asyncio.run(_terminate(workflow_id))


def test_generate_suite_does_not_recreate_the_zero_scenario_suite_on_a_second_call() -> None:
    init_db()
    client = _signed_in_client("Org Suite Generation Zero Scenario Idempotent")
    application = _create_application(client, "Zero Scenario Idempotent App")
    _add_candidate_journey(application, "Sign up")

    first = client.post(f"/applications/{application['id']}/generate-suite")
    assert first.json() == {"suites_triggered": 0}
    first_suites = client.get(f"/applications/{application['id']}/test-suites").json()
    assert len(first_suites) == 1

    second = client.post(f"/applications/{application['id']}/generate-suite")
    assert second.json() == {"suites_triggered": 0}
    second_suites = client.get(f"/applications/{application['id']}/test-suites").json()
    assert len(second_suites) == 1
    assert second_suites[0]["id"] == first_suites[0]["id"]


def test_generation_status_reports_unavailable_when_worker_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Test Suite Results screen polls this separately from the
    generate-suite trigger, since a worker that crashes right after a
    workflow starts leaves no error for the trigger call to surface — this
    is what lets the frontend stop spinning once the worker is confirmed
    gone instead of polling test-suites forever."""
    from api import main as api_main

    async def _no_pollers(client: object, task_queue: str) -> bool:
        return False

    monkeypatch.setattr(api_main, "has_pollers", _no_pollers)

    init_db()
    client = _signed_in_client("Org Generation Status Down")
    application = _create_application(client, "No Generation Worker Status App")

    response = client.get(f"/applications/{application['id']}/generation-status")

    assert response.status_code == 200
    assert response.json() == {"available": False}


def test_generate_suite_is_idempotent_for_journeys_with_existing_test_suite() -> None:
    init_db()
    client = _signed_in_client("Org Suite Generation Idempotent")
    application = _create_application(client, "Idempotent Suite App")
    journey = _add_candidate_journey(application)
    scenario = _add_scenario(journey)
    _add_test_suite_with_asset(journey, scenario)

    response = client.post(f"/applications/{application['id']}/generate-suite")
    assert response.status_code == 202
    assert response.json() == {"suites_triggered": 0}


def test_generate_suite_resumes_a_journey_with_a_scenario_missing_its_test_asset() -> None:
    # SuiteGenerationWorkflow's own fault isolation (Task 4) lets one
    # Scenario's PlaywrightGenerationActivity exhaust its retries without
    # failing the Journey — so a TestSuite can exist with some Scenarios
    # never getting a TestAsset. Checking "TestSuite exists" alone (as
    # `test_generate_suite_is_idempotent_for_journeys_with_existing_test_suite`
    # covers for the *fully* generated case) made that permanent: re-clicking
    # Generate Suite skipped the Journey forever. It must still trigger here.
    init_db()
    client = _signed_in_client("Org Suite Generation Partial")
    application = _create_application(client, "Partial Suite App")
    journey = _add_candidate_journey(application)
    covered_scenario = _add_scenario(journey, "Guest checkout")
    _add_scenario(journey, "Checkout with a saved card")  # never got a TestAsset
    _add_test_suite_with_asset(journey, covered_scenario)
    workflow_id = f"suite-{journey.external_id}-{journey.attempt}"

    try:
        response = client.post(f"/applications/{application['id']}/generate-suite")
        assert response.status_code == 202
        assert response.json() == {"suites_triggered": 1}
    finally:
        asyncio.run(_terminate(workflow_id))


def test_generate_suite_flips_an_incomplete_suite_back_to_generating_on_retry() -> None:
    # So the results screen's existing loader/polling reappears for this
    # retry instead of the stale "incomplete" status leaving the screen
    # looking finished while a new attempt is actually running underneath.
    init_db()
    client = _signed_in_client("Org Suite Generation Retry")
    application = _create_application(client, "Retry Suite App")
    journey = _add_candidate_journey(application)
    covered_scenario = _add_scenario(journey, "Guest checkout")
    _add_scenario(journey, "Checkout with a saved card")  # never got a TestAsset
    _add_test_suite_with_asset(journey, covered_scenario)
    with Session(engine) as session:
        suite = session.exec(
            select(TestSuite).where(TestSuite.journey_id == journey.id)
        ).one()
        suite.status = "incomplete"
        session.add(suite)
        session.commit()
    workflow_id = f"suite-{journey.external_id}-{journey.attempt}"

    try:
        response = client.post(f"/applications/{application['id']}/generate-suite")
        assert response.json() == {"suites_triggered": 1}

        suites = client.get(f"/applications/{application['id']}/test-suites").json()
        assert suites[0]["status"] == "generating"
    finally:
        asyncio.run(_terminate(workflow_id))


def test_generate_suite_leaves_a_terminated_suite_alone_on_retry() -> None:
    init_db()
    client = _signed_in_client("Org Suite Generation Terminated Retry")
    application = _create_application(client, "Terminated Retry Suite App")
    journey = _add_candidate_journey(application)
    covered_scenario = _add_scenario(journey, "Guest checkout")
    _add_scenario(journey, "Checkout with a saved card")
    _add_test_suite_with_asset(journey, covered_scenario)
    with Session(engine) as session:
        suite = session.exec(
            select(TestSuite).where(TestSuite.journey_id == journey.id)
        ).one()
        suite.status = "terminated"
        session.add(suite)
        session.commit()

    response = client.post(f"/applications/{application['id']}/generate-suite")
    assert response.json() == {"suites_triggered": 0}

    suites = client.get(f"/applications/{application['id']}/test-suites").json()
    assert suites[0]["status"] == "terminated"


def test_generate_suite_starting_twice_only_triggers_once() -> None:
    init_db()
    client = _signed_in_client("Org Suite Generation Twice")
    application = _create_application(client, "Twice Suite App")
    journey = _add_candidate_journey(application)
    _add_scenario(journey)
    workflow_id = f"suite-{journey.external_id}-{journey.attempt}"

    try:
        first = client.post(f"/applications/{application['id']}/generate-suite")
        assert first.json() == {"suites_triggered": 1}

        second = client.post(f"/applications/{application['id']}/generate-suite")
        assert second.json() == {"suites_triggered": 0}
    finally:
        asyncio.run(_terminate(workflow_id))


def test_list_test_suites_returns_journey_scoped_suites_with_test_cases() -> None:
    init_db()
    client = _signed_in_client("Org Suite List")
    application = _create_application(client, "Suite List App")
    journey = _add_candidate_journey(application, "Checkout")
    scenario = _add_scenario(journey, name="Guest checkout")
    _add_test_suite_with_asset(journey, scenario)

    response = client.get(f"/applications/{application['id']}/test-suites")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Checkout Test Suite"
    assert body[0]["journey_name"] == "Checkout"
    assert len(body[0]["test_cases"]) == 1
    assert body[0]["test_cases"][0]["name"] == "Guest checkout"
    assert body[0]["test_cases"][0]["type"] == "happy"
    assert "test_guest_checkout" in body[0]["test_cases"][0]["code"]


def test_list_test_suites_is_organization_scoped() -> None:
    init_db()
    client_a = _signed_in_client("Org Suite List A")
    client_b = _signed_in_client("Org Suite List B")
    application = _create_application(client_a, "Org A Suite App")
    journey = _add_candidate_journey(application)
    scenario = _add_scenario(journey)
    _add_test_suite_with_asset(journey, scenario)

    response = client_b.get(f"/applications/{application['id']}/test-suites")
    assert response.status_code == 404
