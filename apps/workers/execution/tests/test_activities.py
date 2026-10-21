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
from datetime import UTC, datetime, timedelta

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
    PlatformUser,
    Scenario,
    Schedule,
    TestAsset,
    TestResult,
    TestRun,
    TestSuite,
)
from execution_worker.db import engine, init_db
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from test_suite_assembler import compute_spec_paths
from workflows import (
    TEST_RUN_STALE_AFTER,
    ExecuteTestActivityInput,
    FinalizeTestRunActivityInput,
    ForceCompleteTestRunActivityInput,
    PrepareTestRunActivityInput,
    SendTestRunReportEmailActivityInput,
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


def _seed_test_asset(
    application: Application, *, safety_classification: str, journey_name: str = "Checkout"
) -> TestAsset:
    with Session(engine) as session:
        discovery_run = DiscoveryRun(application_id=application.id, status="complete")
        session.add(discovery_run)
        session.flush()

        journey = Journey(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            name=journey_name,
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


def test_load_execution_context_matches_assembled_path_when_journey_slugs_collide() -> None:
    """`[REGRESSION]` `_write_project_files` disambiguates a Journey-name-slug
    collision across *every* current TestSuite for the Application (see
    `dedupe_slugs`), but `_load_execution_context_sync` used to recompute
    `compute_spec_paths` scoped to only the one TestSuite/TestAsset it was
    handling — a single-item `dedupe_slugs` call can never reproduce a
    suffix assigned against the wider set, so whichever asset landed in the
    disambiguated folder got handed a spec path that didn't exist on disk,
    surfacing as "playwright report contained no suite matching ...".
    "Login Flow" and "Login Flow!" are distinct Journey names (so the
    recording worker's own exact-name dedup lets both exist) but collapse to
    the identical `sanitize_slug` output, reproducing the collision."""
    init_db()
    application = _seed_application()
    asset_a = _seed_test_asset(
        application, safety_classification="SAFE", journey_name="Login Flow"
    )
    asset_b = _seed_test_asset(
        application, safety_classification="SAFE", journey_name="Login Flow!"
    )

    with Session(engine) as session:
        app_row = session.exec(
            select(Application).where(Application.id == application.id)
        ).one()
        ground_truth = activities_module._load_assembly_inputs_sync(session, app_row)
        expected_paths = compute_spec_paths(
            test_suites=ground_truth.test_suites,
            journeys_by_id=ground_truth.journeys_by_id,
            assets_by_suite=ground_truth.assets_by_suite,
            scenario_name_by_asset_id=ground_truth.scenario_name_by_asset_id,
        )

    # Sanity check that this scenario actually reproduces a collision —
    # otherwise the assertions below would pass for the wrong reason.
    assert expected_paths[asset_a.id] != expected_paths[asset_b.id]

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
        test_run_external_id = test_run.external_id

        test_result_external_ids = {}
        for asset in (asset_a, asset_b):
            test_result = TestResult(
                test_run_id=test_run.id,
                test_asset_id=asset.id,
                scenario_id=asset.scenario_id,
                status="pending",
            )
            session.add(test_result)
            session.flush()
            test_result_external_ids[asset.id] = test_result.external_id
        session.commit()

    for asset in (asset_a, asset_b):
        context = activities_module._load_execution_context_sync(
            ExecuteTestActivityInput(
                application_id=str(application.external_id),
                test_run_id=str(test_run_external_id),
                test_result_id=str(test_result_external_ids[asset.id]),
                test_asset_id=str(asset.external_id),
            )
        )
        assert context is not None
        assert context.spec_path == expected_paths[asset.id]


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


def test_reconcile_stale_test_runs_completes_only_runs_past_the_cutoff() -> None:
    """The catch-all for a TestRun that never reached either Finalize or
    ForceComplete at all (worker died before either ran, or a Temporal
    outage spanned the whole run) — a TestRun still "running" well past
    TEST_RUN_STALE_AFTER must get force-completed, and one still safely
    within a normal run's duration must be left untouched."""
    init_db()
    application = _seed_application()

    with Session(engine) as session:
        stale_run = TestRun(
            application_id=application.id,
            run_number=1,
            status="running",
            environment_snapshot=application.environment,
            target_base_url_snapshot=application.url,
            started_at=datetime.now(UTC) - TEST_RUN_STALE_AFTER - timedelta(minutes=1),
        )
        fresh_run = TestRun(
            application_id=application.id,
            run_number=2,
            status="running",
            environment_snapshot=application.environment,
            target_base_url_snapshot=application.url,
            started_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        session.add(stale_run)
        session.add(fresh_run)
        session.commit()
        session.refresh(stale_run)
        session.refresh(fresh_run)
        stale_external_id = stale_run.external_id
        fresh_external_id = fresh_run.external_id

    reconciled_ids = activities_module._reconcile_stale_test_runs_sync()

    # Not an exact-list assertion: this dev DB is shared across test runs, so
    # a genuinely stale "running" TestRun left over from earlier manual
    # testing may also legitimately get reconciled here — that's correct
    # behavior, not test pollution.
    assert str(stale_external_id) in reconciled_ids
    assert str(fresh_external_id) not in reconciled_ids
    with Session(engine) as session:
        stale_run = session.exec(
            select(TestRun).where(TestRun.external_id == stale_external_id)
        ).one()
        fresh_run = session.exec(
            select(TestRun).where(TestRun.external_id == fresh_external_id)
        ).one()
        assert stale_run.status == "completed"
        assert stale_run.completed_at is not None
        assert fresh_run.status == "running"
        assert fresh_run.completed_at is None


async def test_run_playwright_test_gives_each_invocation_its_own_allure_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Without allure-playwright installed, or with a config that predates
    the per-attempt reporter switch, the test runs with plain
    `--reporter=json` (running tests never depends on the report). With
    both, `--reporter` stays off the command line — a CLI reporter would
    drop the config's `resultsDir` — and every invocation, including a
    rerun of the same TestResult, writes into a fresh folder."""

    class _FakeProcess:
        async def communicate(self):
            return b'{"suites": []}', b""

    calls: list = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append((args, kwargs["env"]))
        return _FakeProcess()

    monkeypatch.setattr(
        activities_module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )
    env_name = activities_module.ALLURE_RESULTS_DIR_ENV

    not_installed = await activities_module._run_playwright_test(
        tmp_path, "tests/a.spec.ts", {}, 30.0, "r1"
    )
    (tmp_path / "node_modules" / "allure-playwright").mkdir(parents=True)
    (tmp_path / "playwright.config.ts").write_text("reporter: [['list']]", encoding="utf-8")
    old_config = await activities_module._run_playwright_test(
        tmp_path, "tests/a.spec.ts", {}, 30.0, "r1"
    )
    (tmp_path / "playwright.config.ts").write_text(
        f"reporter: process.env.{env_name} ? [] : []", encoding="utf-8"
    )
    first = await activities_module._run_playwright_test(tmp_path, "tests/a.spec.ts", {}, 30.0, "r1")
    rerun = await activities_module._run_playwright_test(tmp_path, "tests/a.spec.ts", {}, 30.0, "r1")

    for (args, env), outcome in zip(calls[:2], (not_installed, old_config), strict=True):
        assert "--reporter=json" in args
        assert env_name not in env
        assert outcome["allure_attempt"] is None
    for (args, env), outcome in zip(calls[2:], (first, rerun), strict=True):
        assert not any(a.startswith("--reporter") for a in args)
        assert env[env_name] == f"allure-results/r1/{outcome['allure_attempt']}"
    assert first["allure_attempt"] != rerun["allure_attempt"]


class _FakeObjectStore:
    uploads: list = []

    def put_at_key(self, key: str, data: bytes, content_type: str) -> str:
        _FakeObjectStore.uploads.append((key, data, content_type))
        return key


def _seed_completed_test_run() -> tuple[TestRun, TestAsset]:
    """A run (Run #7) plus the one TestAsset its TestResults point at."""
    application = _seed_application()
    asset = _seed_test_asset(application, safety_classification="SAFE")
    with Session(engine) as session:
        test_run = TestRun(
            application_id=application.id,
            run_number=7,
            status="running",
            environment_snapshot=application.environment,
            target_base_url_snapshot=application.url,
        )
        session.add(test_run)
        session.commit()
        session.refresh(test_run)
        return test_run, asset


def _patch_allure_env(monkeypatch: pytest.MonkeyPatch, project_dir, run_result=None) -> list:
    """Points the activity at `project_dir`, fakes `npx allure generate`
    (writing the report unless `run_result` overrides it) and the object
    store. Returns the captured subprocess calls."""
    calls: list = []
    _FakeObjectStore.uploads = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if run_result is not None:
            return run_result(args, **kwargs)
        report_dir = project_dir / "allure-report"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "index.html").write_text("<html>report</html>", encoding="utf-8")
        return None

    monkeypatch.setattr(activities_module, "project_dir_for", lambda _id: project_dir)
    monkeypatch.setattr(activities_module, "_resolve_bin", lambda name: name)
    monkeypatch.setattr(activities_module.subprocess, "run", fake_run)
    monkeypatch.setattr(activities_module, "ObjectStore", _FakeObjectStore)
    return calls


def _add_test_result(test_run: TestRun, asset: TestAsset, status: str, **fields) -> TestResult:
    with Session(engine) as session:
        test_result = TestResult(
            test_run_id=test_run.id,
            test_asset_id=asset.id,
            scenario_id=asset.scenario_id,
            status=status,
            **fields,
        )
        session.add(test_result)
        session.commit()
        session.refresh(test_result)
        return test_result


def _write_attempt(project_dir, test_result: TestResult, status: str, attempt=None) -> str:
    """One invocation's Allure output for `test_result`, as allure-playwright
    lays it out under the per-attempt folder."""
    attempt = attempt or uuid.uuid4().hex
    folder = project_dir / "allure-results" / str(test_result.external_id) / attempt
    folder.mkdir(parents=True, exist_ok=True)
    result_uuid = str(uuid.uuid4())
    (folder / f"{result_uuid}-result.json").write_text(
        f'{{"uuid": "{result_uuid}", "name": "{attempt}", "status": "{status}"}}', encoding="utf-8"
    )
    (folder / f"{uuid.uuid4()}-attachment.png").write_bytes(b"png")
    return attempt


def _mark_persisted(project_dir, test_result: TestResult, attempt: str | None) -> None:
    """The marker `_persist_test_result_sync` writes, from the row as saved."""
    with Session(engine) as session:
        saved = session.get(TestResult, test_result.id)
        activities_module._write_allure_final_marker(
            project_dir, str(saved.external_id), attempt, saved.status, saved.completed_at
        )


def _write_allure_result(project_dir) -> TestRun:
    """A run with one passed TestResult and its persisted attempt."""
    test_run, asset = _seed_completed_test_run()
    test_result = _add_test_result(test_run, asset, "passed", completed_at=datetime.now(UTC))
    _mark_persisted(project_dir, test_result, _write_attempt(project_dir, test_result, "passed"))
    return test_run


def test_persist_writes_final_marker_from_the_committed_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    init_db()
    test_run, asset = _seed_completed_test_run()
    test_result = _add_test_result(test_run, asset, "pending")
    monkeypatch.setattr(activities_module, "project_dir_for", lambda _id: tmp_path)
    attempt = uuid.uuid4().hex

    activities_module._persist_test_result_sync(
        str(test_run.external_id),
        activities_module._ExecutionContext(
            application=Application(name="x"), test_result_pk=test_result.id, spec_path="tests/a.spec.ts"
        ),
        {"status": "failed", "error_message": "boom", "allure_attempt": attempt},
    )

    marker = activities_module._read_marker(
        tmp_path / "allure-results" / str(test_result.external_id)
    )
    with Session(engine) as session:
        saved = session.get(TestResult, test_result.id)
        assert marker == {
            "attempt": attempt,
            "status": "failed",
            "completed_at": activities_module._timestamp_key(saved.completed_at),
        }


def test_collect_uses_only_each_executed_tests_persisted_attempt(tmp_path) -> None:
    """The report's inventory comes from the database, and each test's
    content from the one attempt its marker names. Earlier attempts (the
    failed run before a heal, an auth-refresh rerun) and a later attempt
    that was never persisted sit in the same folder and must not leak."""
    init_db()
    test_run, asset = _seed_completed_test_run()
    now = datetime.now(UTC)

    healed = _add_test_result(test_run, asset, "passed", completed_at=now)
    _write_attempt(tmp_path, healed, "failed", attempt="0" * 32)  # failed run before the heal
    persisted = _write_attempt(tmp_path, healed, "passed", attempt="1" * 32)
    _write_attempt(tmp_path, healed, "failed", attempt="f" * 32)  # never persisted
    _mark_persisted(tmp_path, healed, persisted)

    stale = _add_test_result(test_run, asset, "failed", completed_at=now, error_message="stale")
    _mark_persisted(tmp_path, stale, _write_attempt(tmp_path, stale, "failed"))
    with Session(engine) as session:  # a later persist whose marker write never happened
        row = session.get(TestResult, stale.id)
        row.completed_at = now + timedelta(seconds=5)
        session.add(row)
        session.commit()

    killed = _add_test_result(
        test_run, asset, "timed_out", completed_at=now, error_message="exceeded the execution timeout"
    )
    empty_attempt = uuid.uuid4().hex
    (tmp_path / "allure-results" / str(killed.external_id) / empty_attempt).mkdir(parents=True)
    _mark_persisted(tmp_path, killed, empty_attempt)

    disagreeing = _add_test_result(test_run, asset, "passed", completed_at=now)
    _mark_persisted(tmp_path, disagreeing, _write_attempt(tmp_path, disagreeing, "failed"))

    _add_test_result(test_run, asset, "blocked")
    started_never_finished = _add_test_result(test_run, asset, "pending")
    _write_attempt(tmp_path, started_never_finished, "passed")
    _add_test_result(  # Prepare failed before any Playwright process ran
        test_run, asset, "errored", completed_at=now, error_message="failed to prepare the test project"
    )

    inventory, title = activities_module._load_report_inventory_sync(str(test_run.external_id))
    final_dir, used, synthesized = activities_module._collect_final_allure_results(
        tmp_path, inventory
    )

    assert title == "Execution Test App · Run #7"
    assert (used, synthesized) == (1, 3)
    results = [
        activities_module.json.loads(file.read_text(encoding="utf-8"))
        for file in final_dir.glob("*-result.json")
    ]
    assert len(results) == 4
    assert [r["status"] for r in results if r["name"] == "1" * 32] == ["passed"]
    assert not any(r["name"] in ("0" * 32, "f" * 32) for r in results)
    synthetic = [r for r in results if r["name"] == "Completes checkout"]
    assert sorted(r["status"] for r in synthetic) == ["broken", "broken", "passed"]
    assert {r["statusDetails"].get("message") for r in synthetic} == {
        "stale",
        "exceeded the execution timeout",
        None,
    }
    assert all(
        r["fullName"] == "checkout/completes-checkout.spec.ts › Completes checkout" for r in synthetic
    )
    # Only the persisted attempt's own attachment was copied.
    assert len(list(final_dir.glob("*-attachment.png"))) == 1


@pytest.mark.parametrize("make_empty_dir", [False, True])
async def test_generate_allure_report_skips_without_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path, make_empty_dir: bool
) -> None:
    init_db()
    test_run, _ = _seed_completed_test_run()
    if make_empty_dir:
        (tmp_path / "allure-results").mkdir()
    calls = _patch_allure_env(monkeypatch, tmp_path)

    result = await activities_module.generate_allure_report_activity(
        activities_module.GenerateAllureReportActivityInput(test_run_id=str(test_run.external_id))
    )

    assert result is None
    assert calls == []
    assert _FakeObjectStore.uploads == []


async def test_generate_allure_report_skips_when_no_test_finished(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Allure output from an attempt that never got persisted (the test is
    still pending) is no reason to publish a report of zero tests."""
    init_db()
    test_run, asset = _seed_completed_test_run()
    pending = _add_test_result(test_run, asset, "pending")
    _write_attempt(tmp_path, pending, "passed")
    calls = _patch_allure_env(monkeypatch, tmp_path)

    result = await activities_module.generate_allure_report_activity(
        activities_module.GenerateAllureReportActivityInput(test_run_id=str(test_run.external_id))
    )

    assert result is None
    assert calls == []


async def test_generate_allure_report_uploads_and_records_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    init_db()
    test_run = _write_allure_result(tmp_path)
    calls = _patch_allure_env(monkeypatch, tmp_path)

    result = await activities_module.generate_allure_report_activity(
        activities_module.GenerateAllureReportActivityInput(test_run_id=str(test_run.external_id))
    )

    expected_key = f"test-runs/{test_run.external_id}/allure-report.html"
    assert result == expected_key
    (args, kwargs), = calls
    assert args == ["npx", "allure", "generate", "allure-results-final"]
    assert kwargs["cwd"] == tmp_path
    assert kwargs["env"]["AITESTGEN_REPORT_TITLE"] == "Execution Test App · Run #7"
    assert kwargs["timeout"] == activities_module.ALLURE_GENERATE_TIMEOUT_SECONDS
    assert _FakeObjectStore.uploads == [(expected_key, b"<html>report</html>", "text/html")]
    with Session(engine) as session:
        refreshed = session.get(TestRun, test_run.id)
        assert refreshed.allure_report_key == expected_key


@pytest.mark.parametrize(
    "error",
    [
        activities_module.subprocess.CalledProcessError(1, ["npx"]),
        activities_module.subprocess.TimeoutExpired(["npx"], 180),
    ],
)
async def test_generate_allure_report_never_raises_on_generate_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path, error: Exception
) -> None:
    init_db()
    test_run = _write_allure_result(tmp_path)

    def failing_run(args, **kwargs):
        raise error

    _patch_allure_env(monkeypatch, tmp_path, run_result=failing_run)

    result = await activities_module.generate_allure_report_activity(
        activities_module.GenerateAllureReportActivityInput(test_run_id=str(test_run.external_id))
    )

    assert result is None
    assert _FakeObjectStore.uploads == []
    with Session(engine) as session:
        assert session.get(TestRun, test_run.id).allure_report_key is None


async def test_generate_allure_report_skips_upload_over_size_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    init_db()
    test_run = _write_allure_result(tmp_path)
    _patch_allure_env(monkeypatch, tmp_path)
    monkeypatch.setattr(activities_module, "ALLURE_REPORT_MAX_BYTES", 5)

    result = await activities_module.generate_allure_report_activity(
        activities_module.GenerateAllureReportActivityInput(test_run_id=str(test_run.external_id))
    )

    assert result is None
    assert _FakeObjectStore.uploads == []


def test_auth_setup_run_stays_out_of_the_allure_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The once-per-run login uses the project config's reporters unless
    told otherwise — and that config now includes `allure-playwright`, which
    would list the login step in the run's report as if it were a test."""
    captured: list = []
    monkeypatch.setattr(activities_module, "_build_subprocess_env", lambda _app: {})
    monkeypatch.setattr(activities_module, "_resolve_bin", lambda name: name)
    monkeypatch.setattr(
        activities_module.subprocess, "run", lambda args, **kwargs: captured.append(args)
    )

    activities_module._run_auth_setup_once(tmp_path, Application(name="x"))

    assert captured == [["npx", "playwright", "test", "--project=setup", "--reporter=list"]]


# --- Run-completed email ------------------------------------------------------


def _seed_user(application: Application, name: str = "Sam") -> PlatformUser:
    with Session(engine) as session:
        user = PlatformUser(
            organization_id=application.organization_id,
            email=f"{name.lower()}-{uuid.uuid4()}@example.com",
            name=name,
            hashed_password="x",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def _seed_schedule(application: Application, created_by_user_id=None) -> Schedule:
    with Session(engine) as session:
        schedule = Schedule(
            application_id=application.id,
            name="Nightly Regression",
            cadence_type="daily",
            hour=2,
            minute=0,
            time_zone="UTC",
            temporal_schedule_id=f"app-schedule-{uuid.uuid4()}",
            created_by_user_id=created_by_user_id,
        )
        session.add(schedule)
        session.commit()
        session.refresh(schedule)
        return schedule


def _seed_finished_run(application: Application, **fields) -> TestRun:
    defaults = dict(
        application_id=application.id,
        run_number=12,
        status="completed",
        environment_snapshot=application.environment,
        target_base_url_snapshot=application.url,
        triggered_by_name="Sam",
        total_count=2,
        passed_count=1,
        failed_count=1,
        started_at=datetime.now(UTC) - timedelta(minutes=3),
        completed_at=datetime.now(UTC),
    )
    defaults.update(fields)
    with Session(engine) as session:
        test_run = TestRun(**defaults)
        session.add(test_run)
        session.commit()
        session.refresh(test_run)
        return test_run


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    sent: list[tuple] = []
    monkeypatch.setattr(activities_module, "smtp_configured", lambda: True)
    monkeypatch.setattr(activities_module, "send_email", lambda *args: sent.append(args))
    return sent


def _send(test_run: TestRun) -> None:
    activities_module._send_test_run_report_email_sync(
        SendTestRunReportEmailActivityInput(test_run_id=str(test_run.external_id))
    )


def _email_state(test_run: TestRun) -> tuple:
    with Session(engine) as session:
        row = session.get(TestRun, test_run.id)
        return row.report_email_claimed_at, row.report_emailed_at


def test_manual_run_emails_the_starter_once(outbox) -> None:
    init_db()
    application = _seed_application()
    starter = _seed_user(application)
    asset = _seed_test_asset(application, safety_classification="SAFE", journey_name="Sign in")
    test_run = _seed_finished_run(application, triggered_by_user_id=starter.id)
    _add_test_result(test_run, asset, "passed")
    _add_test_result(test_run, asset, "failed", error_message="expected Welcome", duration_ms=1200)

    _send(test_run)
    _send(test_run)  # a retry or duplicate activity after success

    [(to, subject, text, html)] = outbox
    assert to == starter.email
    assert subject == "✕ Run #12 · Execution Test App — 1 of 2 tests didn't pass"
    assert "Completes checkout" in html and "Sign in" in html and "expected Welcome" in html
    assert f"/applications/{application.external_id}/test-runs/{test_run.external_id}" in text
    claimed_at, emailed_at = _email_state(test_run)
    assert claimed_at is not None and emailed_at is not None


def test_email_leaves_out_a_failed_heal_attempts_typecheck_error(outbox) -> None:
    # Seen live: a heal whose generated fix fails typecheck overwrites the
    # test's error_message — the email must not show that heal detail.
    init_db()
    application = _seed_application()
    starter = _seed_user(application)
    asset = _seed_test_asset(application, safety_classification="SAFE", journey_name="Sign in")
    test_run = _seed_finished_run(application, triggered_by_user_id=starter.id)
    _add_test_result(test_run, asset, "passed")
    _add_test_result(
        test_run,
        asset,
        "failed",
        error_message=activities_module.HEAL_TYPECHECK_ERROR_PREFIX + "spec.ts(59,5): TS2353",
    )

    _send(test_run)

    [(_, _, text, html)] = outbox
    assert "Completes checkout" in html
    assert "typecheck" not in html and "typecheck" not in text and "TS2353" not in text


def test_scheduled_run_and_run_now_email_the_schedule_creator(outbox) -> None:
    init_db()
    application = _seed_application()
    creator = _seed_user(application, "Creator")
    clicker = _seed_user(application, "Clicker")
    schedule = _seed_schedule(application, created_by_user_id=creator.id)
    # Run now never records a starter on a scheduled run; even if one were
    # recorded, the schedule's creator is still the recipient.
    test_run = _seed_finished_run(
        application,
        schedule_id=schedule.id,
        triggered_by_name=schedule.name,
        triggered_by_user_id=clicker.id,
    )

    _send(test_run)

    [(to, _, text, _)] = outbox
    assert to == creator.email
    assert "you created the schedule “Nightly Regression”" in text


@pytest.mark.parametrize("case", ["seeded_schedule", "no_starter", "removed_user", "other_org"])
def test_unresolvable_recipient_skips_without_claiming(outbox, case, caplog) -> None:
    init_db()
    application = _seed_application()
    if case == "seeded_schedule":
        schedule = _seed_schedule(application, created_by_user_id=None)
        test_run = _seed_finished_run(application, schedule_id=schedule.id)
    elif case == "no_starter":
        test_run = _seed_finished_run(application)
    elif case == "removed_user":
        user = _seed_user(application)
        test_run = _seed_finished_run(application, triggered_by_user_id=user.id)
        with Session(engine) as session:
            session.delete(session.get(PlatformUser, user.id))
            session.commit()
        with Session(engine) as session:
            assert session.get(TestRun, test_run.id).triggered_by_user_id is None  # SET NULL
    else:
        outsider = _seed_user(_seed_application())
        test_run = _seed_finished_run(application, triggered_by_user_id=outsider.id)

    with caplog.at_level("INFO"):
        _send(test_run)

    assert outbox == []
    assert "has no recipient" in caplog.text
    assert _email_state(test_run) == (None, None)


def test_smtp_failure_releases_the_claim_so_a_retry_sends(monkeypatch) -> None:
    init_db()
    application = _seed_application()
    starter = _seed_user(application)
    test_run = _seed_finished_run(application, triggered_by_user_id=starter.id)
    sent: list = []
    failures = [OSError("connection reset")]

    def failing_once(*args):
        if failures:
            raise failures.pop()
        sent.append(args)

    monkeypatch.setattr(activities_module, "smtp_configured", lambda: True)
    monkeypatch.setattr(activities_module, "send_email", failing_once)

    with pytest.raises(OSError):
        _send(test_run)
    assert _email_state(test_run) == (None, None)

    _send(test_run)  # Temporal's retry
    assert len(sent) == 1
    assert _email_state(test_run)[1] is not None


def test_a_held_claim_blocks_another_send(outbox) -> None:
    init_db()
    application = _seed_application()
    starter = _seed_user(application)
    test_run = _seed_finished_run(application, triggered_by_user_id=starter.id)
    # Another attempt claimed it, then died before the SMTP server accepted:
    # at most once means this email is skipped rather than risk a duplicate.
    assert activities_module._claim_report_email_sync(test_run.id)
    assert not activities_module._claim_report_email_sync(test_run.id)

    _send(test_run)

    assert outbox == []
    assert _email_state(test_run)[1] is None


def test_unfinished_run_and_missing_smtp_send_nothing(monkeypatch, outbox) -> None:
    init_db()
    application = _seed_application()
    starter = _seed_user(application)
    running = _seed_finished_run(application, status="running", triggered_by_user_id=starter.id)
    _send(running)
    assert outbox == []

    done = _seed_finished_run(application, run_number=13, triggered_by_user_id=starter.id)
    monkeypatch.setattr(activities_module, "smtp_configured", lambda: False)
    _send(done)
    assert outbox == []
    assert _email_state(done) == (None, None)


def test_prepare_records_who_started_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db()
    application = _seed_application()
    starter = _seed_user(application)

    def _stop_after_the_row_exists(*_a, **_k):
        raise RuntimeError("stop before assembly")

    monkeypatch.setattr(activities_module, "_load_assembly_inputs_sync", _stop_after_the_row_exists)

    result = activities_module._prepare_test_run_sync(
        PrepareTestRunActivityInput(
            application_id=str(application.external_id),
            triggered_by_name=starter.name,
            triggered_by_user_id=str(starter.id),
        )
    )

    with Session(engine) as session:
        test_run = session.exec(
            select(TestRun).where(TestRun.external_id == uuid.UUID(result.test_run_id))
        ).one()
        assert test_run.triggered_by_user_id == starter.id
