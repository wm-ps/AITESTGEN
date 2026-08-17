"""Application onboarding tests (Story 1.3 — AD-5, NFR-1, AD-12 reuse).

Requires PostgreSQL + Vault (dev-mode) + Temporal all reachable, same
skip-cleanly convention as `test_scaffold_probe_db.py`.
"""

import asyncio
import json
import logging
import uuid

import httpx
import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application, DiscoveryRun
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
PLAINTEXT_SESSION_TOKEN = "s3cr3t-session-token-value"


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


def test_create_application_strips_leading_trailing_credential_whitespace() -> None:
    """A copy-paste artifact (stray leading/trailing space) silently breaks
    login at the target app with no useful error anywhere downstream — must
    be stripped before the credential is persisted. An internal space is a
    real part of the credential and must survive untouched."""
    init_db()
    client = _signed_in_client("Org Credential Whitespace")

    response = client.post(
        "/applications",
        json={
            "name": "Whitespace Creds App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": " alice smith ",
            "password": f"  {PLAINTEXT_PASSWORD}\t",
        },
    )

    assert response.status_code == 201
    body = response.json()

    with Session(engine) as session:
        app_row = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(body["id"]))
        ).first()
        assert app_row is not None
        from secrets_client.vault_client import SecretRef, VaultSecretsClient

        stored = json.loads(
            VaultSecretsClient().resolve(SecretRef(path=app_row.secret_ref)).decode()
        )
        assert stored == {"username": "alice smith", "password": PLAINTEXT_PASSWORD}


def test_create_application_defaults_to_standard_login() -> None:
    init_db()
    client = _signed_in_client("Org Auth Method Default")

    response = client.post(
        "/applications",
        json={
            "name": "Default Auth App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": PLAINTEXT_PASSWORD,
        },
    )

    assert response.status_code == 201
    assert response.json()["auth_method"] == "standard_login"


def test_list_applications_scopes_to_org_and_orders_newest_first() -> None:
    init_db()
    client = _signed_in_client("Org List Applications")
    other_org_client = _signed_in_client("Org List Applications Other")

    other_org_client.post(
        "/applications",
        json={
            "name": "Other Org App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": PLAINTEXT_PASSWORD,
        },
    )
    client.post(
        "/applications",
        json={
            "name": "First App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": PLAINTEXT_PASSWORD,
        },
    )
    client.post(
        "/applications",
        json={
            "name": "Second App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": PLAINTEXT_PASSWORD,
        },
    )

    response = client.get("/applications")

    assert response.status_code == 200
    names = [app["name"] for app in response.json()]
    assert names == ["Second App", "First App"]
    assert "Other Org App" not in names


def test_create_application_standard_login_requires_credentials() -> None:
    init_db()
    client = _signed_in_client("Org Auth Method Missing Creds")

    response = client.post(
        "/applications",
        json={
            "name": "Missing Creds App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "auth_method": "standard_login",
        },
    )

    assert response.status_code == 422


def test_create_application_sso_session_reuse_stores_session_state_never_plaintext(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    init_db()
    client = _signed_in_client("Org SSO Session Reuse")
    session_state = json.dumps({"cookies": [{"name": "sid", "value": PLAINTEXT_SESSION_TOKEN}]})

    response = client.post(
        "/applications",
        json={
            "name": "SSO App",
            "url": "https://sso.example.com",
            "environment": "staging",
            "auth_method": "sso_session_reuse",
            "session_state": session_state,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["auth_method"] == "sso_session_reuse"

    with Session(engine) as session:
        app_row = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(body["id"]))
        ).first()
        assert app_row is not None
        assert app_row.auth_method == "sso_session_reuse"
        assert PLAINTEXT_SESSION_TOKEN not in app_row.secret_ref

    for record in caplog.records:
        assert PLAINTEXT_SESSION_TOKEN not in record.getMessage()


def test_create_application_sso_session_reuse_requires_session_state() -> None:
    init_db()
    client = _signed_in_client("Org SSO Missing Session State")

    response = client.post(
        "/applications",
        json={
            "name": "SSO App Missing State",
            "url": "https://sso.example.com",
            "environment": "staging",
            "auth_method": "sso_session_reuse",
        },
    )

    assert response.status_code == 422


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


# --- FR-31 (CR-3) — reachability validation ---
# httpx never touches the network here — a fake AsyncClient stands in so these
# tests exercise `_check_reachable`'s branching, not real DNS.


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeAsyncClient:
    def __init__(
        self,
        *,
        unreachable: bool = False,
        head_status: int = 200,
        get_status: int = 200,
        **_kwargs: object,
    ) -> None:
        self._unreachable = unreachable
        self._head_status = head_status
        self._get_status = get_status

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def head(self, url: str) -> _FakeResponse:
        if self._unreachable:
            raise httpx.RequestError("simulated network failure")
        return _FakeResponse(self._head_status)

    async def get(self, url: str) -> _FakeResponse:
        if self._unreachable:
            raise httpx.RequestError("simulated network failure")
        return _FakeResponse(self._get_status)


@pytest.fixture(autouse=True)
def _reachable_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this module posts a synthetic `*.example.com` URL that
    isn't actually reachable — stub httpx.AsyncClient to treat it as
    reachable by default (FR-31) so the tests above (predating this CR)
    don't become flaky/networked. Tests that exercise the reachability check
    itself override this via their own `monkeypatch.setattr` call below,
    which simply wins (last write to the same attribute)."""
    monkeypatch.setattr("api.main.httpx.AsyncClient", lambda **kwargs: _FakeAsyncClient())


def _post_application(client: TestClient, name: str, url: str = "https://app.example.com"):
    return client.post(
        "/applications",
        json={
            "name": name,
            "url": url,
            "environment": "staging",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )


def test_create_application_rejects_unreachable_url(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db()
    monkeypatch.setattr(
        "api.main.httpx.AsyncClient", lambda **kwargs: _FakeAsyncClient(unreachable=True)
    )
    client = _signed_in_client("Org Unreachable URL")

    response = _post_application(client, "Unreachable App")

    assert response.status_code == 422
    assert "did not respond" in response.json()["detail"]
    with Session(engine) as session:
        assert (
            session.exec(select(Application).where(Application.name == "Unreachable App")).first()
            is None
        )


def test_create_application_rejects_url_returning_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db()
    monkeypatch.setattr(
        "api.main.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(head_status=500, get_status=500),
    )
    client = _signed_in_client("Org 5xx URL")

    response = _post_application(client, "Broken App")

    assert response.status_code == 422
    with Session(engine) as session:
        assert (
            session.exec(select(Application).where(Application.name == "Broken App")).first()
            is None
        )


def test_create_application_stores_and_returns_login_url() -> None:
    init_db()
    client = _signed_in_client("Org Login URL")

    response = client.post(
        "/applications",
        json={
            "name": "Login URL App",
            "url": "https://app.example.com",
            "login_url": "https://app.example.com/login",
            "environment": "staging",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )

    assert response.status_code == 201
    assert response.json()["login_url"] == "https://app.example.com/login"
    with Session(engine) as session:
        app_row = session.exec(
            select(Application).where(Application.name == "Login URL App")
        ).first()
        assert app_row is not None
        assert app_row.login_url == "https://app.example.com/login"


def test_create_application_never_reachability_checks_login_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """login_url is a navigation hint for the worker, not a health check
    target — a login page can legitimately 500 without prior session state
    (the shopbit.onwavemaker.com case that motivated this field). Only `url`
    may gate creation."""
    init_db()
    login_url = "https://app.example.com/login"

    class _RejectsLoginUrlClient(_FakeAsyncClient):
        async def head(self, url: str) -> _FakeResponse:
            if url == login_url:
                raise httpx.RequestError("login_url must never be reachability-checked")
            return await super().head(url)

        async def get(self, url: str) -> _FakeResponse:
            if url == login_url:
                raise httpx.RequestError("login_url must never be reachability-checked")
            return await super().get(url)

    monkeypatch.setattr("api.main.httpx.AsyncClient", lambda **kwargs: _RejectsLoginUrlClient())
    client = _signed_in_client("Org Login URL Not Checked")

    response = client.post(
        "/applications",
        json={
            "name": "Login URL Not Checked App",
            "url": "https://app.example.com",
            "login_url": login_url,
            "environment": "staging",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )

    assert response.status_code == 201


def test_create_application_sets_discovery_stage_initializing() -> None:
    """Story 2.1 (CR-2): DiscoveryRun.stage is set to "initializing" in the
    same request, round-tripping through ApplicationRead.discovery_stage."""
    init_db()
    client = _signed_in_client("Org Discovery Stage")

    response = _post_application(client, "Stage App")

    assert response.status_code == 201
    assert response.json()["discovery_stage"] == "initializing"


def test_create_application_reports_worker_unavailable_when_discovery_queue_has_no_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API up + Temporal up + zero discovery workers polling the queue must
    not look identical to a normal in-progress discovery run (starting a
    workflow succeeds either way) — it should fail fast with a
    `failure_reason` the frontend can recognize and show distinctly, instead
    of the DiscoveryRun sitting at "running" forever with nothing to explain
    why."""
    from api import discovery as api_discovery

    async def _no_pollers(client: object, task_queue: str) -> bool:
        return False

    monkeypatch.setattr(api_discovery, "has_pollers", _no_pollers)

    init_db()
    client = _signed_in_client("Org Discovery Worker Down")

    response = _post_application(client, "No Worker App")

    assert response.status_code == 201
    body = response.json()
    assert body["discovery_status"] == "failed"
    assert body["discovery_failure_reason"] == "worker_unavailable"


def test_discovery_status_reports_unavailable_when_worker_crashes_mid_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`has_pollers` is only checked once, before the workflow starts — a
    worker that crashes right after leaves discovery_status="running" with
    nothing to explain why it's stuck. This is the separate mid-run check
    the frontend polls to tell that apart from a discovery genuinely still
    in progress."""
    init_db()
    client = _signed_in_client("Org Discovery Status Down")

    response = _post_application(client, "Discovery Status App")
    assert response.status_code == 201
    body = response.json()
    assert body["discovery_status"] == "running"

    from api import main as api_main

    async def _no_pollers(client: object, task_queue: str) -> bool:
        return False

    monkeypatch.setattr(api_main, "has_pollers", _no_pollers)

    status_response = client.get(f"/applications/{body['id']}/discovery-status")

    assert status_response.status_code == 200
    assert status_response.json() == {"available": False, "retry_count": 0}

    # A DISC-001 row (Story 2.18's is_temporal_retry diagnostic) for this run
    # should surface as a non-zero retry_count, so the frontend can tell the
    # user it recovered from a worker restart instead of polling in silence.
    from domain import DiscoveryError

    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(body["id"]))
        ).one()
        discovery_run = session.exec(
            select(DiscoveryRun).where(DiscoveryRun.application_id == application.id)
        ).one()
        session.add(
            DiscoveryError(
                application_id=application.id,
                discovery_run_id=discovery_run.id,
                error_code="DISC-001",
                message="Engine restarted (Temporal attempt 2) — resuming",
                retry_count=1,
            )
        )
        session.commit()

    retried_response = client.get(f"/applications/{body['id']}/discovery-status")
    assert retried_response.status_code == 200
    assert retried_response.json() == {"available": False, "retry_count": 1}
