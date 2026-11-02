"""Domain whitelist — admin CRUD, the onboarding gate, and the Applications
list's `domain_approved` flag. DB tests need a live PostgreSQL (same
convention as test_team.py); the matching/validation tests are pure."""

import uuid
from datetime import UTC, datetime

import pytest
from api.approved_domains import host_of, normalize_domain, url_is_approved
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application
from fastapi import HTTPException
from fastapi.testclient import TestClient
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


needs_db = pytest.mark.skipif(
    not _db_available(),
    reason="no PostgreSQL reachable at DATABASE_URL — start docker compose to run this test",
)


@pytest.fixture(autouse=True)
def _domains_approved_by_default() -> None:
    """Shadows conftest's no-op stub so the real check runs here."""


def _client(org_name: str, role: str = "admin") -> TestClient:
    init_db()
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org_name, name="Tester", role=role)
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client


def test_host_of_ignores_scheme_port_path_and_case() -> None:
    assert host_of("HTTPS://Staging.Example.com:8443/app/") == "staging.example.com"
    assert host_of("staging.example.com") == "staging.example.com"
    assert host_of("") is None


def test_subdomains_match_but_lookalikes_do_not() -> None:
    domains = ["example.com"]
    assert url_is_approved("https://example.com", domains)
    assert url_is_approved("https://app.example.com/x", domains)
    assert not url_is_approved("https://notexample.com", domains)
    assert not url_is_approved("https://example.com.evil.io", domains)
    assert not url_is_approved("https://example.com", [])


@pytest.mark.parametrize("raw", ["", "com", "*.example.com", "example.com/app", "bad host.com"])
def test_normalize_domain_rejects_non_domains(raw: str) -> None:
    with pytest.raises(HTTPException) as exc:
        normalize_domain(raw)
    assert exc.value.status_code == 422


def test_normalize_domain_accepts_pasted_url_and_localhost() -> None:
    assert normalize_domain(" https://Example.com:8080/ ") == "example.com"
    assert normalize_domain("localhost") == "localhost"
    assert normalize_domain("10.0.0.5") == "10.0.0.5"


@needs_db
def test_admin_adds_and_deletes_domain_but_cannot_edit() -> None:
    admin = _client("Org Domains CRUD")

    created = admin.post("/domains", json={"host": "Example.com"})
    assert created.status_code == 201
    domain_id = created.json()["id"]
    assert created.json()["host"] == "example.com"
    assert admin.post("/domains", json={"host": "example.com"}).status_code == 409

    assert admin.patch(f"/domains/{domain_id}", json={"host": "example.org"}).status_code == 405

    assert admin.delete(f"/domains/{domain_id}").status_code == 204
    assert admin.get("/domains").json() == []


def _create_app(admin: TestClient, name: str, url: str) -> str | None:
    response = admin.post(
        "/applications",
        json={"name": name, "url": url, "environment": "staging", "username": "u", "password": "p"},
    )
    return response.json()["id"] if response.status_code == 201 else None


def _soft_delete(application_id: str) -> None:
    with Session(engine) as session:
        row = session.exec(select(Application).where(Application.external_id == uuid.UUID(application_id))).one()
        row.deleted_at = datetime.now(UTC)
        session.add(row)
        session.commit()


@needs_db
def test_member_can_read_and_check_but_not_write() -> None:
    member = _client("Org Domains Member", role="member")

    assert member.get("/domains").status_code == 200
    assert member.post("/domains/check", json={"url": "https://a.example.com"}).json() == {
        "allowed": False,
        "host": "a.example.com",
    }
    assert member.post("/domains", json={"host": "example.com"}).status_code == 403


@needs_db
def test_unapproved_domain_is_blocked_then_allowed_once_added() -> None:
    admin = _client("Org Domains Gate")
    url = "https://staging.example.com"

    blocked = admin.post("/applications/test-connection", json={"url": url})
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "DOMAIN_NOT_APPROVED"
    create = admin.post(
        "/applications",
        json={"name": "Gate App", "url": url, "environment": "staging", "username": "u", "password": "p"},
    )
    assert create.status_code == 403
    assert create.json()["detail"] == "DOMAIN_NOT_APPROVED"

    admin.post("/domains", json={"host": "example.com"})

    assert admin.post("/domains/check", json={"url": url}).json()["allowed"] is True
    assert admin.post("/applications/test-connection", json={"url": url}).json()["reachable"] is True


@needs_db
def test_domain_in_use_cannot_be_deleted_until_its_applications_are_gone() -> None:
    admin = _client("Org Domains In Use")
    domain_id = admin.post("/domains", json={"host": "example.com"}).json()["id"]
    app_id = _create_app(admin, "In Use App", "https://in-use.example.com")
    if app_id is None:
        pytest.skip("application creation needs Vault + Temporal")

    row = admin.get("/domains").json()[0]
    assert [a["name"] for a in row["applications"]] == ["In Use App"]

    blocked = admin.delete(f"/domains/{domain_id}")
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "DOMAIN_IN_USE"
    assert [d["host"] for d in admin.get("/domains").json()] == ["example.com"]

    _soft_delete(app_id)

    assert admin.get("/domains").json()[0]["applications"] == []
    assert admin.delete(f"/domains/{domain_id}").status_code == 204


@needs_db
def test_subdomain_entry_can_go_while_a_parent_domain_still_covers_the_app() -> None:
    admin = _client("Org Domains Overlap")
    admin.post("/domains", json={"host": "example.com"})
    sub_id = admin.post("/domains", json={"host": "app.example.com"}).json()["id"]
    if _create_app(admin, "Overlap App", "https://app.example.com") is None:
        pytest.skip("application creation needs Vault + Temporal")

    rows = {d["host"]: d for d in admin.get("/domains").json()}
    assert rows["app.example.com"]["applications"] == []
    assert rows["example.com"]["applications"] == []

    assert admin.delete(f"/domains/{sub_id}").status_code == 204
    # Now the parent is the app's only cover, so it can't go.
    remaining = admin.get("/domains").json()[0]
    assert [a["name"] for a in remaining["applications"]] == ["Overlap App"]
    assert admin.delete(f"/domains/{remaining['id']}").status_code == 409
