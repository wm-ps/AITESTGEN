"""Cancelling a run — the execution worker's side. Real Postgres throughout,
since the guarantee under test is the TestRun row lock:

- every result/run write refuses a cancelled run (persist, heal writes,
  finalize, force-complete, the email claim);
- a test that committed before the cancel keeps its result, and one racing
  the cancel blocks on the lock and then writes nothing;
- CleanupCancelledTestRunActivity is idempotent and never cancels a run that
  already completed;
- `cancel_watch` stops its body within a couple of seconds of the row going
  "cancelled", with no Temporal involved.
"""

import asyncio
import threading
import time
import uuid
from datetime import UTC, datetime

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
    apply_test_run_cancel,
    lock_test_run,
)
from execution_worker.db import engine, init_db
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import (
    CleanupCancelledTestRunActivityInput,
    FinalizeTestRunActivityInput,
    ForceCompleteTestRunActivityInput,
    HealTestActivityInput,
)


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

_LOCATOR_FAILURE = (
    "TimeoutError: locator.click: Timeout 15000ms exceeded.\n"
    "Call log:\n  - waiting for getByRole('button', { name: 'Submit' })"
)


def _seed_run(
    *, run_status: str = "running", result_statuses: tuple[str, ...] = ("pending",)
) -> tuple[TestRun, list[TestResult], TestAsset]:
    init_db()
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Cancel Test App",
            url="https://app.example.com",
            environment="staging",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
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
            scenario_id=scenario.id, test_suite_id=test_suite.id, code="// original spec\n"
        )
        session.add(test_asset)
        session.flush()
        test_run = TestRun(
            application_id=application.id,
            run_number=1,
            status=run_status,
            workflow_id=f"execution-test-{uuid.uuid4()}",
            environment_snapshot=application.environment,
            target_base_url_snapshot=application.url,
            total_count=len(result_statuses),
        )
        session.add(test_run)
        session.flush()
        results = []
        for status in result_statuses:
            result = TestResult(
                test_run_id=test_run.id,
                test_asset_id=test_asset.id,
                scenario_id=test_asset.scenario_id,
                status=status,
                error_message=_LOCATOR_FAILURE if status == "failed" else None,
            )
            session.add(result)
            results.append(result)
        session.commit()
        for row in (test_run, test_asset, *results):
            session.refresh(row)
        return test_run, results, test_asset


def _cancel(test_run: TestRun) -> None:
    with Session(engine) as session:
        locked = lock_test_run(session, test_run.id)
        assert locked is not None
        apply_test_run_cancel(session, locked)
        session.commit()


def _reload(model, pk):
    with Session(engine) as session:
        return session.exec(select(model).where(model.id == pk)).one()


def _passed_outcome() -> dict:
    return {"status": "passed", "duration_ms": 1200, "artifact_paths": [], "allure_attempt": None}


def _context(result: TestResult) -> activities_module._ExecutionContext:
    return activities_module._ExecutionContext(
        application=None,  # type: ignore[arg-type] — persist never reads it
        test_result_pk=result.id,
        spec_path="tests/checkout/completes-checkout.spec.ts",
    )


# --- Race safety: the TestRun row lock ---------------------------------------


def test_a_result_committed_before_the_cancel_is_preserved() -> None:
    test_run, (result,), _ = _seed_run()

    activities_module._persist_test_result_sync(
        str(test_run.external_id), _context(result), _passed_outcome(), require_pending=True
    )
    _cancel(test_run)

    assert _reload(TestResult, result.id).status == "passed"
    assert _reload(TestRun, test_run.id).status == "cancelled"


def test_a_result_arriving_after_the_cancel_is_not_written() -> None:
    test_run, (result,), _ = _seed_run()

    _cancel(test_run)
    activities_module._persist_test_result_sync(
        str(test_run.external_id), _context(result), _passed_outcome(), require_pending=True
    )

    reloaded = _reload(TestResult, result.id)
    assert reloaded.status == "cancelled"
    assert reloaded.duration_ms is None


def test_a_result_racing_the_cancel_waits_for_it_then_writes_nothing() -> None:
    test_run, (result,), _ = _seed_run()

    # Hold the cancel's lock open while the result write runs concurrently.
    with Session(engine) as cancel_session:
        locked = lock_test_run(cancel_session, test_run.id)
        assert locked is not None
        apply_test_run_cancel(cancel_session, locked)

        writer = threading.Thread(
            target=activities_module._persist_test_result_sync,
            args=(str(test_run.external_id), _context(result), _passed_outcome()),
            kwargs={"require_pending": True},
        )
        writer.start()
        writer.join(timeout=1.5)
        assert writer.is_alive(), "the result write must block on the run lock"
        cancel_session.commit()
    writer.join(timeout=10)

    assert not writer.is_alive()
    assert _reload(TestResult, result.id).status == "cancelled"
    assert _reload(TestRun, test_run.id).status == "cancelled"


def test_a_heal_rerun_still_overwrites_a_finished_result_on_a_live_run() -> None:
    # require_pending is only for ExecuteTestActivity's first write; a heal
    # rerun rewrites a "failed" result on purpose.
    test_run, (result,), _ = _seed_run(result_statuses=("failed",))

    activities_module._persist_test_result_sync(
        str(test_run.external_id), _context(result), _passed_outcome()
    )

    assert _reload(TestResult, result.id).status == "passed"


# --- No side effects after a cancel ------------------------------------------


def test_finalize_and_force_complete_never_complete_a_cancelled_run() -> None:
    test_run, (result,), _ = _seed_run()
    _cancel(test_run)

    activities_module._finalize_test_run_sync(
        FinalizeTestRunActivityInput(test_run_id=str(test_run.external_id))
    )
    activities_module._force_complete_test_run_sync(
        ForceCompleteTestRunActivityInput(test_run_id=str(test_run.external_id))
    )

    assert _reload(TestRun, test_run.id).status == "cancelled"
    assert _reload(TestResult, result.id).status == "cancelled"


def test_no_heal_runs_or_writes_on_a_cancelled_run() -> None:
    test_run, (result,), test_asset = _seed_run(result_statuses=("failed",))
    _cancel(test_run)
    heal_input = HealTestActivityInput(
        application_id=str(uuid.uuid4()),
        test_run_id=str(test_run.external_id),
        test_result_id=str(result.external_id),
    )

    assert activities_module._claim_heal_sync(str(result.external_id)) is False
    assert activities_module._load_heal_context_sync(heal_input) is None
    activities_module._record_typecheck_failure_sync(result.id, ["TS2345"], False)
    activities_module._record_heal_supersede_sync(result.id, test_asset.id, "// healed\n", False)

    reloaded = _reload(TestResult, result.id)
    assert reloaded.auto_heal_attempt_count == 0
    assert reloaded.healed_test_asset_id is None
    assert reloaded.error_message == _LOCATOR_FAILURE
    assert _reload(TestAsset, test_asset.id).current is True


def test_the_report_email_is_never_claimed_for_a_cancelled_run() -> None:
    test_run, _, _ = _seed_run()
    _cancel(test_run)

    assert activities_module._claim_report_email_sync(test_run.id) is False


# --- CleanupCancelledTestRunActivity -------------------------------------------


def test_cleanup_applies_a_cancel_sent_straight_to_temporal() -> None:
    test_run, (finished, unfinished), _ = _seed_run(result_statuses=("passed", "pending"))

    activities_module._cleanup_cancelled_test_run_sync(
        CleanupCancelledTestRunActivityInput(workflow_id=test_run.workflow_id)  # type: ignore[arg-type]
    )
    # Idempotent: a retry changes nothing.
    activities_module._cleanup_cancelled_test_run_sync(
        CleanupCancelledTestRunActivityInput(workflow_id=test_run.workflow_id)  # type: ignore[arg-type]
    )

    assert _reload(TestRun, test_run.id).status == "cancelled"
    assert _reload(TestResult, finished.id).status == "passed"
    assert _reload(TestResult, unfinished.id).status == "cancelled"


def test_cleanup_leaves_a_run_that_already_completed() -> None:
    test_run, (result,), _ = _seed_run(run_status="completed", result_statuses=("passed",))

    activities_module._cleanup_cancelled_test_run_sync(
        CleanupCancelledTestRunActivityInput(workflow_id=test_run.workflow_id)  # type: ignore[arg-type]
    )

    assert _reload(TestRun, test_run.id).status == "completed"


def test_cleanup_with_no_run_yet_is_a_no_op() -> None:
    activities_module._cleanup_cancelled_test_run_sync(
        CleanupCancelledTestRunActivityInput(workflow_id=f"execution-never-{uuid.uuid4()}")
    )


# --- cancel_watch: prompt, database-driven -----------------------------------


def test_cancel_watch_interrupts_its_body_when_the_run_is_cancelled() -> None:
    test_run, _, _ = _seed_run()
    is_cancelled = lambda: activities_module._test_run_cancelled_sync(  # noqa: E731
        test_run_id=str(test_run.external_id)
    )

    async def _body() -> tuple[bool, bool, float]:
        started = time.monotonic()
        reached_end = False
        async with activities_module.cancel_watch(is_cancelled) as watch:
            await asyncio.sleep(60)  # an AI call, a live inspection…
            reached_end = True
        return watch.run_cancelled, reached_end, time.monotonic() - started

    async def _main() -> tuple[bool, bool, float]:
        body = asyncio.create_task(_body())
        await asyncio.sleep(0.5)
        await asyncio.to_thread(_cancel, test_run)
        return await body

    run_cancelled, reached_end, elapsed = asyncio.run(_main())

    assert run_cancelled is True
    assert reached_end is False
    assert elapsed < activities_module.CANCEL_POLL_SECONDS + 3
