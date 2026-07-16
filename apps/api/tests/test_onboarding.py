"""Application onboarding tests (Story 1.3 — AD-5, NFR-1, AD-12 reuse).

Requires PostgreSQL + Vault (dev-mode) + Temporal all reachable, same
skip-cleanly convention as `test_scaffold_probe_db.py`.
"""

import asyncio
import logging
import uuid

import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application
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

PLAINTEXT_PASSWORD = "s3cr3t-credential-value"


def _signed_in_client(org_name: str) -> TestClient:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org_name, name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client


def test_create_application_never_stores_plaintext(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    init_db()
    client = _signed_in_client("Org Onboarding")

    response = client.post(
        "/applications",
        json={
            "name": "Test App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": PLAINTEXT_PASSWORD,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["discovery_status"] == "running"
    assert body["discovery_run_id"]

    with Session(engine) as session:
        app_row = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(body["id"]))
        ).first()
        assert app_row is not None
        assert PLAINTEXT_PASSWORD not in app_row.secret_ref

    for record in caplog.records:
        assert PLAINTEXT_PASSWORD not in record.getMessage()


def test_cross_organization_isolation() -> None:
    init_db()
    client_a = _signed_in_client("Org A Isolation")
    client_b = _signed_in_client("Org B Isolation")

    created = client_a.post(
        "/applications",
        json={
            "name": "Org A App",
            "url": "https://a.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )
    assert created.status_code == 201
    application_id = created.json()["id"]

    assert client_a.get(f"/applications/{application_id}").status_code == 200
    assert client_b.get(f"/applications/{application_id}").status_code == 404
