"""Discovery Progress live-feed read endpoint (Story 2.2, Task 4/AC 3).

Requires PostgreSQL + Vault + Temporal reachable, same skip-cleanly
convention as `test_onboarding.py`.
"""

import uuid
from datetime import UTC, datetime, timedelta

import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import DiscoveryRun, Evidence
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


def test_list_evidence_returns_newest_first() -> None:
    init_db()
    client = _signed_in_client("Org Evidence Feed")
    application = _create_application(client, "Feed App")

    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        older = Evidence(
            discovery_run_id=discovery_run.id,
            type="page",
            details={"url": "https://staging.example.com/older"},
            captured_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        newer = Evidence(
            discovery_run_id=discovery_run.id,
            type="api_call",
            details={"url": "https://staging.example.com/api/newer"},
            captured_at=datetime.now(UTC),
        )
        session.add(older)
        session.add(newer)
        session.commit()

    response = client.get(f"/discovery-runs/{application['discovery_run_id']}/evidence")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["type"] == "api_call"
    assert body[1]["type"] == "page"


def test_list_evidence_is_organization_scoped() -> None:
    init_db()
    client_a = _signed_in_client("Org Evidence A")
    client_b = _signed_in_client("Org Evidence B")
    application = _create_application(client_a, "Org A App")

    response = client_b.get(f"/discovery-runs/{application['discovery_run_id']}/evidence")
    assert response.status_code == 404
