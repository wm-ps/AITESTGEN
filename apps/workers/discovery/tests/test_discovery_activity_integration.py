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
from domain import Application, DiscoveryRun, Evidence, Organization
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
async def test_discovery_activity_captures_evidence_against_live_target(
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
    assert result.evidence_count > 0

    with Session(engine) as session:
        rows = session.exec(
            select(Evidence).where(Evidence.discovery_run_id == discovery_run_id)
        ).all()
        completed_run = session.get(DiscoveryRun, discovery_run_id)

    assert completed_run is not None
    assert completed_run.status == "complete"

    assert rows, "expected at least one Evidence row"
    types_seen = {row.type for row in rows}
    assert "page" in types_seen
    assert "form" in types_seen
    assert all(row.discovery_run_id == discovery_run_id for row in rows)
    assert all(row.journey_id is None for row in rows)

    object_store = ObjectStore()
    page_rows = [row for row in rows if row.type == "page"]
    assert page_rows
    for row in page_rows:
        assert row.object_storage_key is not None
        blob = object_store.get(row.object_storage_key)
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
async def test_discovery_activity_marks_failed_without_reason_on_crash(
    target_app_url: str,
) -> None:
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
    assert crashed_run.failure_reason is None


@pytest.mark.asyncio
async def test_evidence_captured_before_a_mid_crawl_crash_is_not_lost(
    monkeypatch: pytest.MonkeyPatch, target_app_url: str
) -> None:
    """The fix for evidence being written only at the very end: a crash
    partway through must not discard whatever was already captured — it
    should already be committed to Postgres by that point."""
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

    assert result.status == "failed"

    with Session(engine) as session:
        rows = session.exec(
            select(Evidence).where(Evidence.discovery_run_id == discovery_run_id)
        ).all()

    assert rows, "evidence captured before the crash must survive it, not be discarded"
