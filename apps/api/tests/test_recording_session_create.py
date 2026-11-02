"""Minting a Record and Play session: an Application connected with sign-in
turned off (`auth_method="none"`) has no stored credential to start signed in
with, so only a logged-out recording is accepted for it."""

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
    except SQLAlchemyError, OSError:
        return False


def _vault_available() -> bool:
    try:
        return hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN).sys.is_initialized()
    except VaultError, OSError:
        return False


pytestmark = pytest.mark.skipif(
    not (_db_available() and _vault_available()),
    reason="requires PostgreSQL + Vault reachable — start docker compose",
)


def _signed_in_client() -> TestClient:
    init_db()
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name="Org Recording Sessions", name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client


def _application(client: TestClient, *, sign_in: bool) -> str:
    credentials = (
        {"auth_method": "standard_login", "username": "qa-test-account", "password": "x"}
        if sign_in
        else {"auth_method": "none"}
    )
    response = client.post(
        "/applications",
        json={
            "name": "Recording App",
            "url": "https://staging.example.com",
            "environment": "staging",
            **credentials,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _mint(client: TestClient, app_id: str, auth_mode: str) -> int:
    return client.post(
        f"/applications/{app_id}/recordings/sessions",
        json={"auth_mode": auth_mode, "name": "Browse"},
    ).status_code


def test_no_sign_in_app_rejects_an_authenticated_recording() -> None:
    client = _signed_in_client()
    assert _mint(client, _application(client, sign_in=False), "authenticated") == 422


def test_no_sign_in_app_records_logged_out() -> None:
    client = _signed_in_client()
    assert _mint(client, _application(client, sign_in=False), "logged_out") == 201


def test_sign_in_app_still_records_authenticated() -> None:
    client = _signed_in_client()
    assert _mint(client, _application(client, sign_in=True), "authenticated") == 201
