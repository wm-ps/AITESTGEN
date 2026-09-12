"""`/overview-stats` — org-wide aggregates for Global overview's "Avg run
duration" and "Self-healed locators" prototype sidebar cards.

Requires PostgreSQL + Vault + Temporal reachable, same skip-cleanly
convention as `test_home.py`.
"""

import uuid
from datetime import UTC, datetime, timedelta

import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import (
    Application,
    DiscoveryRun,
    Journey,
    Scenario,
    TestAsset,
    TestResult,
    TestRun,
    TestSuite,
)
from fastapi.testclient import TestClient
from hvac.exceptions import VaultError
from secrets_client.vault_client import VAULT_ADDR, VAULT_TOKEN
from sqlalchemy import func, text
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


def _seed_test_asset(application: dict) -> tuple[uuid.UUID, TestAsset]:
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
        session.commit()
        session.refresh(test_asset)
        return discovery_run.application_id, test_asset


def _seed_completed_run(application_id: uuid.UUID, *, duration_seconds: float) -> TestRun:
    with Session(engine) as session:
        existing_count = session.exec(
            select(func.count()).where(TestRun.application_id == application_id)
        ).one()
        started = datetime.now(UTC) - timedelta(seconds=duration_seconds)
        test_run = TestRun(
            application_id=application_id,
            run_number=existing_count + 1,
            status="completed",
            environment_snapshot="staging",
            target_base_url_snapshot="https://staging.example.com",
            total_count=1,
            passed_count=1,
            started_at=started,
            completed_at=started + timedelta(seconds=duration_seconds),
        )
        session.add(test_run)
        session.commit()
        session.refresh(test_run)
        return test_run


def test_get_overview_stats_is_zeroed_for_an_org_with_no_applications() -> None:
    init_db()
    client = _signed_in_client("Org Overview Stats Empty")

    body = client.get("/overview-stats").json()
    assert body["avg_run_duration_ms"] is None
    assert body["run_count"] == 0
    assert body["self_healed_count"] == 0


def test_get_overview_stats_averages_completed_run_durations() -> None:
    init_db()
    client = _signed_in_client("Org Overview Stats Duration")
    application = _create_application(client, "Duration App")
    app_id, _ = _seed_test_asset(application)

    _seed_completed_run(app_id, duration_seconds=60)
    _seed_completed_run(app_id, duration_seconds=120)

    body = client.get("/overview-stats").json()
    assert body["run_count"] == 2
    assert body["avg_run_duration_ms"] == pytest.approx(90_000, rel=0.01)


def test_get_overview_stats_counts_self_healed_results_within_7_days() -> None:
    init_db()
    client = _signed_in_client("Org Overview Stats Healed")
    application = _create_application(client, "Healed App")
    app_id, asset = _seed_test_asset(application)
    test_run = _seed_completed_run(app_id, duration_seconds=30)

    with Session(engine) as session:
        # Healed, recent — counted.
        session.add(
            TestResult(
                test_run_id=test_run.id,
                test_asset_id=asset.id,
                scenario_id=asset.scenario_id,
                status="passed",
                healed_test_asset_id=asset.id,
                completed_at=datetime.now(UTC),
            )
        )
        # Healed, outside the 7-day window — not counted.
        session.add(
            TestResult(
                test_run_id=test_run.id,
                test_asset_id=asset.id,
                scenario_id=asset.scenario_id,
                status="passed",
                healed_test_asset_id=asset.id,
                completed_at=datetime.now(UTC) - timedelta(days=8),
            )
        )
        # Never healed — not counted.
        session.add(
            TestResult(
                test_run_id=test_run.id,
                test_asset_id=asset.id,
                scenario_id=asset.scenario_id,
                status="passed",
                completed_at=datetime.now(UTC),
            )
        )
        session.commit()

    body = client.get("/overview-stats").json()
    assert body["self_healed_count"] == 1


def test_get_overview_stats_scoped_to_org() -> None:
    init_db()
    client = _signed_in_client("Org Overview Stats Scope A")
    other_client = _signed_in_client("Org Overview Stats Scope B")
    application = _create_application(other_client, "Other Org App")
    app_id, _ = _seed_test_asset(application)
    _seed_completed_run(app_id, duration_seconds=45)

    body = client.get("/overview-stats").json()
    assert body["run_count"] == 0
    assert body["avg_run_duration_ms"] is None
