"""POST /test-results/{id}/heal — manual "Retry with self-heal". Eligibility
checks here must mirror `heal_test_activity`'s own no-op condition exactly
(same HEALABLE_STATUSES, same DiscoverySettings.max_heal_attempts, same
HEAL_CLAIM_STALE_AFTER staleness window) so this endpoint's 409s and the
activity's own behavior never disagree — see that shared reasoning in
apps/api/src/api/main.py::heal_test_result.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from api.db import engine, init_db
from api.scripts.seed_dev_data import seed
from api.temporal_client import get_temporal_client
from domain import (
    Application,
    DiscoveryRun,
    DiscoverySettings,
    Journey,
    Organization,
    Scenario,
    TestAsset,
    TestResult,
    TestRun,
    TestSuite,
)
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from api.main import app


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
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
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
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
            "auth_method": "standard_login",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )
    assert response.status_code == 201
    return response.json()


def _seed_test_result(application: dict, **overrides) -> TestResult:
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
            name="Completes checkout",
            steps=["Add item to cart"],
            expected_result="Order confirmed",
            test_data=[],
            generation_run_id=journey.attempt,
        )
        session.add(scenario)
        session.flush()
        test_suite = TestSuite(
            journey_id=journey.id, name="Checkout Test Suite", generation_run_id=journey.attempt
        )
        session.add(test_suite)
        session.flush()
        test_asset = TestAsset(scenario_id=scenario.id, test_suite_id=test_suite.id, code="// spec\n")
        session.add(test_asset)
        session.flush()
        test_run = TestRun(
            application_id=discovery_run.application_id,
            run_number=1,
            status="completed",
            environment_snapshot="staging",
            target_base_url_snapshot="https://staging.example.com",
        )
        session.add(test_run)
        session.flush()
        defaults = dict(
            test_run_id=test_run.id,
            test_asset_id=test_asset.id,
            scenario_id=scenario.id,
            status="failed",
            error_message="Timed out 15000ms waiting for expect(locator).toBeVisible()",
        )
        defaults.update(overrides)
        test_result = TestResult(**defaults)
        session.add(test_result)
        session.commit()
        session.refresh(test_result)
        return test_result


def _set_max_heal_attempts(value: int) -> None:
    with Session(engine) as session:
        settings = session.exec(select(DiscoverySettings)).one()
        settings.max_heal_attempts = value
        session.add(settings)
        session.commit()


def test_heal_returns_404_for_unknown_test_result() -> None:
    init_db()
    client = _signed_in_client("Org Heal 404")
    _create_application(client, "App")

    response = client.post(f"/test-results/{uuid.uuid4()}/heal")

    assert response.status_code == 404


def test_heal_returns_404_for_a_result_in_another_organization() -> None:
    init_db()
    owner_client = _signed_in_client("Org Heal Owner")
    owner_app = _create_application(owner_client, "Owner App")
    result = _seed_test_result(owner_app)

    other_client = _signed_in_client("Org Heal Other")
    _create_application(other_client, "Other App")

    response = other_client.post(f"/test-results/{result.external_id}/heal")

    assert response.status_code == 404


def test_heal_returns_409_when_status_is_not_healable() -> None:
    init_db()
    client = _signed_in_client("Org Heal Passed")
    application = _create_application(client, "Passed App")
    result = _seed_test_result(application, status="passed", error_message=None)

    response = client.post(f"/test-results/{result.external_id}/heal")

    assert response.status_code == 409


def test_heal_returns_409_when_attempt_budget_already_spent() -> None:
    init_db()
    _set_max_heal_attempts(3)
    client = _signed_in_client("Org Heal Exhausted")
    application = _create_application(client, "Exhausted App")
    result = _seed_test_result(application, status="failed", heal_attempt_count=3)

    response = client.post(f"/test-results/{result.external_id}/heal")

    assert response.status_code == 409


def test_heal_returns_409_when_a_heal_is_already_in_progress() -> None:
    init_db()
    client = _signed_in_client("Org Heal In Progress")
    application = _create_application(client, "In Progress App")
    result = _seed_test_result(
        application, status="failed", heal_started_at=datetime.now(UTC) - timedelta(minutes=5)
    )

    response = client.post(f"/test-results/{result.external_id}/heal")

    assert response.status_code == 409


@pytest.mark.skipif(not _temporal_available(), reason="requires Temporal reachable")
def test_heal_allows_retry_once_a_prior_claim_is_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    """A worker that crashed mid-heal without clearing `heal_started_at`
    must not permanently block a later manual retry."""
    from api import main as api_main

    async def _no_pollers(client: object, task_queue: str) -> bool:
        return False

    monkeypatch.setattr(api_main, "has_pollers", _no_pollers)

    init_db()
    _set_max_heal_attempts(3)
    client = _signed_in_client("Org Heal Stale Claim")
    application = _create_application(client, "Stale Claim App")
    result = _seed_test_result(
        application, status="failed", heal_started_at=datetime.now(UTC) - timedelta(hours=1)
    )

    response = client.post(f"/test-results/{result.external_id}/heal")

    # Not a 409 — the staleness window means this is treated as eligible.
    # 503 here just reflects no execution worker polling in this test env
    # (has_pollers patched to False above, same convention as
    # test_test_runs.py's own worker-down test).
    assert response.status_code != 409
    assert response.status_code == 503


@pytest.mark.skipif(not _temporal_available(), reason="requires Temporal reachable")
def test_heal_starts_workflow_for_an_eligible_result() -> None:
    init_db()
    _set_max_heal_attempts(3)
    client = _signed_in_client("Org Heal Eligible")
    application = _create_application(client, "Eligible App")
    result = _seed_test_result(application, status="failed")

    response = client.post(f"/test-results/{result.external_id}/heal")

    assert response.status_code == 202
    assert response.json() == {"started": True}


@pytest.mark.skipif(not _temporal_available(), reason="requires Temporal reachable")
def test_heal_duplicate_click_is_not_an_error() -> None:
    """Deterministic workflow id (`heal-{id}`) — a rapid double-click hits
    WorkflowAlreadyStartedError, treated as already-in-progress, not a
    failure."""
    init_db()
    _set_max_heal_attempts(3)
    client = _signed_in_client("Org Heal Double Click")
    application = _create_application(client, "Double Click App")
    result = _seed_test_result(application, status="failed")

    first = client.post(f"/test-results/{result.external_id}/heal")
    # Reset the claim so the second call reaches workflow-start, not the
    # in-progress 409 — isolating this test to the WorkflowAlreadyStartedError
    # path specifically.
    with Session(engine) as session:
        row = session.exec(select(TestResult).where(TestResult.id == result.id)).one()
        row.heal_started_at = None
        session.add(row)
        session.commit()
    second = client.post(f"/test-results/{result.external_id}/heal")

    assert first.status_code == 202
    assert second.status_code == 202
