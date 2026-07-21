"""Discover Journeys read endpoints (Story 3.1) and Rename/Delete (Story 3.4).

Requires PostgreSQL + Vault + Temporal reachable, same skip-cleanly convention
as `test_onboarding.py`. Journeys/JourneySteps are seeded directly against the
DB rather than via a real Discovery Run — InferenceActivity's LLM-backed
inference is out of scope for testing this read/curation slice.
"""

import uuid

import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import DiscoveryRun, Journey, JourneyStep, Page
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


def _add_candidate_journey(application: dict, name: str = "Login") -> str:
    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        page = Page(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            url="https://staging.example.com/login",
            title="Login",
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
        session.flush()

        session.add_all(
            [
                JourneyStep(
                    journey_id=journey.id, page_id=page.id, step_order=1, stage_label="Login"
                ),
                JourneyStep(
                    journey_id=journey.id,
                    page_id=page.id,
                    step_order=2,
                    stage_label="MFA Verification",
                ),
            ]
        )
        session.commit()
        session.refresh(journey)
        return str(journey.external_id)


def test_list_journeys_returns_name_and_step_count() -> None:
    init_db()
    client = _signed_in_client("Org Journey List")
    application = _create_application(client, "Journey List App")
    _add_candidate_journey(application, name="Checkout")

    response = client.get(f"/applications/{application['id']}/journeys")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Checkout"
    assert body[0]["step_count"] == 2
    assert "confidence" not in body[0]
    assert "risk" not in body[0]


def test_list_journeys_excludes_deleted() -> None:
    init_db()
    client = _signed_in_client("Org Journey Excludes Deleted")
    application = _create_application(client, "Excludes Deleted App")
    journey_id = _add_candidate_journey(application)

    assert client.delete(f"/journeys/{journey_id}").status_code == 204
    response = client.get(f"/applications/{application['id']}/journeys")
    assert response.json() == []


def test_list_journeys_is_organization_scoped() -> None:
    init_db()
    client_a = _signed_in_client("Org Journey List A")
    client_b = _signed_in_client("Org Journey List B")
    application = _create_application(client_a, "Org A Journey App")
    _add_candidate_journey(application)

    response = client_b.get(f"/applications/{application['id']}/journeys")
    assert response.status_code == 404


def test_journey_steps_returns_ordered_route_method_stage_label() -> None:
    init_db()
    client = _signed_in_client("Org Journey Steps")
    application = _create_application(client, "Journey Steps App")
    journey_id = _add_candidate_journey(application)

    response = client.get(f"/journeys/{journey_id}/steps")
    assert response.status_code == 200
    body = response.json()
    assert [s["stage_label"] for s in body] == ["Login", "MFA Verification"]
    assert body[0]["route"] == "https://staging.example.com/login"
    assert body[0]["method"] == "GET"


def test_rename_journey_updates_name() -> None:
    init_db()
    client = _signed_in_client("Org Journey Rename")
    application = _create_application(client, "Journey Rename App")
    journey_id = _add_candidate_journey(application, name="Old Name")

    response = client.patch(f"/journeys/{journey_id}", json={"name": "New Name"})
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"

    listed = client.get(f"/applications/{application['id']}/journeys").json()
    assert listed[0]["name"] == "New Name"


def test_rename_already_deleted_journey_is_rejected() -> None:
    init_db()
    client = _signed_in_client("Org Journey Rename Deleted")
    application = _create_application(client, "Journey Rename Deleted App")
    journey_id = _add_candidate_journey(application)

    assert client.delete(f"/journeys/{journey_id}").status_code == 204
    response = client.patch(f"/journeys/{journey_id}", json={"name": "New Name"})
    assert response.status_code == 409


def test_delete_already_deleted_journey_is_rejected() -> None:
    init_db()
    client = _signed_in_client("Org Journey Delete Twice")
    application = _create_application(client, "Journey Delete Twice App")
    journey_id = _add_candidate_journey(application)

    assert client.delete(f"/journeys/{journey_id}").status_code == 204
    assert client.delete(f"/journeys/{journey_id}").status_code == 409


def test_journey_curation_is_organization_scoped() -> None:
    init_db()
    client_a = _signed_in_client("Org Journey Curation A")
    client_b = _signed_in_client("Org Journey Curation B")
    application = _create_application(client_a, "Org A Curation App")
    journey_id = _add_candidate_journey(application)

    assert client_b.patch(f"/journeys/{journey_id}", json={"name": "Hijacked"}).status_code == 404
    assert client_b.delete(f"/journeys/{journey_id}").status_code == 404
