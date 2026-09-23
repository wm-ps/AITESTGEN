"""Application Context — persistent, user-authored application knowledge,
shown in the UI as "Notes" (business goal, business domain, business rules,
additional context).

Requires PostgreSQL + Vault + Temporal reachable, same skip-cleanly
convention as `test_onboarding.py`.
"""

import asyncio
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


def _signed_in_client(org_name: str, role: str = "admin") -> TestClient:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org_name, name="Tester", role=role)
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


def test_application_context_can_be_set_during_onboarding() -> None:
    """Option A: Notes provided in the "Add application" form must already
    be on the row before discovery's first `InferenceActivity` run ever
    sees it — i.e. set synchronously inside `create_application`, not added
    later via a second call."""
    init_db()
    client = _signed_in_client("Org Application Context Onboarding")

    response = client.post(
        "/applications",
        json={
            "name": "Onboarding Notes App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": "irrelevant",
            "application_context": {
                "business_goal": "Manage clients, accounts and investments.",
                "business_rules": ["A Tenant must be selected before its Engagements become available."],
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["application_context"] == {
        "business_goal": "Manage clients, accounts and investments.",
        "business_domain": None,
        "business_rules": ["A Tenant must be selected before its Engagements become available."],
        "additional_context": None,
    }

    # The real assertion this feature exists for: the row already carries
    # it at creation time, before any Notes-tab PATCH could ever happen —
    # available to InferenceActivity's very first run.
    with Session(engine) as session:
        row = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(body["id"]))
        ).one()
        assert row.application_context["business_goal"] == "Manage clients, accounts and investments."


def test_application_context_is_optional_during_onboarding() -> None:
    """Backward compatibility: omitting it in the create payload must
    behave exactly as before this field existed."""
    init_db()
    client = _signed_in_client("Org Application Context Onboarding Optional")

    response = client.post(
        "/applications",
        json={
            "name": "No Notes App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )

    assert response.status_code == 201
    assert response.json()["application_context"] is None


def test_view_add_edit_and_save_application_context() -> None:
    init_db()
    client = _signed_in_client("Org Application Context")
    application_id = _create_application(client, "Context App")["id"]

    # No context saved yet — existing applications must continue working
    # exactly as before this feature existed.
    read = client.get(f"/applications/{application_id}")
    assert read.json()["application_context"] is None

    save = client.patch(
        f"/applications/{application_id}/context",
        json={
            "business_goal": "Manage clients, accounts and investments.",
            "business_rules": ["Engagements shown depend on the selected tenant."],
        },
    )
    assert save.status_code == 200
    assert save.json()["application_context"] == {
        "business_goal": "Manage clients, accounts and investments.",
        "business_domain": None,
        "business_rules": ["Engagements shown depend on the selected tenant."],
        "additional_context": None,
    }

    # Save -> reload — the next read sees the same, persisted context.
    reread = client.get(f"/applications/{application_id}")
    assert reread.json()["application_context"]["business_goal"] == (
        "Manage clients, accounts and investments."
    )


def test_updating_application_context_replaces_the_previous_saved_content() -> None:
    """The user can update context at any time; the next read sees the
    latest saved version, never a stale one."""
    init_db()
    client = _signed_in_client("Org Application Context Update")
    application_id = _create_application(client, "Context Update App")["id"]

    client.patch(
        f"/applications/{application_id}/context",
        json={"business_rules": ["Engagement depends on Tenant."]},
    )

    updated = client.patch(
        f"/applications/{application_id}/context",
        json={
            "business_rules": [
                "Engagement depends on Tenant.",
                "Changing Tenant clears the currently selected Engagement.",
            ]
        },
    )

    assert updated.json()["application_context"]["business_rules"] == [
        "Engagement depends on Tenant.",
        "Changing Tenant clears the currently selected Engagement.",
    ]


def test_partial_application_context_is_accepted() -> None:
    init_db()
    client = _signed_in_client("Org Application Context Partial")
    application_id = _create_application(client, "Context Partial App")["id"]

    response = client.patch(
        f"/applications/{application_id}/context",
        json={"business_goal": "Only the goal, nothing else."},
    )

    assert response.status_code == 200
    body = response.json()["application_context"]
    assert body["business_goal"] == "Only the goal, nothing else."
    assert body["business_rules"] is None


def test_empty_application_context_payload_clears_stored_context() -> None:
    init_db()
    client = _signed_in_client("Org Application Context Clear")
    application_id = _create_application(client, "Context Clear App")["id"]
    client.patch(
        f"/applications/{application_id}/context",
        json={"business_goal": "Will be cleared."},
    )

    cleared = client.patch(f"/applications/{application_id}/context", json={})

    assert cleared.status_code == 200
    assert cleared.json()["application_context"] is None
    with Session(engine) as session:
        row = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(application_id))
        ).one()
        assert row.application_context is None


def test_update_application_context_requires_admin() -> None:
    init_db()
    admin_client = _signed_in_client("Org Application Context Non Admin")
    application_id = _create_application(admin_client, "Non Admin Context App")["id"]

    member_client = _signed_in_client("Org Application Context Non Admin", role="member")
    response = member_client.patch(
        f"/applications/{application_id}/context",
        json={"business_goal": "attempt"},
    )

    assert response.status_code == 403


def test_application_context_is_isolated_per_application() -> None:
    """Critical: Application A's context must never leak into Application
    B's response, even within the same organization."""
    init_db()
    client = _signed_in_client("Org Application Context Isolation")
    app_a = _create_application(client, "Context App A")["id"]
    app_b = _create_application(client, "Context App B")["id"]

    client.patch(
        f"/applications/{app_a}/context",
        json={"business_goal": "App A's own business goal."},
    )

    app_b_read = client.get(f"/applications/{app_b}")
    assert app_b_read.json()["application_context"] is None


def test_application_context_field_over_2000_characters_is_rejected() -> None:
    init_db()
    client = _signed_in_client("Org Application Context Too Long")
    application_id = _create_application(client, "Context Too Long App")["id"]

    response = client.patch(
        f"/applications/{application_id}/context",
        json={"business_goal": "x" * 2001},
    )

    assert response.status_code == 422


def test_business_rules_over_2000_joined_characters_is_rejected() -> None:
    init_db()
    client = _signed_in_client("Org Application Context Rules Too Long")
    application_id = _create_application(client, "Context Rules Too Long App")["id"]

    response = client.patch(
        f"/applications/{application_id}/context",
        json={"business_rules": ["x" * 1000, "y" * 1002]},
    )

    assert response.status_code == 422


def test_application_context_never_exposes_credentials() -> None:
    init_db()
    client = _signed_in_client("Org Application Context No Creds")
    application_id = _create_application(client, "Context No Creds App")["id"]

    save = client.patch(
        f"/applications/{application_id}/context",
        json={"additional_context": "Login uses the shared QA account."},
    )

    assert "secret_ref" not in save.json()
    assert "password" not in save.text
