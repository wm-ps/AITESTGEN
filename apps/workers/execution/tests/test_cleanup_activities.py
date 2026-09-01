"""FindPurgeCandidatesActivity / PurgeApplicationActivity — Postgres only.

Seeds an Application with a representative chain of dependent rows
(discovery_run -> journey -> scenario/test_suite -> test_asset, plus a
test_run -> test_result -> test_result_artifact chain) spanning several
levels of the delete order, soft-deletes it in the past, and asserts the
purge removes all of it while leaving an unrelated Application's data alone.
Vault/S3 calls are expected to fail in this environment (no real secret/
object exists) — the activity logs and continues rather than raising, so
this only asserts on the DB side.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from domain import (
    Application,
    DiscoveryRun,
    DiscoverySettings,
    Journey,
    Organization,
    Scenario,
    TestAsset,
    TestResult,
    TestRun,
    TestSuite,
)
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import PurgeApplicationInput

from execution_worker.cleanup_activities import (
    find_purge_candidates_activity,
    purge_application_activity,
)
from execution_worker.db import engine, init_db


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)


def _seed_application(*, deleted_at: datetime | None) -> Application:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        application = Application(
            organization_id=org.id,
            name="Cleanup Test App",
            url="https://app.example.com",
            environment="staging",
            auth_method="standard_login",
            secret_ref=f"applications/{org.id}/{uuid.uuid4()}",
            deleted_at=deleted_at,
        )
        session.add(application)
        session.flush()

        discovery_run = DiscoveryRun(application_id=application.id, status="complete")
        session.add(discovery_run)
        session.flush()

        journey = Journey(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            name="Checkout",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()

        scenario = Scenario(
            journey_id=journey.id, type="happy", name="Happy path", generation_run_id=1
        )
        test_suite = TestSuite(journey_id=journey.id, name="Checkout suite", generation_run_id=1)
        session.add(scenario)
        session.add(test_suite)
        session.flush()

        test_asset = TestAsset(
            scenario_id=scenario.id, test_suite_id=test_suite.id, code="// spec"
        )
        session.add(test_asset)

        test_run = TestRun(
            application_id=application.id,
            run_number=1,
            status="complete",
            environment_snapshot="staging",
            target_base_url_snapshot="https://app.example.com",
        )
        session.add(test_run)
        session.flush()

        test_result = TestResult(
            test_run_id=test_run.id,
            test_asset_id=test_asset.id,
            scenario_id=scenario.id,
            status="passed",
        )
        session.add(test_result)

        session.commit()
        session.refresh(application)
        return application


def _set_retention(period: str) -> None:
    with Session(engine) as session:
        settings = session.exec(select(DiscoverySettings)).one()
        settings.delete_project_after = period
        session.add(settings)
        session.commit()


def test_purge_removes_eligible_application_and_leaves_others_alone() -> None:
    init_db()
    _set_retention("1_day")

    old_deleted_at = datetime.now(UTC) - timedelta(days=2)
    eligible = _seed_application(deleted_at=old_deleted_at)
    untouched = _seed_application(deleted_at=None)
    recently_deleted = _seed_application(deleted_at=datetime.now(UTC))

    candidates = find_purge_candidates_activity()
    assert str(eligible.external_id) in candidates
    assert str(untouched.external_id) not in candidates
    assert str(recently_deleted.external_id) not in candidates

    result = purge_application_activity(
        PurgeApplicationInput(application_id=str(eligible.external_id))
    )
    assert result.skipped is False
    assert result.rows_deleted > 1  # application row + its dependents

    with Session(engine) as session:
        assert (
            session.exec(select(Application).where(Application.id == eligible.id)).first() is None
        )
        assert (
            session.exec(
                select(DiscoveryRun).where(DiscoveryRun.application_id == eligible.id)
            ).first()
            is None
        )
        assert (
            session.exec(select(Application).where(Application.id == untouched.id)).first()
            is not None
        )
        assert (
            session.exec(
                select(Application).where(Application.id == recently_deleted.id)
            ).first()
            is not None
        )


def test_purge_is_a_safe_noop_on_retry() -> None:
    init_db()
    _set_retention("1_day")
    application = _seed_application(deleted_at=datetime.now(UTC) - timedelta(days=2))

    first = purge_application_activity(
        PurgeApplicationInput(application_id=str(application.external_id))
    )
    assert first.skipped is False

    second = purge_application_activity(
        PurgeApplicationInput(application_id=str(application.external_id))
    )
    assert second.skipped is True
