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
    Form,
    FormField,
    Journey,
    Organization,
    Page,
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
from workflows import (
    ExecuteTestActivityInput,
    FinalizeTestRunActivityInput,
    ForceCompleteTestRunActivityInput,
    PrepareTestRunActivityInput,
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


def test_prepare_assigns_unique_sequential_run_numbers_under_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`trigger_test_run` starts each run as an independently-uuid4()-keyed
    Temporal workflow with no idempotency key (api/main.py), so two "Run All
    Tests" clicks for the same Application can race — each with its own
    `_prepare_test_run_sync` call and its own DB session, just like the
    `ThreadPoolExecutor` below simulates. `run_number` must still come out
    unique and contiguous (1..N), which only holds if the
    `Application.next_test_run_number` claim is actually atomic."""
    from concurrent.futures import ThreadPoolExecutor

    init_db()
    application = _seed_application()
    _seed_test_asset(application, safety_classification="SAFE")

    monkeypatch.setattr(
        activities_module, "assemble_test_suite_project_to_dir", lambda *a, **k: None
    )
    monkeypatch.setattr(activities_module, "_install_project", lambda *a, **k: None)

    def _prepare(_: int) -> str:
        return activities_module._prepare_test_run_sync(
            PrepareTestRunActivityInput(application_id=str(application.external_id))
        ).test_run_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        test_run_ids = list(pool.map(_prepare, range(8)))

    with Session(engine) as session:
        run_numbers = [
            session.exec(
                select(TestRun).where(TestRun.external_id == uuid.UUID(test_run_id))
            )
            .one()
            .run_number
            for test_run_id in test_run_ids
        ]
    assert sorted(run_numbers) == list(range(1, 9))


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


def test_prepare_force_closes_run_when_assembly_inputs_crash_before_any_test_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crash in `_load_assembly_inputs_sync` happens before any TestResult
    row exists — this must still mark the TestRun "completed" instead of
    leaving it stuck "running" with zero TestResults (the earlier, narrower
    try/except only covered the assemble/install/auth step, not this one)."""
    init_db()
    application = _seed_application()
    _seed_test_asset(application, safety_classification="SAFE")

    def _always_fails(*_a, **_k):
        raise RuntimeError("simulated assembly-inputs failure")

    monkeypatch.setattr(activities_module, "_load_assembly_inputs_sync", _always_fails)

    result = activities_module._prepare_test_run_sync(
        PrepareTestRunActivityInput(application_id=str(application.external_id))
    )

    assert result.blocked is False
    assert result.executable == []
    with Session(engine) as session:
        test_run = session.exec(
            select(TestRun).where(TestRun.external_id == uuid.UUID(result.test_run_id))
        ).one()
        assert test_run.status == "completed"
        assert test_run.total_count == 0
        assert test_run.errored_count == 0


def test_prepare_logs_in_once_when_login_evidence_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """`[FIXED]` Every `ExecuteTestActivity` used to re-run `auth.setup.ts`
    inside its own concurrent subprocess, each overwriting the shared
    `.auth/state.json` — a same-account app allowing only one active
    session then boots out whichever concurrent test was mid-run, landing
    it back on the login page (`toHaveURL` mismatch redirected to
    `/Account/Login?ReturnUrl=...`). Login must happen exactly once, in
    `PrepareTestRunActivity`, which always runs alone (see module
    docstring) — never once per `ExecuteTestActivity`."""
    init_db()
    application = _seed_application()
    _seed_test_asset(application, safety_classification="SAFE")

    with Session(engine) as session:
        discovery_run = DiscoveryRun(application_id=application.id, status="complete")
        session.add(discovery_run)
        session.flush()
        page = Page(
            application_id=application.id, discovery_run_id=discovery_run.id, url="/login"
        )
        session.add(page)
        session.flush()
        form = Form(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            page_id=page.id,
            action_url="/login",
        )
        session.add(form)
        session.flush()
        session.add(FormField(form_id=form.id, name="password", input_type="password"))
        session.commit()

    monkeypatch.setattr(
        activities_module, "assemble_test_suite_project_to_dir", lambda *a, **k: None
    )
    monkeypatch.setattr(activities_module, "_install_project", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(
        activities_module, "_run_auth_setup_once", lambda *a, **k: calls.append(a)
    )

    result = activities_module._prepare_test_run_sync(
        PrepareTestRunActivityInput(application_id=str(application.external_id))
    )

    assert result.blocked is False
    assert len(calls) == 1


async def test_run_playwright_test_skips_setup_dependency(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Pairs with the once-only login above: each per-spec invocation must
    reuse the `.auth/state.json` that `PrepareTestRunActivity` already
    wrote instead of re-running the `setup` project dependency itself."""

    class _FakeProcess:
        async def communicate(self):
            return b'{"suites": []}', b""

    captured_args = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured_args.extend(args)
        return _FakeProcess()

    monkeypatch.setattr(
        activities_module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )

    await activities_module._run_playwright_test(
        tmp_path, "tests/example.spec.ts", {}, 30.0, "test-result-id"
    )

    assert "--no-deps" in captured_args


async def test_execute_test_retries_once_after_session_invalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[FIXED]` support/fixtures.ts marks a failure caused by an invalidated
    shared `@auth` session with `AUTH_SESSION_INVALID` (see its own note) —
    `ExecuteTestActivity` must recognize that marker, refresh the session
    exactly once, and retry the same spec rather than reporting a flaky-
    looking failure. A failure WITHOUT the marker must never trigger a
    retry — that's a real test failure, not a session problem."""
    init_db()
    application = _seed_application()
    asset = _seed_test_asset(application, safety_classification="SAFE")

    with Session(engine) as session:
        test_run = TestRun(
            application_id=application.id,
            run_number=1,
            status="running",
            environment_snapshot="staging",
            target_base_url_snapshot=application.url,
        )
        session.add(test_run)
        session.flush()
        test_result = TestResult(
            test_run_id=test_run.id,
            test_asset_id=asset.id,
            scenario_id=asset.scenario_id,
            status="pending",
        )
        session.add(test_result)
        session.commit()
        session.refresh(test_run)
        session.refresh(test_result)
        test_run_external_id = test_run.external_id
        test_result_external_id = test_result.external_id

    monkeypatch.setattr(activities_module, "_ensure_project_dir", lambda *a, **k: _noop())
    monkeypatch.setattr(activities_module, "_build_subprocess_env", lambda *a, **k: {})

    refresh_calls = []

    async def fake_refresh(*a, **k):
        refresh_calls.append(a)

    monkeypatch.setattr(activities_module, "_refresh_auth_once", fake_refresh)

    outcomes = [
        {
            "status": "failed",
            "duration_ms": 100,
            "error_message": "Error: locator not found\n\nAUTH_SESSION_INVALID: session dead",
            "stack_trace": None,
            "console_output": None,
            "artifact_paths": [],
        },
        {
            "status": "passed",
            "duration_ms": 50,
            "error_message": None,
            "stack_trace": None,
            "console_output": None,
            "artifact_paths": [],
        },
    ]
    run_calls = []

    async def fake_run_playwright_test(*a, **k):
        run_calls.append(a)
        return outcomes[len(run_calls) - 1]

    monkeypatch.setattr(activities_module, "_run_playwright_test", fake_run_playwright_test)

    await activities_module.execute_test_activity(
        ExecuteTestActivityInput(
            application_id=str(application.external_id),
            test_run_id=str(test_run_external_id),
            test_result_id=str(test_result_external_id),
            test_asset_id=str(asset.external_id),
        )
    )

    assert len(run_calls) == 2
    assert len(refresh_calls) == 1
    with Session(engine) as session:
        result = session.exec(
            select(TestResult).where(TestResult.external_id == test_result_external_id)
        ).one()
        assert result.status == "passed"


async def test_execute_test_does_not_retry_an_unrelated_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    application = _seed_application()
    asset = _seed_test_asset(application, safety_classification="SAFE")

    with Session(engine) as session:
        test_run = TestRun(
            application_id=application.id,
            run_number=1,
            status="running",
            environment_snapshot="staging",
            target_base_url_snapshot=application.url,
        )
        session.add(test_run)
        session.flush()
        test_result = TestResult(
            test_run_id=test_run.id,
            test_asset_id=asset.id,
            scenario_id=asset.scenario_id,
            status="pending",
        )
        session.add(test_result)
        session.commit()
        session.refresh(test_run)
        session.refresh(test_result)
        test_run_external_id = test_run.external_id
        test_result_external_id = test_result.external_id

    monkeypatch.setattr(activities_module, "_ensure_project_dir", lambda *a, **k: _noop())
    monkeypatch.setattr(activities_module, "_build_subprocess_env", lambda *a, **k: {})

    refresh_calls = []

    async def fake_refresh(*a, **k):
        refresh_calls.append(a)

    monkeypatch.setattr(activities_module, "_refresh_auth_once", fake_refresh)

    run_calls = []

    async def fake_run_playwright_test(*a, **k):
        run_calls.append(a)
        return {
            "status": "failed",
            "duration_ms": 100,
            "error_message": "Error: locator not found",
            "stack_trace": None,
            "console_output": None,
            "artifact_paths": [],
        }

    monkeypatch.setattr(activities_module, "_run_playwright_test", fake_run_playwright_test)

    await activities_module.execute_test_activity(
        ExecuteTestActivityInput(
            application_id=str(application.external_id),
            test_run_id=str(test_run_external_id),
            test_result_id=str(test_result_external_id),
            test_asset_id=str(asset.external_id),
        )
    )

    assert len(run_calls) == 1
    assert len(refresh_calls) == 0


async def _noop() -> None:
    return None


def test_finalize_aggregates_counts_and_marks_completed() -> None:
    init_db()
    application = _seed_application()
    asset_passed = _seed_test_asset(application, safety_classification="SAFE")
    asset_failed = _seed_test_asset(application, safety_classification="SAFE")

    with Session(engine) as session:
        test_run = TestRun(
            application_id=application.id,
            run_number=1,
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


def test_persist_result_updates_live_counts_before_run_finishes() -> None:
    """The polling frontend reads TestRun.passed_count/failed_count while a
    run is still in progress — this must not sit at 0 until Finalize runs."""
    init_db()
    application = _seed_application()
    asset_done = _seed_test_asset(application, safety_classification="SAFE")
    asset_pending = _seed_test_asset(application, safety_classification="SAFE")

    with Session(engine) as session:
        test_run = TestRun(
            application_id=application.id,
            run_number=1,
            status="running",
            environment_snapshot=application.environment,
            target_base_url_snapshot=application.url,
            total_count=2,
        )
        session.add(test_run)
        session.flush()
        done_result = TestResult(
            test_run_id=test_run.id,
            test_asset_id=asset_done.id,
            scenario_id=asset_done.scenario_id,
            status="pending",
        )
        session.add(done_result)
        session.add(
            TestResult(
                test_run_id=test_run.id,
                test_asset_id=asset_pending.id,
                scenario_id=asset_pending.scenario_id,
                status="pending",
            )
        )
        session.commit()
        session.refresh(test_run)
        session.refresh(done_result)
        test_run_external_id = test_run.external_id
        test_run_id = test_run.id
        done_result_pk = done_result.id

    activities_module._persist_test_result_sync(
        str(test_run_external_id),
        activities_module._ExecutionContext(
            application=application, test_result_pk=done_result_pk, spec_path="tests/x.spec.ts"
        ),
        {"status": "passed", "duration_ms": 100},
    )

    with Session(engine) as session:
        test_run = session.exec(select(TestRun).where(TestRun.id == test_run_id)).one()
        assert test_run.passed_count == 1
        assert test_run.failed_count == 0
        assert test_run.status == "running"  # only Finalize marks it completed


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
            run_number=1,
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


def test_force_complete_falls_back_to_bare_status_flip_when_finalize_itself_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ForceCompleteTestRunActivity is the workflow's last-resort call when
    FinalizeTestRunActivity exhausted its own retries — it must still close
    the TestRun even if the real finalize logic (re-tried here first) fails
    again for the same reason."""
    init_db()
    application = _seed_application()

    with Session(engine) as session:
        test_run = TestRun(
            application_id=application.id,
            run_number=1,
            status="running",
            environment_snapshot=application.environment,
            target_base_url_snapshot=application.url,
        )
        session.add(test_run)
        session.commit()
        session.refresh(test_run)
        test_run_external_id = test_run.external_id

    def _always_fails(_input: FinalizeTestRunActivityInput) -> None:
        raise RuntimeError("simulated finalize failure")

    monkeypatch.setattr(activities_module, "_finalize_test_run_sync", _always_fails)

    activities_module._force_complete_test_run_sync(
        ForceCompleteTestRunActivityInput(test_run_id=str(test_run_external_id))
    )

    with Session(engine) as session:
        test_run = session.exec(
            select(TestRun).where(TestRun.external_id == test_run_external_id)
        ).one()
        assert test_run.status == "completed"
        assert test_run.completed_at is not None
