"""PrepareSingleTestRunActivity — Postgres only, no real Playwright/npm
install needed: `assemble_test_suite_project_to_dir`/`_install_project` are
monkeypatched, same convention `test_activities.py` uses for the sibling
`PrepareTestRunActivity`.
"""

import uuid

import execution_worker.add_test_case_activities as add_test_case_activities_module
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
from workflows import DiscardTestRunActivityInput, PrepareSingleTestRunActivityInput


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


def _seed_application() -> Application:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        application = Application(
            organization_id=org.id,
            name="Add Test Case Activities Test App",
            url="https://app.example.com",
            environment="staging",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.commit()
        session.refresh(application)
        return application


def _seed_test_asset(application: Application) -> TestAsset:
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


def test_prepare_single_test_run_assigns_a_run_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """`[FIXED]` regression: `TestRun` was constructed here without
    `run_number` — a NOT NULL column — so every "Add Test Case"/live-
    exploration run crashed with a Postgres constraint violation before a
    single test ever executed."""
    init_db()
    application = _seed_application()
    test_asset = _seed_test_asset(application)
    monkeypatch.setattr(
        add_test_case_activities_module, "assemble_test_suite_project_to_dir", lambda *a, **k: None
    )
    monkeypatch.setattr(add_test_case_activities_module, "_install_project", lambda *a, **k: None)

    result = add_test_case_activities_module._prepare_single_test_run_sync(
        PrepareSingleTestRunActivityInput(
            application_id=str(application.external_id),
            test_asset_id=str(test_asset.external_id),
        )
    )

    with Session(engine) as session:
        test_run = session.exec(
            select(TestRun).where(TestRun.external_id == uuid.UUID(result.test_run_id))
        ).one()
        assert test_run.run_number == 1


def test_prepare_single_test_run_assigns_sequential_run_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    application = _seed_application()
    monkeypatch.setattr(
        add_test_case_activities_module, "assemble_test_suite_project_to_dir", lambda *a, **k: None
    )
    monkeypatch.setattr(add_test_case_activities_module, "_install_project", lambda *a, **k: None)

    run_numbers = []
    for _ in range(3):
        test_asset = _seed_test_asset(application)
        result = add_test_case_activities_module._prepare_single_test_run_sync(
            PrepareSingleTestRunActivityInput(
                application_id=str(application.external_id),
                test_asset_id=str(test_asset.external_id),
            )
        )
        with Session(engine) as session:
            test_run = session.exec(
                select(TestRun).where(TestRun.external_id == uuid.UUID(result.test_run_id))
            ).one()
            run_numbers.append(test_run.run_number)

    assert run_numbers == [1, 2, 3]


def test_discard_test_run_deletes_the_run_and_its_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """LiveExplorationTestWorkflow's internal verify+heal pass discards its
    own TestRun/TestResult rather than finalizing them — a real dashboard/
    Runs-tab query lists every TestRun for an Application with no filter, so
    anything left behind there would leak an internal check as if it were a
    real, user-visible run."""
    init_db()
    application = _seed_application()
    test_asset = _seed_test_asset(application)
    monkeypatch.setattr(
        add_test_case_activities_module, "assemble_test_suite_project_to_dir", lambda *a, **k: None
    )
    monkeypatch.setattr(add_test_case_activities_module, "_install_project", lambda *a, **k: None)

    prep = add_test_case_activities_module._prepare_single_test_run_sync(
        PrepareSingleTestRunActivityInput(
            application_id=str(application.external_id),
            test_asset_id=str(test_asset.external_id),
        )
    )

    add_test_case_activities_module._discard_test_run_sync(
        DiscardTestRunActivityInput(test_run_id=prep.test_run_id)
    )

    with Session(engine) as session:
        assert (
            session.exec(
                select(TestRun).where(TestRun.external_id == uuid.UUID(prep.test_run_id))
            ).one_or_none()
            is None
        )
        assert (
            session.exec(
                select(TestResult).where(TestResult.external_id == uuid.UUID(prep.test_result_id))
            ).one_or_none()
            is None
        )

    # Idempotent under Temporal's at-least-once retry — a repeat call on an
    # already-discarded run must not raise.
    add_test_case_activities_module._discard_test_run_sync(
        DiscardTestRunActivityInput(test_run_id=prep.test_run_id)
    )
