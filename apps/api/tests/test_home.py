"""`/home` aggregate endpoint (replaces Home screen's 1+3N-call poll with one).

Requires PostgreSQL + Vault + Temporal reachable, same skip-cleanly convention
as `test_onboarding.py`.
"""

import uuid

import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import DiscoveryRun, Journey, Scenario, TestSuite
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


def _add_scenario(journey: Journey, name: str = "Guest checkout") -> None:
    with Session(engine) as session:
        session.add(
            Scenario(
                journey_id=journey.id,
                type="happy",
                name=name,
                steps=["Add item to cart", "Submit payment"],
                expected_result="Order confirmation is shown",
                test_data=[{"name": "username", "mandatory": True, "value": "qa-user"}],
                generation_run_id=journey.attempt,
            )
        )
        session.commit()


def _add_test_suite(journey: Journey) -> None:
    with Session(engine) as session:
        session.add(
            TestSuite(
                journey_id=journey.id,
                name=f"{journey.name} Test Suite",
                generation_run_id=journey.attempt,
            )
        )
        session.commit()


def test_get_home_returns_counts_scoped_to_org() -> None:
    init_db()
    client = _signed_in_client("Org Home")
    other_org_client = _signed_in_client("Org Home Other")

    application = _create_application(client, "Home App")
    journey = _add_candidate_journey(application)
    _add_scenario(journey, name="Guest checkout")
    _add_scenario(journey, name="Member checkout")
    _add_test_suite(journey)

    other_org_client.post(
        "/applications",
        json={
            "name": "Other Org App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )

    response = client.get("/home")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == application["id"]
    assert body[0]["journey_count"] == 1
    assert body[0]["scenario_count"] == 2
    assert body[0]["suite_count"] == 1
