"""The real `discovery_activity` end-to-end (Story 2.2, Task 5) — Postgres +
Vault + MinIO + a live local target app, no Temporal server involved (calls
the Activity function directly, same skip-cleanly convention as
`apps/api/tests/test_onboarding.py`).
"""

import json
import uuid

import discovery_worker.activities as activities_module
import hvac
import pytest
from discovery_worker.activities import discovery_activity
from discovery_worker.db import engine, init_db
from discovery_worker.object_store import MINIO_ENDPOINT, ObjectStore
from domain import ApiEndpoint, Application, DiscoveryRun, Form, Organization, Page
from fixtures.target_app import configure
from secrets_client.vault_client import VAULT_ADDR, VAULT_TOKEN, VaultSecretsClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import DiscoveryActivityInput


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
    except Exception:
        return False


def _minio_available() -> bool:
    import urllib.request

    try:
        urllib.request.urlopen(f"http://{MINIO_ENDPOINT}/minio/health/live", timeout=2)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not (_db_available() and _vault_available() and _minio_available()),
    reason="requires PostgreSQL + Vault + MinIO reachable — start docker compose",
)


def _seed_application(target_app_url: str) -> tuple[str, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Returns (secret_ref, application_external_id, discovery_run_id, run_external_id)."""
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        credential = json.dumps({"username": "qa", "password": "qa-pass"}).encode()
        secret_ref = VaultSecretsClient().store(org.id, credential)

        application = Application(
            organization_id=org.id,
            name="Discovery Activity Test App",
            url=target_app_url,
            environment="test",
            auth_method="standard_login",
            secret_ref=secret_ref.path,
        )
        session.add(application)
        session.flush()

        discovery_run = DiscoveryRun(application_id=application.id, status="running")
        session.add(discovery_run)
        session.commit()
        session.refresh(application)
        session.refresh(discovery_run)

        return (
            secret_ref.path,
            application.external_id,
            discovery_run.id,
            discovery_run.external_id,
        )


@pytest.mark.asyncio
async def test_discovery_activity_captures_the_application_model_against_live_target(
    target_app_url: str,
) -> None:
    init_db()
    secret_ref_path, application_external_id, discovery_run_id, discovery_run_external_id = (
        _seed_application(target_app_url)
    )

    result = await discovery_activity(
        DiscoveryActivityInput(
            discovery_run_id=str(discovery_run_external_id),
            application_id=str(application_external_id),
            secret_ref=secret_ref_path,
        )
    )
    assert result.status == "complete"
    assert result.page_count > 0

    with Session(engine) as session:
        pages = session.exec(select(Page).where(Page.discovery_run_id == discovery_run_id)).all()
        forms = session.exec(select(Form).where(Form.discovery_run_id == discovery_run_id)).all()
        completed_run = session.get(DiscoveryRun, discovery_run_id)

    assert completed_run is not None
    assert completed_run.status == "complete"
    # CR-2 (AC 10): authenticating -> discovering, and stage remains
    # "discovering" through completion (ApplicationModelBuilder/Inference are
    # separate Activities that own the later stage transitions).
    assert completed_run.stage == "discovering"

    assert pages, "expected at least one Page row"
    assert forms, "expected at least one Form row"
    assert all(page.discovery_run_id == discovery_run_id for page in pages)
    assert all(page.merged_into_id is None for page in pages)
    # Journey attribution no longer lives on Page at all (Story 2.6 rework —
    # see JourneyStep) — DiscoveryActivity structurally cannot set it.

    object_store = ObjectStore()
    for page in pages:
        assert page.object_storage_key is not None
        blob = object_store.get(page.object_storage_key)
        assert len(blob) > 0


@pytest.mark.asyncio
async def test_discovery_activity_marks_failed_on_session_expiry(target_app_url: str) -> None:
    init_db()
    # See test_crawler.py's matching test for why this is 3, not 2 — the
    # shared header form's own same-page resubmit is itself an authenticated
    # hit that must land before expiry to keep it from tripping mid-form-loop.
    configure(expire_after=3)
    secret_ref_path, application_external_id, discovery_run_id, discovery_run_external_id = (
        _seed_application(target_app_url)
    )

    await discovery_activity(
        DiscoveryActivityInput(
            discovery_run_id=str(discovery_run_external_id),
            application_id=str(application_external_id),
            secret_ref=secret_ref_path,
        )
    )

    with Session(engine) as session:
        failed_run = session.get(DiscoveryRun, discovery_run_id)

    assert failed_run is not None
    assert failed_run.status == "failed"
    assert failed_run.failure_reason == "session_expired"


@pytest.mark.asyncio
async def test_discovery_activity_marks_failed_with_reason_on_crash(
    target_app_url: str,
) -> None:
    """`[FIXED 2026-07-22]` A crash used to leave `failure_reason` blank —
    the actual exception was silently swallowed with no log and no trace of
    why, both here and in the worker's own logs, making any real failure
    (like the cascading DB session bug this same fix day uncovered)
    undiagnosable from the DB alone. Now records the exception type/message
    (bounded to 500 chars) so a real failure is actually diagnosable."""
    init_db()
    _, application_external_id, discovery_run_id, discovery_run_external_id = _seed_application(
        target_app_url
    )

    await discovery_activity(
        DiscoveryActivityInput(
            discovery_run_id=str(discovery_run_external_id),
            application_id=str(application_external_id),
            secret_ref="applications/does-not-exist/nonexistent-secret",
        )
    )

    with Session(engine) as session:
        crashed_run = session.get(DiscoveryRun, discovery_run_id)

    assert crashed_run is not None
    assert crashed_run.status == "failed"
    assert crashed_run.failure_reason
    assert "InvalidPath" in crashed_run.failure_reason


@pytest.mark.asyncio
async def test_pages_captured_before_a_mid_crawl_crash_are_not_lost(
    monkeypatch: pytest.MonkeyPatch, target_app_url: str
) -> None:
    """The fix for captures being written only at the very end: a crash
    partway through must not discard whatever was already captured — it
    should already be committed to Postgres by that point.

    2026-07-21: a screenshot-upload failure is now caught per-page (like a
    broken `goto` destination) instead of escaping to fail the whole run —
    a transient MinIO hiccup on one page shouldn't torch hours of otherwise-
    healthy traversal. So the crawl now runs to completion around the
    simulated failure rather than crashing; what this test actually checks
    (captures before the failure point are never lost) still holds."""
    init_db()
    secret_ref_path, application_external_id, discovery_run_id, discovery_run_external_id = (
        _seed_application(target_app_url)
    )

    real_object_store = ObjectStore()
    calls = {"count": 0}

    class _CrashingObjectStore:
        def put(self, data: bytes, discovery_run_id) -> str:
            calls["count"] += 1
            if calls["count"] > 1:
                raise RuntimeError("simulated crash mid-crawl")
            return real_object_store.put(data, discovery_run_id)

        def get(self, key: str) -> bytes:
            return real_object_store.get(key)

    monkeypatch.setattr(activities_module, "ObjectStore", _CrashingObjectStore)

    result = await discovery_activity(
        DiscoveryActivityInput(
            discovery_run_id=str(discovery_run_external_id),
            application_id=str(application_external_id),
            secret_ref=secret_ref_path,
        )
    )

    assert result.status == "complete"

    with Session(engine) as session:
        pages = session.exec(select(Page).where(Page.discovery_run_id == discovery_run_id)).all()

    assert pages, "pages captured before the failure must survive it, not be discarded"
    assert calls["count"] > 1, "the simulated failure must actually have been hit"


@pytest.mark.asyncio
async def test_a_bad_capture_does_not_poison_the_rest_of_the_crawl(
    monkeypatch: pytest.MonkeyPatch, target_app_url: str
) -> None:
    """`[FIXED 2026-07-22]` A single bad insert (any real DB-level error —
    observed live: exactly this class of failure on an `ApiEndpoint`
    capture) used to poison the whole SQLAlchemy `Session`: Postgres refuses
    every further `commit()` on a session with a failed transaction
    (`psycopg.errors.InFailedSqlTransaction`) until an explicit
    `rollback()`, which `_persist` never did — cascading into an uncaught
    exception that crashed the *entire* Activity. Temporal then retried it
    from absolute scratch, repeatedly, forever restarting discovery from
    zero (observed live: 31 minutes and 16 attempts to get through what
    should have taken well under a minute). Simulates one real,
    guaranteed-to-fail insert (a foreign-key violation — a `page_id` that
    doesn't exist) and proves the crawl survives it and keeps discovering
    and persisting everything captured afterward."""
    init_db()
    secret_ref_path, application_external_id, discovery_run_id, discovery_run_external_id = (
        _seed_application(target_app_url)
    )

    real_api_endpoint = ApiEndpoint
    calls = {"count": 0}

    class _PoisoningApiEndpoint:
        def __new__(cls, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                kwargs["page_id"] = uuid.uuid4()  # a real UUID, but not a real Page — FK violation
            return real_api_endpoint(**kwargs)

    monkeypatch.setattr(activities_module, "ApiEndpoint", _PoisoningApiEndpoint)

    result = await discovery_activity(
        DiscoveryActivityInput(
            discovery_run_id=str(discovery_run_external_id),
            application_id=str(application_external_id),
            secret_ref=secret_ref_path,
        )
    )

    assert result.status == "complete"
    assert calls["count"] >= 1, "the simulated bad capture must actually have been hit"

    with Session(engine) as session:
        pages = session.exec(select(Page).where(Page.discovery_run_id == discovery_run_id)).all()

    assert len(pages) > 1, (
        "pages discovered after the poisoned capture must still be persisted, "
        "proving the session recovered instead of cascading"
    )
