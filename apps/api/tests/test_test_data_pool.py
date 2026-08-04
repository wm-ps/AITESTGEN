"""Test Data Pool CRUD (Story 2.20). Requires PostgreSQL + Vault + Temporal
reachable, same skip-cleanly convention as `test_journey_curation.py`.
"""

import uuid

import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from fastapi.testclient import TestClient
from hvac.exceptions import VaultError
from secrets_client.vault_client import VAULT_ADDR, VAULT_TOKEN
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


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


def test_create_and_list_non_sensitive_entry() -> None:
    init_db()
    client = _signed_in_client("Org Pool List")
    application = _create_application(client, "Pool List App")

    response = client.post(
        f"/applications/{application['id']}/test-data",
        json={"label": "Policy Number", "field_name": "Policy Number", "value": "ABC-123"},
    )
    assert response.status_code == 201
    created = response.json()
    assert created["value"] == "ABC-123"
    assert created["is_sensitive"] is False

    listed = client.get(f"/applications/{application['id']}/test-data").json()
    assert len(listed) == 1
    assert listed[0]["label"] == "Policy Number"


def test_sensitive_entry_value_is_never_returned() -> None:
    init_db()
    client = _signed_in_client("Org Pool Sensitive")
    application = _create_application(client, "Pool Sensitive App")

    response = client.post(
        f"/applications/{application['id']}/test-data",
        json={
            "label": "API Key",
            "field_name": "API Key",
            "value": "super-secret-value",
            "is_sensitive": True,
        },
    )
    assert response.status_code == 201
    created = response.json()
    assert created["value"] is None
    assert created["is_sensitive"] is True

    listed = client.get(f"/applications/{application['id']}/test-data").json()
    assert listed[0]["value"] is None


def test_duplicate_normalized_key_is_rejected() -> None:
    init_db()
    client = _signed_in_client("Org Pool Dup")
    application = _create_application(client, "Pool Dup App")

    payload = {"label": "Policy Number", "field_name": "Policy Number", "value": "ABC-123"}
    first = client.post(f"/applications/{application['id']}/test-data", json=payload)
    assert first.status_code == 201
    second = client.post(f"/applications/{application['id']}/test-data", json=payload)
    assert second.status_code == 409


def test_update_and_delete_entry() -> None:
    init_db()
    client = _signed_in_client("Org Pool Update")
    application = _create_application(client, "Pool Update App")
    created = client.post(
        f"/applications/{application['id']}/test-data",
        json={"label": "Coupon", "field_name": "Coupon", "value": "SAVE10"},
    ).json()

    updated = client.patch(f"/test-data/{created['id']}", json={"value": "SAVE20"})
    assert updated.status_code == 200
    assert updated.json()["value"] == "SAVE20"

    deleted = client.delete(f"/test-data/{created['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/applications/{application['id']}/test-data").json() == []


def test_entry_from_another_organization_is_not_visible() -> None:
    init_db()
    owner = _signed_in_client("Org Pool Owner")
    application = _create_application(owner, "Pool Owner App")
    created = owner.post(
        f"/applications/{application['id']}/test-data",
        json={"label": "Secret Field", "field_name": "Secret Field", "value": "x"},
    ).json()

    other = _signed_in_client("Org Pool Intruder")
    assert other.get(f"/applications/{application['id']}/test-data").status_code == 404
    assert other.patch(f"/test-data/{created['id']}", json={"value": "y"}).status_code == 404
    assert other.delete(f"/test-data/{created['id']}").status_code == 404
