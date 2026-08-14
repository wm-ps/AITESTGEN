"""PrepareTestRunActivity / FinalizeTestRunActivity — Postgres only, no real
Playwright/npm install needed for these cases: the "has executable tests"
path monkeypatches `assemble_test_suite_project_to_dir`/`_install_project`
so this exercises the DB-facing aggregation logic in isolation from Node
tooling. `ExecuteTestActivity` itself (a real `npx playwright test`
subprocess against a live target) is out of scope for a unit test — see the
plan's manual end-to-end verification step instead.

There is deliberately no execution-policy/safety-classification gating to
test here anymore (see `activities.py::_prepare_test_run_sync`'s own
ponytail note) — every current TestAsset is executable unconditionally.
"""

import uuid

import execution_worker.activities as activities_module
import pytest
from domain import (
    Application,
    DiscoveryRun,
    Journey,
    Organization,
    Scenario,
    TestAsset,
    TestResult,
    TestRun,
    TestSuite,
)
from execution_worker.db import engine, init_db
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import FinalizeTestRunActivityInput, PrepareTestRunActivityInput


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


def _seed_application(**overrides) -> Application:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        defaults = dict(
            organization_id=org.id,
            name="Execution Test App",
            url="https://app.example.com",
            environment="staging",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        defaults.update(overrides)
        application = Application(**defaults)
        session.add(application)
        session.commit()
        session.refresh(application)
        return application


def _seed_test_asset(application: Application, *, safety_classification: str) -> TestAsset:
    with Session(engine) as session:
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
            journey_id=journey.id,
            type="happy",
            name="Completes checkout",
            steps=["Add item to cart"],
            generation_run_id=journey.attempt,
            safety_classification=safety_classification,
        )
        session.add(scenario)
        session.flush()

        test_suite = TestSuite(
            journey_id=journey.id, name="Checkout Test Suite", generation_run_id=journey.attempt
        )
        session.add(test_suite)
        session.flush()

        test_asset = TestAsset(
            scenario_id=scenario.id, test_suite_id=test_suite.id, code="// spec\n"
        )
        session.add(test_asset)
        session.commit()
        session.refresh(test_asset)
        return test_asset


def test_prepare_runs_unconditionally_with_no_execution_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No ExecutionPolicy row exists for this Application at all — Run All
    Tests must still work (this is exactly the gap that motivated removing
    the gate)."""
    init_db()
    application = _seed_application()
    asset = _seed_test_asset(application, safety_classification="SAFE")

    monkeypatch.setattr(
        activities_module, "assemble_test_suite_project_to_dir", lambda *a, **k: None
    )
    monkeypatch.setattr(activities_module, "_install_project", lambda *a, **k: None)

    result = activities_module._prepare_test_run_sync(
        PrepareTestRunActivityInput(application_id=str(application.external_id))
    )

    assert result.blocked is False
    assert [t.test_asset_id for t in result.executable] == [str(asset.external_id)]
    with Session(engine) as session:
        test_run = session.exec(
            select(TestRun).where(TestRun.external_id == uuid.UUID(result.test_run_id))
        ).one()
        assert test_run.status == "running"
        assert test_run.execution_policy_id is None


def test_prepare_runs_destructive_and_unknown_scenarios_unconditionally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    application = _seed_application()
    safe_asset = _seed_test_asset(application, safety_classification="SAFE")
    destructive_asset = _seed_test_asset(application, safety_classification="DESTRUCTIVE")
    unknown_asset = _seed_test_asset(application, safety_classification="UNKNOWN")

    monkeypatch.setattr(
        activities_module, "assemble_test_suite_project_to_dir", lambda *a, **k: None
    )
    monkeypatch.setattr(activities_module, "_install_project", lambda *a, **k: None)

    result = activities_module._prepare_test_run_sync(
        PrepareTestRunActivityInput(application_id=str(application.external_id))
    )

    assert result.blocked is False
    assert {t.test_asset_id for t in result.executable} == {
        str(safe_asset.external_id),
        str(destructive_asset.external_id),
        str(unknown_asset.external_id),
    }

    with Session(engine) as session:
        test_run = session.exec(
            select(TestRun).where(TestRun.external_id == uuid.UUID(result.test_run_id))
        ).one()
        assert test_run.total_count == 3
        assert test_run.blocked_count == 0

        results = session.exec(
            select(TestResult).where(TestResult.test_run_id == test_run.id)
        ).all()
        assert all(r.status == "pending" for r in results)


def test_finalize_aggregates_counts_and_marks_completed() -> None:
    init_db()
    application = _seed_application()
    asset_passed = _seed_test_asset(application, safety_classification="SAFE")
    asset_failed = _seed_test_asset(application, safety_classification="SAFE")

    with Session(engine) as session:
        test_run = TestRun(
            application_id=application.id,
            status="running",
            environment_snapshot=application.environment,
            target_base_url_snapshot=application.url,
        )
        session.add(test_run)
        session.flush()
        session.add(
            TestResult(
                test_run_id=test_run.id,
                test_asset_id=asset_passed.id,
                scenario_id=asset_passed.scenario_id,
                status="passed",
            )
        )
        session.add(
            TestResult(
                test_run_id=test_run.id,
                test_asset_id=asset_failed.id,
                scenario_id=asset_failed.scenario_id,
                status="failed",
            )
        )
        session.commit()
        session.refresh(test_run)
        test_run_external_id = test_run.external_id

    activities_module._finalize_test_run_sync(
        FinalizeTestRunActivityInput(test_run_id=str(test_run_external_id))
    )

    with Session(engine) as session:
        test_run = session.exec(
            select(TestRun).where(TestRun.external_id == test_run_external_id)
        ).one()
        assert test_run.status == "completed"
        assert test_run.total_count == 2
        assert test_run.passed_count == 1
        assert test_run.failed_count == 1
        assert test_run.completed_at is not None


def test_finalize_marks_leftover_pending_results_as_errored() -> None:
    """An ExecuteTestActivity that exhausted its own retries leaves its
    TestResult stuck at "pending" — FinalizeTestRunActivity still always
    runs, so without this fix that result would silently vanish from every
    count instead of surfacing as a real outcome."""
    init_db()
    application = _seed_application()
    stuck_asset = _seed_test_asset(application, safety_classification="SAFE")

    with Session(engine) as session:
        test_run = TestRun(
            application_id=application.id,
            status="running",
            environment_snapshot=application.environment,
            target_base_url_snapshot=application.url,
        )
        session.add(test_run)
        session.flush()
        session.add(
            TestResult(
                test_run_id=test_run.id,
                test_asset_id=stuck_asset.id,
                scenario_id=stuck_asset.scenario_id,
                status="pending",
            )
        )
        session.commit()
        session.refresh(test_run)
        test_run_external_id = test_run.external_id

    activities_module._finalize_test_run_sync(
        FinalizeTestRunActivityInput(test_run_id=str(test_run_external_id))
    )

    with Session(engine) as session:
        test_run = session.exec(
            select(TestRun).where(TestRun.external_id == test_run_external_id)
        ).one()
        assert test_run.status == "completed"
        assert test_run.total_count == 1
        assert test_run.errored_count == 1

        result = session.exec(
            select(TestResult).where(TestResult.test_asset_id == stuck_asset.id)
        ).one()
        assert result.status == "errored"
        assert result.error_message is not None
        assert result.completed_at is not None
