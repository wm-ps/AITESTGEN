"""PrepareTestRunActivity / ExecuteTestActivity / FinalizeTestRunActivity —
Run All Tests feature.

`PrepareTestRunActivity` creates the `TestRun`/`TestResult` rows for every
current `TestAsset` before any Playwright process ever runs (see its own
ponytail note on why there's no execution-policy/safety-classification
gating here anymore), then assembles the project once, since it always
runs alone before any `ExecuteTestActivity` starts (no first-caller race to
guard with a file lock).

`ExecuteTestActivity` always returns a result rather than raising for a
test's own pass/fail/timeout outcome — an actual raised exception here
means a genuine infra failure (subprocess couldn't start, DB write failed),
which Temporal's own retry policy handles.

Credentials: resolved from Vault via `Application.secret_ref` (the same
mechanism discovery already uses) and passed only as subprocess env for the
one `npx playwright test` invocation — never written to a file, never
logged, never present in the assembled project's source.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai_provider.hosted import HostedAIProvider
from domain import (
    Application,
    DiscoverySettings,
    Journey,
    PlatformUser,
    Scenario,
    Schedule,
    TestAsset,
    TestResult,
    TestResultArtifact,
    TestRun,
    TestSuite,
)
from generation_worker import spec_linter
from generation_worker.activities import (
    resolve_known_application_model_sync,
    supersede_test_asset,
)
from generation_worker.typecheck import typecheck_playwright_code
from mailer import FRONTEND_BASE_URL, send_email, smtp_configured
from object_store import ObjectStore
from secrets_client.vault_client import SecretRef, VaultSecretsClient
from sqlalchemy import or_, update
from sqlmodel import Session, select
from temporalio import activity
from test_suite_assembler import (
    ALLURE_RESULTS_DIR_ENV,
    REPORT_TITLE_ENV,
    assemble_test_suite_project_to_dir,
    compute_spec_paths,
    find_login_page_evidence,
)
from workflows import (
    AUTO_HEAL_ATTEMPT_CAP,
    HEAL_CLAIM_STALE_AFTER,
    HEALABLE_STATUSES,
    TEST_RUN_STALE_AFTER,
    ExecutableTest,
    ExecuteTestActivityInput,
    FinalizeTestRunActivityInput,
    ForceCompleteTestRunActivityInput,
    GenerateAllureReportActivityInput,
    HealTestActivityInput,
    PrepareTestRunActivityInput,
    PrepareTestRunActivityResult,
    SendTestRunReportEmailActivityInput,
)

from execution_worker.db import engine
from execution_worker.live_inspection import _live_inspection_enabled, run_live_inspection
from execution_worker.project_cache import cleanup_project_dir, project_dir_for
from execution_worker.run_report_email import (
    FailedTest,
    RunCounts,
    RunEmail,
    build_email,
    run_url,
)

logger = logging.getLogger(__name__)

# A single ExecuteTestActivity call: browser launch + full scenario
# walkthrough. Generous, but bounded — an app that never responds must not
# hang a worker slot forever.
PLAYWRIGHT_RUN_TIMEOUT_SECONDS = 8 * 60

# Playwright's own console output (and the error/stack strings embedded in
# its JSON report) is colorized for a terminal — verified live against a
# real failing run. Stripped before storage so TestResult.error_message/
# stack_trace render as plain text in the UI instead of raw escape codes.
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str | None) -> str | None:
    return _ANSI_ESCAPE_RE.sub("", text) if text else text


def _resolve_bin(name: str) -> str:
    """Resolves `npm`/`npx` to a full path via `PATH`/`PATHEXT` before
    handing it to `subprocess`/`asyncio.create_subprocess_exec`.

    ponytail: on Windows, `npm`/`npx` are `.cmd` shims, not `.exe` files —
    `CreateProcess` (what both of those call without `shell=True`) only
    resolves a bare name via `PATHEXT` extension search when invoked
    through `cmd.exe`'s own shell, not directly, so passing the bare
    string `"npm"` fails with `WinError 2` on local Windows dev even
    though the exact same code works unmodified in the Linux container
    this worker actually ships in (real ELF binaries there, no shim
    lookup needed). `shutil.which` does the same `PATHEXT`-aware search
    Windows' shell does and hands back a real, fully-qualified path,
    which `CreateProcess` *can* run directly — cross-platform, not a
    Windows-only special case."""
    resolved = shutil.which(name)
    if resolved is None:
        raise RuntimeError(f"{name!r} was not found on PATH")
    return resolved


@dataclass
class _AssemblyInputs:
    test_assets: list[TestAsset]
    test_suites: list[TestSuite]
    journeys_by_id: dict[uuid.UUID, Journey]
    assets_by_suite: dict[uuid.UUID, list[TestAsset]]
    scenario_name_by_asset_id: dict[uuid.UUID, str]
    login_evidence: object


def _load_assembly_inputs_sync(
    session: Session, application: Application, test_asset_ids: set[uuid.UUID] | None = None
) -> _AssemblyInputs:
    journeys = session.exec(
        select(Journey).where(
            Journey.application_id == application.id, Journey.status == "candidate"
        )
    ).all()
    journeys_by_id = {j.id: j for j in journeys}

    test_suites = (
        session.exec(
            select(TestSuite).where(
                TestSuite.journey_id.in_(journeys_by_id.keys()),  # type: ignore[attr-defined]
                TestSuite.current.is_(True),  # type: ignore[attr-defined]
            )
        ).all()
        if journeys_by_id
        else []
    )
    suite_ids = [ts.id for ts in test_suites]

    asset_filters = [
        TestAsset.test_suite_id.in_(suite_ids),  # type: ignore[attr-defined]
        TestAsset.current.is_(True),  # type: ignore[attr-defined]
    ]
    if test_asset_ids is not None:
        # Run Suite Flow: a "Run Journey(s)" run (or a rebuild of any run's
        # project dir — see `_rebuild_project_dir_sync`) restricts to exactly
        # this set of TestAssets; `None` means unscoped (Full Suite).
        asset_filters.append(TestAsset.external_id.in_(test_asset_ids))  # type: ignore[attr-defined]

    test_assets = session.exec(select(TestAsset).where(*asset_filters)).all() if suite_ids else []
    assets_by_suite: dict[uuid.UUID, list[TestAsset]] = {}
    for asset in test_assets:
        assets_by_suite.setdefault(asset.test_suite_id, []).append(asset)

    scenario_ids = {a.scenario_id for a in test_assets}
    scenarios_by_id = {
        s.id: s
        for s in (
            session.exec(
                select(Scenario).where(Scenario.id.in_(scenario_ids))  # type: ignore[attr-defined]
            ).all()
            if scenario_ids
            else []
        )
    }
    scenario_name_by_asset_id = {
        a.id: scenarios_by_id[a.scenario_id].name
        for a in test_assets
        if a.scenario_id in scenarios_by_id
    }

    login_evidence = (
        find_login_page_evidence(session, application)
        if application.auth_method == "standard_login"
        else None
    )

    return _AssemblyInputs(
        test_assets=test_assets,
        test_suites=test_suites,
        journeys_by_id=journeys_by_id,
        assets_by_suite=assets_by_suite,
        scenario_name_by_asset_id=scenario_name_by_asset_id,
        login_evidence=login_evidence,
    )


# Serializes rebuilds within this worker process — if a crash/restart wipes
# `/tmp` mid-TestRun (the assembled project dir is local-disk, not
# persisted; see project_cache.py's own docstring), several redelivered
# ExecuteTestActivity calls can all discover the same missing directory at
# once. One lock keyed globally, not per-TestRun: rebuilding is an
# exceptional recovery path, not the hot path, so briefly serializing
# unrelated runs' rebuilds too is a fine trade for staying simple.
_project_rebuild_lock = asyncio.Lock()


async def _ensure_project_dir(test_run_id: uuid.UUID, application_id: uuid.UUID) -> None:
    dest_dir = project_dir_for(test_run_id)
    if (dest_dir / "package.json").exists():
        return
    async with _project_rebuild_lock:
        await asyncio.to_thread(_rebuild_project_dir_sync, test_run_id, application_id)


def _rebuild_project_dir_sync(test_run_id: uuid.UUID, application_id: uuid.UUID) -> None:
    dest_dir = project_dir_for(test_run_id)
    if (dest_dir / "package.json").exists():
        return
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == application_id)
        ).one()
        # Scope this rebuild to exactly the TestAssets this TestRun's own
        # TestResult rows already reference — not the Application's current
        # full scope, which would silently pull in extra (or since-changed)
        # TestAssets for a "Run Journey(s)" run. Works unmodified for a Full
        # Suite run too, since its TestResult set already covers every asset.
        run = session.exec(select(TestRun).where(TestRun.external_id == test_run_id)).one()
        test_asset_ids = set(
            session.exec(
                select(TestAsset.external_id).where(  # type: ignore[arg-type]
                    TestAsset.id.in_(  # type: ignore[attr-defined]
                        select(TestResult.test_asset_id).where(
                            TestResult.test_run_id == run.id  # type: ignore[arg-type]
                        )
                    )
                )
            ).all()
        )
        inputs = _load_assembly_inputs_sync(session, application, test_asset_ids)
        assemble_test_suite_project_to_dir(
            dest_dir,
            application,
            inputs.test_suites,
            inputs.journeys_by_id,
            inputs.assets_by_suite,
            inputs.scenario_name_by_asset_id,
            inputs.login_evidence,
        )
    _install_project(dest_dir)
    # This function only runs when the project dir was missing (evicted
    # from local disk mid-TestRun, e.g. by a worker restart) — a rebuild
    # must recreate .auth/state.json too when the app needs one, exactly
    # like PrepareTestRunActivity's own initial assembly does below (same
    # condition). Previously this rebuild path skipped it entirely: any
    # `@auth` test executed after such an eviction — including a HealTest-
    # Activity retry, which only ever calls _ensure_project_dir, never
    # PrepareTestRunActivity — failed with "ENOENT .auth/state.json" no
    # matter how many heal attempts remained.
    if inputs.login_evidence is not None:
        _run_auth_setup_once(dest_dir, application)


@activity.defn(name="PrepareTestRunActivity")
async def prepare_test_run_activity(
    input: PrepareTestRunActivityInput,
) -> PrepareTestRunActivityResult:
    return await asyncio.to_thread(_prepare_test_run_sync, input)


def _prepare_test_run_sync(input: PrepareTestRunActivityInput) -> PrepareTestRunActivityResult:
    logger.info("PrepareTestRunActivity: starting for application_id=%s", input.application_id)
    # ponytail: no ExecutionPolicy/allowlist/destructive-action gating here
    # — deliberately removed per explicit request, to let "Run All Tests"
    # work with zero setup. The `ExecutionPolicy` model/table and its
    # `GET`/`PUT` endpoints still exist (main.py) but nothing reads them on
    # this path anymore; every current TestAsset is executed unconditionally
    # against `Application.url`, regardless of `Scenario.safety_classification`.
    # To restore the original "deny by default" design: re-add a
    # `select(ExecutionPolicy)...` lookup here, short-circuit to
    # `TestRun.status="blocked"` when disabled/off-allowlist (see git history
    # for the removed version), and re-gate the per-asset loop below on
    # `classification == "SAFE" or policy.destructive_actions_permitted`.
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(input.application_id))
        ).one()

        # Claim this Application's next run_number atomically before
        # inserting the TestRun row, in the same transaction/commit below.
        # Postgres's row lock on this UPDATE (held until commit) is what
        # makes two concurrent "Run All Tests" clicks for the same
        # Application race-safe — same `update(...).where(...).values(...)`
        # idiom as `_claim_heal_sync` below, with `.returning()` added.
        run_number = session.execute(
            update(Application)
            .where(Application.id == application.id)  # type: ignore[arg-type]
            .values(next_test_run_number=Application.next_test_run_number + 1)
            .returning(Application.next_test_run_number - 1)  # type: ignore[arg-type]
        ).scalar_one()

        # Schedules feature: resolve the (external) schedule id the
        # workflow was handed into this Schedule's PK. `.first()`, not
        # `.one()`, and deliberately no `deleted_at IS NULL` filter (unlike
        # every other Schedule lookup in this codebase) — a schedule
        # soft-deleted in the window since the fire-time gate check must
        # still resolve correctly so this TestRun keeps its FK, not sink
        # the run.
        schedule_pk: uuid.UUID | None = None
        if input.schedule_id is not None:
            schedule_pk = session.exec(
                select(Schedule.id).where(Schedule.external_id == uuid.UUID(input.schedule_id))
            ).first()

        test_run = TestRun(
            application_id=application.id,
            run_number=run_number,
            schedule_id=schedule_pk,
            status="running",
            environment_snapshot=application.environment,
            target_base_url_snapshot=application.url,
            triggered_by_name=input.triggered_by_name,
            triggered_by_user_id=(
                uuid.UUID(input.triggered_by_user_id) if input.triggered_by_user_id else None
            ),
            suite_name=input.suite_name,
            started_at=datetime.now(UTC),
        )
        session.add(test_run)
        session.commit()
        session.refresh(test_run)

        # Everything below can throw before a single TestResult exists (a
        # bad query in _load_assembly_inputs_sync) or mid-loop (partway
        # through creating rows) — all of it is inside one try/except so any
        # failure here still force-closes the TestRun instead of leaving it
        # stuck "running" with an inconsistent set of TestResult rows.
        executable: list[ExecutableTest] = []
        pending_assets: list = []
        test_results_by_asset_id: dict[uuid.UUID, TestResult] = {}
        try:
            test_asset_ids = (
                {uuid.UUID(a) for a in input.test_asset_ids}
                if input.test_asset_ids is not None
                else None
            )
            inputs = _load_assembly_inputs_sync(session, application, test_asset_ids)
            test_assets = inputs.test_assets
            assets_by_suite = inputs.assets_by_suite
            scenario_name_by_asset_id = inputs.scenario_name_by_asset_id

            # Per-test-result rows first — every TestAsset gets a row before
            # any project assembly/install so a slow npm install never
            # delays the "why is my count already showing" moment for the
            # poller. Every TestAsset is executable unconditionally (see
            # this function's own ponytail note above).
            for asset in test_assets:
                test_result = TestResult(
                    test_run_id=test_run.id,
                    test_asset_id=asset.id,
                    scenario_id=asset.scenario_id,
                    status="pending",
                )
                session.add(test_result)
                session.flush()
                test_results_by_asset_id[asset.id] = test_result

            test_run.total_count = len(test_assets)
            session.add(test_run)
            session.commit()

            pending_assets = test_assets
            if not pending_assets:
                return PrepareTestRunActivityResult(
                    test_run_id=str(test_run.external_id), blocked=False, executable=[]
                )

            dest_dir = project_dir_for(test_run.external_id)
            assemble_test_suite_project_to_dir(
                dest_dir,
                application,
                inputs.test_suites,
                inputs.journeys_by_id,
                assets_by_suite,
                scenario_name_by_asset_id,
                inputs.login_evidence,
            )
            _install_project(dest_dir)
            if inputs.login_evidence is not None:
                _run_auth_setup_once(dest_dir, application)
        except Exception as exc:  # noqa: BLE001 — infra failure, not a test outcome
            for test_result in test_results_by_asset_id.values():
                test_result.status = "errored"
                test_result.error_message = f"failed to prepare the test project: {exc}"
                test_result.completed_at = datetime.now(UTC)
                session.add(test_result)
            test_run.total_count = len(test_results_by_asset_id)
            test_run.errored_count = len(test_results_by_asset_id)
            test_run.status = "completed"
            test_run.completed_at = datetime.now(UTC)
            session.add(test_run)
            session.commit()
            logger.error(
                "PrepareTestRunActivity: test_run_id=%s failed to prepare project: %s",
                test_run.external_id,
                exc,
            )
            return PrepareTestRunActivityResult(
                test_run_id=str(test_run.external_id), blocked=False, executable=[]
            )

        for asset in pending_assets:
            test_result = test_results_by_asset_id[asset.id]
            executable.append(
                ExecutableTest(
                    test_result_id=str(test_result.external_id),
                    test_asset_id=str(asset.external_id),
                )
            )

        logger.info(
            "PrepareTestRunActivity: test_run_id=%s prepared with %d executable tests",
            test_run.external_id,
            len(executable),
        )
        return PrepareTestRunActivityResult(
            test_run_id=str(test_run.external_id), blocked=False, executable=executable
        )


def _run_auth_setup_once(dest_dir: Path, application: Application) -> None:
    """Logs in exactly once per TestRun, here in `PrepareTestRunActivity` —
    which always runs alone, no concurrency to race (see module docstring)
    — instead of letting `auth.setup.ts` run again inside every individual
    `ExecuteTestActivity`'s own `npx playwright test <spec>` subprocess.
    Each of those runs concurrently against this *same* project directory
    (see `_run_playwright_test`'s docstring); without this, every one of
    them independently re-logs-in and overwrites the shared `.auth/
    state.json`, so a same-account app that only allows one active session
    (routine for a banking-style app) boots out whichever concurrent test
    was mid-run, and it lands back on the login page. One login here, then
    every `ExecuteTestActivity` invocation passes `--no-deps` to reuse the
    resulting file read-only instead of repeating the race."""
    try:
        subprocess.run(
            # `--reporter=list` overrides the project config's reporters, so
            # this login step never lands in the run's Allure report as if
            # it were one of the run's test cases.
            [_resolve_bin("npx"), "playwright", "test", "--project=setup", "--reporter=list"],
            cwd=dest_dir,
            env=_build_subprocess_env(application),
            check=True,
            capture_output=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as exc:
        # `[FIXED]` `logger.exception` on the caller side only ever logged
        # the Python traceback — `CalledProcessError.__str__` doesn't
        # include the subprocess's own stdout/stderr, so every refresh
        # failure was logged with no way to tell *why* the login itself
        # failed (real bad credentials vs. a bug in `isAuthenticated`'s own
        # verification vs. something else). Re-raised with both attached to
        # the message so it survives into that same log line.
        raise RuntimeError(
            f"auth.setup.ts failed (exit {exc.returncode}):\n"
            f"stdout: {exc.stdout.decode(errors='replace')}\n"
            f"stderr: {exc.stderr.decode(errors='replace')}"
        ) from exc


# The clear, greppable marker support/fixtures.ts's `page` fixture raises when
# an `@auth` test's restored session looks to have gone bad mid-run (see that
# file's own note) — `_maybe_retry_after_session_invalidation` below looks for
# this exact string in a failed test's `error_message`.
AUTH_SESSION_INVALID_MARKER = "AUTH_SESSION_INVALID"

# One shared account's session is used by every `@auth` test in a TestRun
# (see `_run_auth_setup_once`) — several can hit the same invalidated session
# and want to refresh it around the same moment. Global, not per-TestRun,
# matching `_project_rebuild_lock`'s own reasoning: refreshing is an
# exceptional recovery path, not the hot path.
_auth_refresh_lock = asyncio.Lock()
_last_auth_refresh_at: dict[uuid.UUID, float] = {}
# A concurrent caller that lost the race to refresh reuses whatever the
# winner just produced instead of logging in again itself — a second login
# moments later is wasted work at best, and on an app that treats concurrent
# logins as suspicious, could invalidate the very session it just fixed.
_AUTH_REFRESH_DEDUP_SECONDS = 5.0


async def _refresh_auth_once(test_run_id: uuid.UUID, dest_dir: Path, application: Application) -> None:
    async with _auth_refresh_lock:
        last = _last_auth_refresh_at.get(test_run_id, 0.0)
        if time.monotonic() - last < _AUTH_REFRESH_DEDUP_SECONDS:
            return
        # `[FIXED]` Recorded even when the attempt below fails — this used to
        # only record on success, so a genuinely broken login (bad
        # credentials, a real outage) got hammered again by every next
        # caller with zero backoff instead of being deduped like a
        # successful refresh is. Every caller still sees the real failure
        # (this re-raises), just not on top of a thundering herd of
        # identical doomed attempts.
        _last_auth_refresh_at[test_run_id] = time.monotonic()
        await asyncio.to_thread(_run_auth_setup_once, dest_dir, application)


def _install_project(dest_dir: Path) -> None:
    """`npm install`, not `npm ci` — the assembled project has no
    `package-lock.json` (generated fresh every run, never checked into
    anything a lockfile could pin against). Chromium is pre-installed at the
    Docker image layer (see this app's Dockerfile), but `playwright install`
    still runs per-project as a cheap cache-hit safety net in case the
    pinned `@playwright/test` version in `package.json` ever drifts from the
    image's pre-installed browser revision."""
    subprocess.run(
        [_resolve_bin("npm"), "install"], cwd=dest_dir, check=True, capture_output=True, timeout=300
    )
    subprocess.run(
        [_resolve_bin("npx"), "playwright", "install", "chromium"],
        cwd=dest_dir,
        check=True,
        capture_output=True,
        timeout=300,
    )


@dataclass
class _ExecutionContext:
    application: Application
    test_result_pk: uuid.UUID
    spec_path: str


@activity.defn(name="ExecuteTestActivity")
async def execute_test_activity(input: ExecuteTestActivityInput) -> str:
    context = await asyncio.to_thread(_load_execution_context_sync, input)
    if context is None:
        # Already handled by a prior Temporal attempt for this TestResult
        # (at-least-once retry) — idempotent no-op, matches
        # playwright_generation_activity's own re-check convention.
        logger.info(
            "ExecuteTestActivity: test_result_id=%s already handled, skipping", input.test_result_id
        )
        return input.test_result_id

    logger.info(
        "ExecuteTestActivity: test_result_id=%s starting spec_path=%s",
        input.test_result_id,
        context.spec_path,
    )
    test_run_id = uuid.UUID(input.test_run_id)
    await _ensure_project_dir(test_run_id, uuid.UUID(input.application_id))
    env = await asyncio.to_thread(_build_subprocess_env, context.application)
    project_dir = project_dir_for(test_run_id)
    outcome = await _run_playwright_test(
        project_dir,
        context.spec_path,
        env,
        PLAYWRIGHT_RUN_TIMEOUT_SECONDS,
        input.test_result_id,
    )
    # `[FIXED]` Every `@auth` test in this TestRun shares the ONE session
    # `_run_auth_setup_once` established — a concurrently-running test that
    # logs out, changes the password, or otherwise invalidates the account's
    # session invalidates it for every other `@auth` test still using that
    # same snapshot. support/fixtures.ts detects this and raises a clear,
    # marked error instead of (or alongside) a confusing locator failure —
    # retried here exactly once, against a freshly re-established session,
    # rather than reported as a flaky/broken test. A retry that fails again
    # (a genuinely broken credential, an app that's actually down) is
    # reported as-is, not retried further.
    if outcome["status"] == "failed" and AUTH_SESSION_INVALID_MARKER in (
        outcome.get("error_message") or ""
    ):
        logger.warning(
            "ExecuteTestActivity: test_result_id=%s hit an invalidated session — "
            "refreshing auth and retrying once",
            input.test_result_id,
        )
        try:
            await _refresh_auth_once(test_run_id, project_dir, context.application)
        except Exception:  # noqa: BLE001 — retry is best-effort; report the original outcome
            logger.exception(
                "ExecuteTestActivity: test_result_id=%s auth refresh failed, keeping "
                "original outcome",
                input.test_result_id,
            )
        else:
            outcome = await _run_playwright_test(
                project_dir,
                context.spec_path,
                env,
                PLAYWRIGHT_RUN_TIMEOUT_SECONDS,
                input.test_result_id,
            )
    await asyncio.to_thread(_persist_test_result_sync, input.test_run_id, context, outcome)
    logger.info(
        "ExecuteTestActivity: test_result_id=%s finished status=%s",
        input.test_result_id,
        outcome["status"],
    )
    return input.test_result_id


def _load_execution_context_sync(input: ExecuteTestActivityInput) -> _ExecutionContext | None:
    with Session(engine) as session:
        test_result = session.exec(
            select(TestResult).where(TestResult.external_id == uuid.UUID(input.test_result_id))
        ).one()
        if test_result.status != "pending":
            return None

        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(input.application_id))
        ).one()
        test_asset = session.exec(
            select(TestAsset).where(TestAsset.external_id == uuid.UUID(input.test_asset_id))
        ).one()

        # Recomputed fresh from the same DB-sourced inputs Prepare used —
        # never persisted, never relies on in-memory state surviving across
        # separate Activity invocations (see compute_spec_paths' docstring).
        # Scoped to the whole Application (not just this one TestSuite/
        # TestAsset) — `dedupe_slugs` only disambiguates a Journey-name-slug
        # collision when it sees every current TestSuite at once, same as
        # `_write_project_files` did when it actually wrote the project to
        # disk; recomputing from a single suite can never reproduce a suffix
        # assigned against that wider set, and silently points at the wrong
        # (or a nonexistent) spec path.
        inputs = _load_assembly_inputs_sync(session, application)
        spec_path_by_asset_id = compute_spec_paths(
            test_suites=inputs.test_suites,
            journeys_by_id=inputs.journeys_by_id,
            assets_by_suite=inputs.assets_by_suite,
            scenario_name_by_asset_id=inputs.scenario_name_by_asset_id,
        )

        return _ExecutionContext(
            application=application,
            test_result_pk=test_result.id,
            spec_path=spec_path_by_asset_id[test_asset.id],
        )


def _build_subprocess_env(application: Application) -> dict:
    vault_client = VaultSecretsClient()
    credential = vault_client.resolve(SecretRef(path=application.secret_ref))
    env = dict(os.environ)
    # Playwright has no "screenshot only on pass" mode — capture every test's
    # final screen when passed ones are wanted at all, and let
    # `_persist_test_result_sync` drop the ones the setting excludes.
    if _load_screenshot_capture_sync() != "failed":
        env["AITESTGEN_SCREENSHOT"] = "on"
    if application.auth_method == "sso_session_reuse":
        env["AITESTGEN_STORAGE_STATE"] = credential.decode()
    else:
        creds = json.loads(credential.decode())
        env["AITESTGEN_LOGIN_USERNAME"] = creds["username"]
        env["AITESTGEN_LOGIN_PASSWORD"] = creds["password"]
    return env


ALLURE_RESULTS_DIR = "allure-results"
# Written next to a TestResult's attempt folders each time Vantage persists
# an outcome for it — the only link from a saved TestResult to the one
# attempt that produced it (see `_write_allure_final_marker`).
ALLURE_FINAL_MARKER = "final.json"


def _allure_attempts_supported(project_dir: Path) -> bool:
    """Whether this project can write Allure results into a per-invocation
    folder. Needs allure-playwright installed *and* a playwright.config.ts
    whose reporter list reads ALLURE_RESULTS_DIR_ENV (see
    test_suite_assembler's `_ALLURE_REPORTER_LINES`). Otherwise — a partly
    failed `npm install`, or a project dir assembled before this config —
    the test runs with plain `--reporter=json`: running tests never depends
    on the report."""
    if not (project_dir / "node_modules" / "allure-playwright").is_dir():
        return False
    try:
        config = (project_dir / "playwright.config.ts").read_text(encoding="utf-8")
    except OSError:
        return False
    return ALLURE_RESULTS_DIR_ENV in config


async def _run_playwright_test(
    project_dir: Path,
    spec_path: str,
    env: dict,
    timeout_seconds: float,
    test_result_id: str,
) -> dict:
    """Runs `npx playwright test <spec_path>` with the JSON reporter in
    `project_dir`. Never raises for the test's own outcome.

    `--output` is set to a per-`test_result_id` subdirectory — Playwright's
    default `test-results/` output directory is shared by the whole
    project, and this activity's own bounded concurrency means several
    `ExecuteTestActivity` calls can run against the *same* assembled
    project directory at once; without an isolated output dir, one test's
    screenshot/trace scan could pick up another concurrently-running test's
    artifacts. Verified against a real `npx playwright test` run (schema
    below is not guessed): the target spec's own project (`chromium`)
    depends on the `setup` project (`auth.setup.ts`) — skipped here via
    `--no-deps` since `PrepareTestRunActivity` already ran it once (see
    `_run_auth_setup_once`), but a *pre-`--no-deps`* run with a failed
    setup showed the target spec with `results: []` and a top-level
    `status: "skipped"` — never its own `results[-1]`. This parser still
    checks the *target file's own suite* specifically rather than just
    returning the first suite with any results, so that shape (or a
    project without a `setup` dependency at all) both still resolve to the
    test's own outcome instead of some other suite's.

    ponytail: parses only the JSON-reporter fields this activity actually
    needs (final outcome, duration, first error) rather than the full
    reporter schema (multiple retries per test, richer attachment
    metadata) — revisit if a real run surfaces a shape this doesn't handle.
    """
    output_dir = f"test-results/{test_result_id}"
    # Every invocation — first run, auth-refresh rerun, infra retry, heal
    # rerun — gets its own Allure results folder, so the report can use
    # exactly the one attempt whose outcome Vantage persisted (see
    # `_write_allure_final_marker`) and nothing from the others. The config's
    # reporter list switches to `json` + allure-playwright when the env var
    # is set, so `--reporter` stays off the command line in that case.
    allure_attempt: str | None = None
    if _allure_attempts_supported(project_dir):
        allure_attempt = uuid.uuid4().hex
        env = {
            **env,
            ALLURE_RESULTS_DIR_ENV: f"{ALLURE_RESULTS_DIR}/{test_result_id}/{allure_attempt}",
        }
        reporter_args: list[str] = []
    else:
        reporter_args = ["--reporter=json"]
    proc = await asyncio.create_subprocess_exec(
        _resolve_bin("npx"),
        "playwright",
        "test",
        spec_path,
        *reporter_args,
        f"--output={output_dir}",
        # `PrepareTestRunActivity` already ran the `setup` project's login
        # once (see `_run_auth_setup_once`) — skip re-running it as a
        # dependency here. Several of these invocations run concurrently
        # against the same project dir; without `--no-deps` each would
        # re-login and overwrite the shared `.auth/state.json`, racing
        # exactly the scenario `_run_auth_setup_once` exists to avoid. A
        # no-op when the target spec has no dependency project at all.
        "--no-deps",
        cwd=str(project_dir),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning(
            "ExecuteTestActivity: test_result_id=%s timed out after %ds",
            test_result_id,
            timeout_seconds,
        )
        return {
            "status": "timed_out",
            "duration_ms": int(timeout_seconds * 1000),
            "error_message": "playwright test exceeded the execution timeout",
            "stack_trace": None,
            "console_output": None,
            "artifact_paths": [],
            "allure_attempt": allure_attempt,
        }

    result = _parse_playwright_report(stdout, stderr, spec_path)
    # Every artifact on disk — `_persist_test_result_sync` decides which are
    # kept (Screenshot capture setting), so a passed test's screenshot isn't
    # discarded here.
    result["artifact_paths"] = _find_artifacts(project_dir / output_dir)
    result["allure_attempt"] = allure_attempt
    return result


def _parse_playwright_report(stdout: bytes, stderr: bytes, spec_path: str) -> dict:
    console_output = _strip_ansi(stderr.decode("utf-8", errors="replace")[-4000:]) or None
    try:
        report = json.loads(stdout.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {
            "status": "errored",
            "duration_ms": None,
            "error_message": "playwright produced no parseable JSON report",
            "stack_trace": None,
            "console_output": console_output,
        }

    # `suite.file`/`spec.file` are relative to `testDir` ("tests/"), while
    # `spec_path` (from compute_spec_paths) is relative to the project
    # root — strip that one leading segment, and normalize separators
    # (Playwright reports them OS-native; verified backslash-separated on
    # Windows in local testing).
    target_file = spec_path.removeprefix("tests/").replace("\\", "/")

    for suite in report.get("suites", []):
        suite_file = (suite.get("file") or "").replace("\\", "/")
        if suite_file != target_file:
            continue
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                results = test.get("results") or []
                if results:
                    result = results[-1]
                    status = {
                        "passed": "passed",
                        "failed": "failed",
                        "timedOut": "timed_out",
                    }.get(result.get("status"), "errored")
                    # `[FIXED]` Used to take only the FIRST error (`result["error"]`,
                    # falling back to `errors[0]`) — an `@auth` test whose restored
                    # session went bad mid-run gets a SECOND error appended by
                    # support/fixtures.ts's page fixture (see its own note), always
                    # after the original, now-misleading locator/assertion failure.
                    # Taking only the first one silently dropped that clarifying
                    # signal, which `_maybe_retry_after_session_invalidation` below
                    # greps `error_message` for. Concatenate every error instead —
                    # nothing from before is lost, and the clarifying one (when
                    # present) is now actually visible/greppable.
                    raw_errors = result.get("errors") or (
                        [result["error"]] if result.get("error") else []
                    )
                    messages = [
                        e.get("message") for e in raw_errors if isinstance(e, dict) and e.get("message")
                    ]
                    error_message = "\n\n".join(messages) if messages else None
                    stack_trace = next(
                        (e.get("stack") for e in raw_errors if isinstance(e, dict) and e.get("stack")),
                        None,
                    )
                    return {
                        "status": status,
                        "duration_ms": result.get("duration"),
                        "error_message": _strip_ansi(error_message),
                        "stack_trace": _strip_ansi(stack_trace),
                        "console_output": console_output,
                    }

                # No result recorded for this project — verified live: this
                # happens when a dependency project (auth.setup.ts) failed
                # first, which skips every project depending on it before
                # the target test ever ran.
                return {
                    "status": "errored",
                    "duration_ms": None,
                    "error_message": (
                        f"test was never executed (top-level status "
                        f"{test.get('status')!r}) — its setup dependency likely failed"
                    ),
                    "stack_trace": None,
                    "console_output": console_output,
                }

    return {
        "status": "errored",
        "duration_ms": None,
        "error_message": f"playwright report contained no suite matching {target_file!r}",
        "stack_trace": None,
        "console_output": console_output,
    }


def _find_artifacts(output_dir: Path) -> list[Path]:
    if not output_dir.exists():
        return []
    return [p for p in output_dir.rglob("*") if p.is_file() and p.suffix in (".png", ".zip")]


def _load_screenshot_capture_sync() -> str:
    with Session(engine) as session:
        settings = session.exec(select(DiscoverySettings)).first()
        return settings.screenshot_capture if settings else "failed"


def _keep_artifact(artifact_type: str, status: str, screenshot_capture: str) -> bool:
    """Traces stay failure-only; a screenshot is kept per the Screenshot
    capture setting ("failed" = any non-passed status)."""
    passed = status == "passed"
    if artifact_type == "trace":
        return not passed
    return screenshot_capture == "all" or (screenshot_capture == "passed") == passed


def _tally_counts(results: list[TestResult]) -> dict[str, int]:
    counts = {status: 0 for status in ("passed", "failed", "timed_out", "errored", "blocked")}
    for result in results:
        if result.status in counts:
            counts[result.status] += 1
    return counts


def _persist_test_result_sync(test_run_id: str, context: _ExecutionContext, outcome: dict) -> None:
    """`test_run_id` is a plain str (the TestRun's external id, used only to
    scope ObjectStore artifact keys) rather than a whole
    `ExecuteTestActivityInput`, so `HealTestActivity` — which has its own
    `HealTestActivityInput`, not an `ExecuteTestActivityInput` — can reuse
    this same persist-and-retally logic for a heal attempt's rerun outcome
    without a fake/duck-typed input object."""
    with Session(engine) as session:
        test_result = session.exec(
            select(TestResult).where(TestResult.id == context.test_result_pk)
        ).one()
        test_result.status = outcome["status"]
        test_result.duration_ms = outcome.get("duration_ms")
        test_result.error_message = outcome.get("error_message")
        test_result.stack_trace = outcome.get("stack_trace")
        test_result.console_output = outcome.get("console_output")
        test_result.started_at = test_result.started_at or datetime.now(UTC)
        test_result.completed_at = datetime.now(UTC)
        session.add(test_result)
        session.flush()

        # A heal attempt reruns this same TestResult for real — each rerun
        # would otherwise pile its own screenshot/trace on top of every
        # prior attempt's, showing the whole heal history instead of just
        # what the *current* code produces. Only the latest run's artifacts
        # are ever meaningful (they're what the current TestAsset code
        # actually did), so the prior set is deleted, both from the DB and
        # the underlying objects, before the new one is recorded.
        prior_artifacts = session.exec(
            select(TestResultArtifact).where(TestResultArtifact.test_result_id == test_result.id)
        ).all()
        if prior_artifacts:
            object_store = ObjectStore()
            for artifact in prior_artifacts:
                object_store.delete(artifact.object_store_key)
                session.delete(artifact)
            session.flush()

        screenshot_capture = _load_screenshot_capture_sync()
        for path in outcome.get("artifact_paths", []):
            artifact_type = "trace" if path.suffix == ".zip" else "screenshot"
            if not _keep_artifact(artifact_type, outcome["status"], screenshot_capture):
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            content_type = "application/zip" if artifact_type == "trace" else "image/png"
            key = ObjectStore().put_test_artifact(
                data, uuid.UUID(test_run_id), content_type=content_type
            )
            session.add(
                TestResultArtifact(
                    test_result_id=test_result.id,
                    artifact_type=artifact_type,
                    object_store_key=key,
                    content_type=content_type,
                    size_bytes=len(data),
                )
            )

        # Live progress for the polling frontend — without this, StatTiles
        # sit at 0 for the whole run since FinalizeTestRunActivity only
        # tallies once, at the very end.
        run_results = session.exec(
            select(TestResult).where(TestResult.test_run_id == test_result.test_run_id)
        ).all()
        counts = _tally_counts(run_results)
        test_run = session.exec(
            select(TestRun).where(TestRun.id == test_result.test_run_id)
        ).one()
        test_run.passed_count = counts["passed"]
        test_run.failed_count = counts["failed"]
        test_run.timed_out_count = counts["timed_out"]
        test_run.errored_count = counts["errored"]
        test_run.blocked_count = counts["blocked"]
        session.add(test_run)

        session.commit()
        test_result_external_id = str(test_result.external_id)
        completed_at = test_result.completed_at

    _write_allure_final_marker(
        project_dir_for(uuid.UUID(test_run_id)),
        test_result_external_id,
        outcome.get("allure_attempt"),
        outcome["status"],
        completed_at,
    )


def _as_utc(value: datetime) -> datetime:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)


def _timestamp_key(value: datetime | None) -> str | None:
    return None if value is None else _as_utc(value).isoformat()


def _write_allure_final_marker(
    project_dir: Path,
    test_result_id: str,
    attempt: str | None,
    status: str,
    completed_at: datetime | None,
) -> None:
    """Records which attempt folder holds the outcome just persisted for
    this TestResult — written only *after* the commit, so it can never name
    an attempt whose outcome didn't land. An attempt that ran but was never
    persisted (a crash or activity timeout mid-run) is simply never named.
    The status and `completed_at` are copied from the committed row so
    `_collect_final_allure_results` can tell a stale marker (a crash between
    a later commit and its marker write) from a current one. `attempt` is
    None when the invocation couldn't write Allure results at all.

    Best-effort: a marker that can't be written only means the report shows
    this test without its detailed results, never a failed test run."""
    if not project_dir.is_dir():
        return
    try:
        marker_dir = project_dir / ALLURE_RESULTS_DIR / test_result_id
        marker_dir.mkdir(parents=True, exist_ok=True)
        tmp = marker_dir / f"{ALLURE_FINAL_MARKER}.tmp"
        tmp.write_text(
            json.dumps(
                {"attempt": attempt, "status": status, "completed_at": _timestamp_key(completed_at)}
            ),
            encoding="utf-8",
        )
        os.replace(tmp, marker_dir / ALLURE_FINAL_MARKER)
    except OSError:
        logger.warning(
            "could not write the Allure final-attempt marker for test_result_id=%s",
            test_result_id,
            exc_info=True,
        )


# --- Self-healing (HealTestActivity) --------------------------------------

# A same-code, no-AI-call rerun when the *current* failure is infra, not a
# code defect — bounds a persistently-down target application to one extra
# rerun per check rather than spinning this activity forever. Never
# increments either of TestResult's auto_/manual_heal_attempt_count.
MAX_INFRA_RETRIES_PER_CALL = 1

_INFRA_ERROR_SIGNATURES = (
    "playwright produced no parseable json report",  # _parse_playwright_report — process/report itself broke
    "its setup dependency likely failed",  # auth.setup.ts (login) failed, not this test's code
    "playwright report contained no suite matching",  # assembly/config issue
    "playwright test exceeded the execution timeout",  # _run_playwright_test — the WHOLE process was killed after
    # PLAYWRIGHT_RUN_TIMEOUT_SECONDS; distinct from Playwright's own
    # per-test `timedOut` result (a real, healable locator/assertion
    # timeout with its own, different error_message) — only this exact
    # fixed string means the whole browser/subprocess hung, an environment
    # problem, not this test's own logic.
)


def _is_infra_failure(status: str, error_message: str | None) -> bool:
    if status not in ("errored", "timed_out"):
        return False
    if not error_message:
        return True
    lowered = error_message.lower()
    return any(sig in lowered for sig in _INFRA_ERROR_SIGNATURES)


# Deterministic trigger for live inspection (heal_test_activity's loop,
# below) — mirrors _is_infra_failure's style. Only ever checked AFTER
# _is_infra_failure has already had first say (the loop's own infra break
# runs before this), so an infra-classified failure never reaches this
# classifier at all: infra failures must never consume a heal attempt OR
# trigger a live-browser inspection over the same root cause. These five
# patterns map to the five categories a stale/broken locator actually shows
# up as: a locator Playwright waited for and never found, a locator that now
# matches more than one element (UI changed shape), an element that's been
# removed from the DOM since the test was written, a plain not-found/no-match
# message for dynamic content that hasn't rendered (yet, or ever, if the app
# changed), and the shared `ensureVisible` helper's own custom error (a
# locator that resolved but never became visible even after an explicit
# scroll-into-view — the same stale/wrong-locator or changed-UI root cause
# as the other four, just worded by this project's own helper instead of by
# Playwright itself).
_LOCATOR_FAILURE_PATTERNS = (
    re.compile(r"waiting for (?:locator|selector)", re.IGNORECASE),
    re.compile(r"strict mode violation.*resolved to \d+ elements", re.IGNORECASE),
    re.compile(r"element is not attached to (?:the )?dom", re.IGNORECASE),
    re.compile(r"no elements? found for selector|element(?:s)? not found", re.IGNORECASE),
    re.compile(r"is not visible even after scrolling", re.IGNORECASE),
)


def _is_locator_failure(status: str, error_message: str | None) -> bool:
    """Deterministic — never left to AI judgment alone. True only for a
    failure that looks like a stale/invalid locator, changed UI, a missing
    element, or unrendered dynamic content; used to gate whether
    heal_test_activity's loop launches a live Playwright inspection before
    asking the AI for a fix."""
    if not error_message:
        return False
    return any(pattern.search(error_message) for pattern in _LOCATOR_FAILURE_PATTERNS)


async def _run_playwright_with_infra_retry(
    project_dir: Path, spec_path: str, env: dict, timeout_seconds: float, test_result_id: str
) -> dict:
    """Runs the test; if the outcome is an infra failure (not a code
    defect), reruns the *same* code up to MAX_INFRA_RETRIES_PER_CALL more
    times with no AI call involved — this is what bounds a persistently-down
    target application to one extra rerun per check instead of spinning
    HealTestActivity forever."""
    outcome = await _run_playwright_test(project_dir, spec_path, env, timeout_seconds, test_result_id)
    retries = 0
    while (
        _is_infra_failure(outcome["status"], outcome.get("error_message"))
        and retries < MAX_INFRA_RETRIES_PER_CALL
    ):
        retries += 1
        outcome = await _run_playwright_test(project_dir, spec_path, env, timeout_seconds, test_result_id)
    return outcome


def _normalize_failure_signature(error_message: str | None) -> str:
    """Coarse fingerprint for the no-progress guard. Strips digits (a
    duration/timestamp/line-number that legitimately varies run to run
    without the underlying failure actually changing) so two
    functionally-identical errors don't compare unequal just because of
    incidental noise."""
    if not error_message:
        return ""
    return re.sub(r"\d+", "", error_message.lower()).strip()[:500]


def _claim_heal_sync(test_result_external_id: str) -> bool:
    """Concurrency guard: atomically claims this TestResult for healing by
    setting `heal_started_at` only if no other claim is currently active (or
    the existing one is stale) — a single conditional UPDATE, not a
    check-then-set, so an automatic heal (from `run_one`, right after
    `ExecuteTestActivity`) and a manual retry click can never both proceed
    against the same TestResult at once. Returns whether *this* call won the
    claim."""
    now = datetime.now(UTC)
    stale_before = now - HEAL_CLAIM_STALE_AFTER
    with Session(engine) as session:
        result = session.execute(
            update(TestResult)
            .where(
                TestResult.external_id == uuid.UUID(test_result_external_id),  # type: ignore[arg-type]
                or_(
                    TestResult.heal_started_at.is_(None),  # type: ignore[attr-defined]
                    TestResult.heal_started_at < stale_before,  # type: ignore[operator]
                ),
            )
            .values(heal_started_at=now)
        )
        session.commit()
        return (result.rowcount or 0) > 0  # type: ignore[attr-defined]


def _release_heal_claim_sync(test_result_external_id: str) -> None:
    with Session(engine) as session:
        session.execute(
            update(TestResult)
            .where(TestResult.external_id == uuid.UUID(test_result_external_id))  # type: ignore[arg-type]
            .values(heal_started_at=None)
        )
        session.commit()


@dataclass
class _HealContext:
    test_result_pk: uuid.UUID
    application: Application
    scenario: Scenario
    known_pages: list[dict[str, str]]
    known_locators: list[dict[str, str]]
    # Resolved once per HealTestActivity invocation (same lifecycle as
    # known_pages/known_locators above), supplied on every AI call within
    # the loop — the same numeric-vs-string field hint original generation
    # already gives the model, missing here before was a real cause of
    # heal repeatedly regenerating the same TS2345 type mismatch.
    field_input_types: dict[str, str]
    spec_path: str
    # The resolved cap for *this* invocation's origin — AUTO_HEAL_ATTEMPT_CAP
    # for automatic (input.triggered_manually=False), or
    # DiscoverySettings.max_heal_attempts for manual. Never a shared value.
    attempt_cap: int


def _load_heal_context_sync(input: HealTestActivityInput) -> _HealContext | None:
    with Session(engine) as session:
        test_result = session.exec(
            select(TestResult).where(TestResult.external_id == uuid.UUID(input.test_result_id))
        ).one()
        discovery_settings = session.exec(select(DiscoverySettings)).one()
        if input.triggered_manually:
            current_count = test_result.manual_heal_attempt_count
            attempt_cap = discovery_settings.max_heal_attempts
        else:
            current_count = test_result.auto_heal_attempt_count
            attempt_cap = AUTO_HEAL_ATTEMPT_CAP
        if test_result.status not in HEALABLE_STATUSES or current_count >= attempt_cap:
            # Not eligible — already passed/blocked, or this origin's own
            # budget is already spent. Safe no-op: this is what lets
            # HealTestActivity be called unconditionally after every
            # ExecuteTestActivity with no branching in workflow code.
            return None

        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(input.application_id))
        ).one()
        test_asset = session.exec(
            select(TestAsset).where(
                TestAsset.scenario_id == test_result.scenario_id,
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).one()
        test_suite = session.exec(
            select(TestSuite).where(TestSuite.id == test_asset.test_suite_id)
        ).one()
        journey = session.exec(select(Journey).where(Journey.id == test_suite.journey_id)).one()
        scenario = session.exec(select(Scenario).where(Scenario.id == test_asset.scenario_id)).one()
        known_pages, known_locators, _, known_page_ids = resolve_known_application_model_sync(
            session, journey.id, scenario
        )
        # Same mechanism original generation uses (generation_worker/
        # activities.py) — the real captured HTML input_type per field name,
        # so the AI can tell a numeric field from a text one instead of
        # guessing (the "wrap it in Number(...)" prompt rule needs this
        # concrete signal to actually fire).
        field_input_types = spec_linter.field_input_types_for_pages(session, known_page_ids)
        # Scoped to the whole Application, not just this one TestSuite/
        # TestAsset — see `_load_execution_context_sync`'s own note on why a
        # single-suite recompute can never reproduce a `dedupe_slugs` suffix
        # that assembly assigned against the full current-TestSuite set.
        inputs = _load_assembly_inputs_sync(session, application)
        spec_path_by_asset_id = compute_spec_paths(
            test_suites=inputs.test_suites,
            journeys_by_id=inputs.journeys_by_id,
            assets_by_suite=inputs.assets_by_suite,
            scenario_name_by_asset_id=inputs.scenario_name_by_asset_id,
        )
        return _HealContext(
            test_result_pk=test_result.id,
            application=application,
            scenario=scenario,
            known_pages=known_pages,
            known_locators=known_locators,
            field_input_types=field_input_types,
            spec_path=spec_path_by_asset_id[test_asset.id],
            attempt_cap=attempt_cap,
        )


@dataclass
class _HealLoopState:
    status: str
    error_message: str | None
    stack_trace: str | None
    console_output: str | None
    heal_attempt_count: int
    test_asset: TestAsset


def _load_heal_loop_state_sync(
    test_result_pk: uuid.UUID, scenario_id: uuid.UUID, triggered_manually: bool
) -> _HealLoopState:
    """Reloaded fresh at the top of every loop iteration (rather than
    threading a stale in-memory TestAsset/TestResult across iterations) —
    each attempt's `supersede_test_asset`/typecheck-failure write commits in
    its own short transaction (see `_record_heal_supersede_sync`/
    `_record_typecheck_failure_sync` below), so re-reading here is always
    the truth after the previous iteration's write, and a Temporal-level
    retry of this whole activity after a worker crash mid-loop resumes from
    exactly what was actually committed rather than duplicating or losing
    an attempt."""
    with Session(engine) as session:
        test_result = session.exec(select(TestResult).where(TestResult.id == test_result_pk)).one()
        test_asset = session.exec(
            select(TestAsset).where(
                TestAsset.scenario_id == scenario_id,
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).one()
        return _HealLoopState(
            status=test_result.status,
            error_message=test_result.error_message,
            stack_trace=test_result.stack_trace,
            console_output=test_result.console_output,
            heal_attempt_count=(
                test_result.manual_heal_attempt_count
                if triggered_manually
                else test_result.auto_heal_attempt_count
            ),
            test_asset=test_asset,
        )


def _fetch_latest_screenshot_sync(test_result_pk: uuid.UUID) -> bytes | None:
    with Session(engine) as session:
        artifact = session.exec(
            select(TestResultArtifact)
            .where(
                TestResultArtifact.test_result_id == test_result_pk,
                TestResultArtifact.artifact_type == "screenshot",
            )
            .order_by(TestResultArtifact.created_at.desc())  # type: ignore[arg-type]
        ).first()
        if artifact is None:
            return None
        key = artifact.object_store_key
    try:
        return ObjectStore().get(key)
    except Exception:  # noqa: BLE001 — best-effort context, never blocks healing
        logger.warning(
            "HealTestActivity: test_result_id=%s failed to fetch screenshot for AI context, "
            "continuing without it",
            test_result_pk,
        )
        return None


HEAL_TYPECHECK_ERROR_PREFIX = "generated fix failed typecheck: "


def _record_typecheck_failure_sync(
    test_result_pk: uuid.UUID, tsc_errors: list[str], triggered_manually: bool
) -> None:
    with Session(engine) as session:
        test_result = session.exec(select(TestResult).where(TestResult.id == test_result_pk)).one()
        if triggered_manually:
            test_result.manual_heal_attempt_count += 1
        else:
            test_result.auto_heal_attempt_count += 1
        test_result.error_message = HEAL_TYPECHECK_ERROR_PREFIX + "; ".join(tsc_errors[:5])
        session.add(test_result)
        session.commit()


def _record_heal_supersede_sync(
    test_result_pk: uuid.UUID, prior_test_asset_id: uuid.UUID, code: str, triggered_manually: bool
) -> None:
    """Typecheck passed — promote immediately (a healed candidate becomes
    `current` the moment it typechecks clean, regardless of what the
    subsequent real run does) and record it as this attempt's
    `healed_test_asset_id`. Spec-linter warnings are deliberately not
    re-run against healed code — this feature only needs the fix to
    typecheck and actually pass; re-linting is the original generation
    path's own concern, not asked for here."""
    with Session(engine) as session:
        prior = session.exec(select(TestAsset).where(TestAsset.id == prior_test_asset_id)).one()
        new_asset = supersede_test_asset(
            session,
            prior,
            code=code,
            requires_auth=prior.requires_auth,
            warnings=[],
            status="ready",
            primary_page_id=prior.primary_page_id,
        )
        session.flush()
        test_result = session.exec(select(TestResult).where(TestResult.id == test_result_pk)).one()
        if triggered_manually:
            test_result.manual_heal_attempt_count += 1
        else:
            test_result.auto_heal_attempt_count += 1
        test_result.healed_test_asset_id = new_asset.id
        session.add(test_result)
        session.commit()


@activity.defn(name="HealTestActivity")
async def heal_test_activity(input: HealTestActivityInput) -> None:
    """Owns the entire bounded, iterative self-heal loop for one
    TestResult — called unconditionally after every ExecuteTestActivity in
    the automatic path, and once more (same activity, same logic) from
    HealTestExecutionWorkflow for the manual-retry path. Never raises for a
    heal attempt's own AI/typecheck/execution outcome; a genuine infra
    failure here (subprocess couldn't start, DB write failed) is what
    Temporal's own retry_policy on this activity call handles.

    input.triggered_manually selects which of TestResult's two independent
    budgets this invocation reads and increments: False (automatic)
    spends only auto_heal_attempt_count, capped at the fixed
    AUTO_HEAL_ATTEMPT_CAP; True (manual) spends only
    manual_heal_attempt_count, capped at the admin-configurable
    DiscoverySettings.max_heal_attempts. Neither origin can ever consume
    the other's budget.

    The heal loop, one iteration:
      real execution -> failure evidence -> AI diagnosis -> targeted edit ->
      typecheck -> update current TestAsset -> real re-execution -> new
      failure evidence -> (pass | no-progress stop | loop again), bounded by
      this invocation's own attempt_cap.
    """
    claimed = await asyncio.to_thread(_claim_heal_sync, input.test_result_id)
    if not claimed:
        logger.info(
            "HealTestActivity: test_result_id=%s already being healed (automatic or manual), "
            "skipping",
            input.test_result_id,
        )
        return
    try:
        ctx = await asyncio.to_thread(_load_heal_context_sync, input)
        if ctx is None:
            logger.info(
                "HealTestActivity: test_result_id=%s not eligible for healing, skipping",
                input.test_result_id,
            )
            return

        await _ensure_project_dir(uuid.UUID(input.test_run_id), uuid.UUID(input.application_id))
        project_dir = project_dir_for(uuid.UUID(input.test_run_id))
        env = await asyncio.to_thread(_build_subprocess_env, ctx.application)
        exec_context = _ExecutionContext(
            application=ctx.application, test_result_pk=ctx.test_result_pk, spec_path=ctx.spec_path
        )

        # Step 2 — infra check on the failure that triggered healing, before
        # any AI call or attempt is spent. A same-code, no-AI-call rerun;
        # still infra after that one bounded retry stops here entirely,
        # leaving this origin's attempt count untouched for a later trigger
        # once the environment issue clears.
        initial_state = await asyncio.to_thread(
            _load_heal_loop_state_sync, ctx.test_result_pk, ctx.scenario.id, input.triggered_manually
        )
        if _is_infra_failure(initial_state.status, initial_state.error_message):
            outcome = await _run_playwright_with_infra_retry(
                project_dir, ctx.spec_path, env, PLAYWRIGHT_RUN_TIMEOUT_SECONDS, input.test_result_id
            )
            await asyncio.to_thread(_persist_test_result_sync, input.test_run_id, exec_context, outcome)
            if _is_infra_failure(outcome["status"], outcome.get("error_message")):
                logger.info(
                    "HealTestActivity: test_result_id=%s still an infra failure after one "
                    "bounded retry, stopping",
                    input.test_result_id,
                )
                return

        # Step 3 — the bounded, iterative heal loop.
        # Bounded AI-requested live-inspection fallback (see
        # _PLAYWRIGHT_FAILURE_CONTEXT's own closing instruction): the
        # deterministic classifier below is the primary trigger; this flag
        # carries the *previous* iteration's AI response into the *next*
        # iteration's decision — never a same-iteration round-trip, and
        # fully overwritten every iteration right after that iteration's own
        # AI call, so it never accumulates across more than one attempt.
        ai_requested_live_inspection = False
        # Carries the immediately-previous typecheck-failed candidate + its
        # exact tsc diagnostics into the next attempt (generate_playwright's
        # existing repair mechanism, the same one generation-worker's own
        # original-generation retry loop already uses) — reassigned, never
        # accumulated, so it always holds only the LAST failed candidate.
        # previous_code below stays pinned to the current TestAsset the
        # whole time (untouched by this) — that's the initial baseline;
        # repair is the separate "fix this specific broken draft" turn.
        repair: tuple[str, list[str]] | None = None
        while True:
            state = await asyncio.to_thread(
                _load_heal_loop_state_sync, ctx.test_result_pk, ctx.scenario.id, input.triggered_manually
            )
            if state.status not in HEALABLE_STATUSES or state.heal_attempt_count >= ctx.attempt_cap:
                break
            if _is_infra_failure(state.status, state.error_message):
                # Already resolved by the step-2 pre-check above; landing
                # here again is unexpected but safe to stop on rather than
                # spend an attempt against an environment problem.
                break

            pre_attempt_signature = _normalize_failure_signature(state.error_message)
            screenshot_png = await asyncio.to_thread(_fetch_latest_screenshot_sync, ctx.test_result_pk)

            # Targeted live inspection — deterministic primary trigger
            # (_is_locator_failure), bounded AI-requested fallback, gated by
            # the operational kill switch. Never a full crawl: one page,
            # the most specific one known for this scenario (its
            # journey's own last known page) falling back to the bare
            # application URL only when no known page exists, reusing this
            # TestRun's own auth session — never a fresh login.
            live_inspection_result = None
            locator_failure_matched = _is_locator_failure(state.status, state.error_message)
            if _live_inspection_enabled() and (
                locator_failure_matched or ai_requested_live_inspection
            ):
                target_url = ctx.known_pages[-1]["url"] if ctx.known_pages else ctx.application.url
                logger.info(
                    "HealTestActivity: test_result_id=%s triggering live inspection "
                    "(reason=%s)",
                    input.test_result_id,
                    "locator_failure_classifier" if locator_failure_matched else "ai_requested",
                )
                live_inspection_result = await run_live_inspection(
                    project_dir=project_dir, target_url=target_url
                )

            try:
                code_result = await HostedAIProvider().generate_playwright(
                    ctx.scenario,
                    ctx.known_pages,
                    ctx.known_locators,
                    requires_auth=state.test_asset.requires_auth,
                    field_input_types=ctx.field_input_types,
                    repair=repair,
                    previous_code=state.test_asset.code,
                    failure_error_message=state.error_message,
                    failure_stack_trace=state.stack_trace,
                    failure_console_output=state.console_output,
                    target_url=ctx.application.url,
                    failure_screenshot_png=screenshot_png,
                    live_inspection_locators=(
                        live_inspection_result.locator_candidates if live_inspection_result else None
                    ),
                    live_inspection_aria_snapshot=(
                        live_inspection_result.aria_snapshot if live_inspection_result else None
                    ),
                    application_context=ctx.application.application_context,
                )
            except Exception:
                logger.exception(
                    "HealTestActivity: test_result_id=%s AI generation call failed, stopping "
                    "heal loop",
                    input.test_result_id,
                )
                break

            ai_requested_live_inspection = code_result.requests_live_inspection

            tsc_errors = await typecheck_playwright_code(code_result.code)
            if tsc_errors:
                # An attempt is "an AI generation call was made" — already
                # counted here regardless of what typecheck does with it.
                # The candidate itself is NOT promoted to the current
                # TestAsset (only a typecheck-passing one is, below) — but
                # it and its exact diagnostics carry forward as `repair` so
                # the next attempt sees precisely what it wrote and why it
                # broke, instead of blindly retrying from the same original
                # baseline with only a summarized error string.
                await asyncio.to_thread(
                    _record_typecheck_failure_sync, ctx.test_result_pk, tsc_errors, input.triggered_manually
                )
                repair = (code_result.code, tsc_errors)
                continue

            # Typecheck passed — this candidate becomes the new baseline.
            # Clear any in-flight repair turn: a subsequent failure (if any)
            # will be a real runtime failure against this new current
            # TestAsset, not another compile-fix retry of a discarded draft.
            repair = None
            await asyncio.to_thread(
                _record_heal_supersede_sync,
                ctx.test_result_pk,
                state.test_asset.id,
                code_result.code,
                input.triggered_manually,
            )

            spec_file = project_dir / ctx.spec_path
            await asyncio.to_thread(spec_file.write_text, code_result.code, "utf-8")
            outcome = await _run_playwright_with_infra_retry(
                project_dir, ctx.spec_path, env, PLAYWRIGHT_RUN_TIMEOUT_SECONDS, input.test_result_id
            )
            await asyncio.to_thread(_persist_test_result_sync, input.test_run_id, exec_context, outcome)

            if outcome["status"] == "passed":
                logger.info("HealTestActivity: test_result_id=%s healed successfully", input.test_result_id)
                break
            if _is_infra_failure(outcome["status"], outcome.get("error_message")):
                logger.info(
                    "HealTestActivity: test_result_id=%s rerun still an infra failure after one "
                    "bounded retry, stopping",
                    input.test_result_id,
                )
                break

            new_signature = _normalize_failure_signature(outcome.get("error_message"))
            if new_signature == pre_attempt_signature:
                logger.info(
                    "HealTestActivity: test_result_id=%s no-progress guard triggered, stopping "
                    "heal loop",
                    input.test_result_id,
                )
                break
            # Otherwise loop again — the top of the loop re-reads the
            # now-current TestAsset and this attempt's fresh failure
            # evidence as the next attempt's input.
    finally:
        await asyncio.to_thread(_release_heal_claim_sync, input.test_result_id)


# Below the workflow's 5-minute start_to_close for this activity, so a stuck
# `allure generate` is always killed here first, never orphaned.
ALLURE_GENERATE_TIMEOUT_SECONDS = 180
# ponytail: a run whose single-file report exceeds this gets no report —
# the Vantage report plugin inlines attachments (screenshots, plus traces
# within its own per-file caps) as base64. A fuller version would
# upload the multi-file report directory instead of one HTML file.
ALLURE_REPORT_MAX_BYTES = 100 * 1024 * 1024


def allure_report_key(test_run_id: str) -> str:
    return f"test-runs/{test_run_id}/allure-report.html"


# Only these generated the report's inventory: a TestResult that actually
# ran. `pending` never finished, `blocked` never started.
_EXECUTED_STATUSES = ("passed", "failed", "timed_out", "errored")
ALLURE_FINAL_RESULTS_DIR = "allure-results-final"


@dataclass
class _ReportInventoryItem:
    external_id: str
    status: str
    completed_at: datetime | None
    started_at: datetime | None
    error_message: str | None
    stack_trace: str | None
    name: str
    spec_path: str | None


def _load_report_inventory_sync(test_run_id: str) -> tuple[list[_ReportInventoryItem], str]:
    """Every TestResult of this run that ran, plus the report title. Spec
    paths are recomputed the same way ExecuteTestActivity does, keyed by
    Scenario rather than TestAsset — a healed test's current TestAsset is a
    newer row than the one the TestResult was created for."""
    with Session(engine) as session:
        test_run = session.exec(
            select(TestRun).where(TestRun.external_id == uuid.UUID(test_run_id))
        ).one()
        application = session.exec(
            select(Application).where(Application.id == test_run.application_id)
        ).one()
        results = session.exec(
            select(TestResult).where(
                TestResult.test_run_id == test_run.id,
                TestResult.status.in_(_EXECUTED_STATUSES),  # type: ignore[attr-defined]
            )
        ).all()
        scenario_ids = {r.scenario_id for r in results}
        scenarios = (
            {
                s.id: s
                for s in session.exec(
                    select(Scenario).where(Scenario.id.in_(scenario_ids))  # type: ignore[attr-defined]
                ).all()
            }
            if scenario_ids
            else {}
        )
        inputs = _load_assembly_inputs_sync(session, application)
        spec_path_by_asset_id = compute_spec_paths(
            test_suites=inputs.test_suites,
            journeys_by_id=inputs.journeys_by_id,
            assets_by_suite=inputs.assets_by_suite,
            scenario_name_by_asset_id=inputs.scenario_name_by_asset_id,
        )
        spec_path_by_scenario_id = {
            asset.scenario_id: spec_path_by_asset_id[asset.id]
            for assets in inputs.assets_by_suite.values()
            for asset in assets
            if asset.id in spec_path_by_asset_id
        }
        items = [
            _ReportInventoryItem(
                external_id=str(r.external_id),
                status=r.status,
                completed_at=r.completed_at,
                started_at=r.started_at,
                error_message=r.error_message,
                stack_trace=r.stack_trace,
                name=scenarios[r.scenario_id].name if r.scenario_id in scenarios else "Test",
                spec_path=spec_path_by_scenario_id.get(r.scenario_id),
            )
            for r in results
        ]
        return items, f"{application.name} · Run #{test_run.run_number}"


def _read_marker(folder: Path) -> dict | None:
    try:
        marker = json.loads((folder / ALLURE_FINAL_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return marker if isinstance(marker, dict) else None


def _valid_final_attempt(folder: Path, item: _ReportInventoryItem) -> Path | None:
    """The attempt folder holding `item`'s persisted outcome, or None if it
    can't be trusted. Only the attempt the marker names is ever considered
    — earlier (pre-heal, auth-refresh, infra-retry) and unpersisted attempts
    sit beside it and are never read."""
    marker = _read_marker(folder)
    if (
        marker is None
        or marker.get("status") != item.status
        or marker.get("completed_at") != _timestamp_key(item.completed_at)
        or not isinstance(marker.get("attempt"), str)
        or not re.fullmatch(r"[0-9a-f]{32}", marker["attempt"])
    ):
        return None
    attempt_dir = folder / marker["attempt"]
    statuses = []
    for result_file in attempt_dir.glob("*-result.json"):
        try:
            statuses.append(json.loads(result_file.read_text(encoding="utf-8")).get("status"))
        except (OSError, ValueError):
            return None
    if not statuses:
        return None
    # Allure's status must tell the same story Vantage persisted.
    all_passed = all(s == "passed" for s in statuses)
    if (item.status == "passed") != all_passed:
        return None
    return attempt_dir


def _synthesized_result(item: _ReportInventoryItem) -> dict:
    """Stands in for a test that ran but left no usable Allure result (killed
    at the process timeout, a stale marker, a crash before the reporter
    wrote). Its status follows Vantage's own: Broken unless Vantage saved it
    as passed — the report must never contradict the run."""

    def millis(value: datetime | None) -> int | None:
        return None if value is None else int(_as_utc(value).timestamp() * 1000)

    spec = (item.spec_path or "").removeprefix("tests/")
    passed = item.status == "passed"
    return {
        "uuid": str(uuid.uuid4()),
        "historyId": f"vantage-{item.external_id}",
        "testCaseId": f"vantage-{item.external_id}",
        "name": item.name,
        "fullName": f"{spec} › {item.name}" if spec else item.name,
        "status": "passed" if passed else "broken",
        "statusDetails": {}
        if passed
        else {
            "message": item.error_message or "The test produced no detailed results.",
            "trace": item.stack_trace or "",
        },
        "stage": "finished",
        "start": millis(item.started_at),
        "stop": millis(item.completed_at),
        "labels": [{"name": "framework", "value": "playwright"}],
        "parameters": [],
        "links": [],
        "steps": [],
        "attachments": [],
    }


def _collect_final_allure_results(
    project_dir: Path, inventory: list[_ReportInventoryItem]
) -> tuple[Path, int, int]:
    """Builds `allure-results-final/` with exactly one entry per executed
    TestResult: the files of its persisted attempt, or a synthesized result
    when that attempt can't be trusted. Returns (dir, used, synthesized).

    Tests that never ran (blocked, still pending, or errored by Prepare
    before any Playwright process started) have no `allure-results/<id>/`
    folder and are left out — nothing is invented for them."""
    results_root = project_dir / ALLURE_RESULTS_DIR
    final_dir = project_dir / ALLURE_FINAL_RESULTS_DIR
    shutil.rmtree(final_dir, ignore_errors=True)
    final_dir.mkdir(parents=True)
    used = synthesized = 0
    for item in inventory:
        folder = results_root / item.external_id
        if not folder.is_dir():
            continue
        attempt_dir = _valid_final_attempt(folder, item)
        if attempt_dir is not None:
            for file in attempt_dir.iterdir():
                if file.is_file():
                    shutil.copy2(file, final_dir / file.name)
            used += 1
        else:
            synthetic = _synthesized_result(item)
            (final_dir / f"{synthetic['uuid']}-result.json").write_text(
                json.dumps(synthetic), encoding="utf-8"
            )
            synthesized += 1
    return final_dir, used, synthesized


@activity.defn(name="GenerateAllureReportActivity")
async def generate_allure_report_activity(input: GenerateAllureReportActivityInput) -> str | None:
    return await asyncio.to_thread(_generate_allure_report_sync, input)


def _generate_allure_report_sync(input: GenerateAllureReportActivityInput) -> str | None:
    """Builds the Vantage report from the Allure results of each executed
    test's persisted attempt (see `_collect_final_allure_results`), uploads
    it as one HTML file, and records its key on the TestRun. Best-effort:
    returns None and never raises — a missing or broken report must never
    block Finalize.

    ponytail: assumes one execution worker host per run (k8s runs
    `replicas: 1`) — results are written to, and the report built from, that
    host's local project dir. With several replicas a run's tests could
    spread across hosts and this would see only part of them, or none."""
    try:
        project_dir = project_dir_for(uuid.UUID(input.test_run_id))
        results_dir = project_dir / ALLURE_RESULTS_DIR
        if not results_dir.is_dir() or not any(results_dir.iterdir()):
            logger.info(
                "GenerateAllureReportActivity: test_run_id=%s has no Allure results, skipping",
                input.test_run_id,
            )
            return None

        inventory, title = _load_report_inventory_sync(input.test_run_id)
        final_dir, used, synthesized = _collect_final_allure_results(project_dir, inventory)
        logger.info(
            "GenerateAllureReportActivity: test_run_id=%s report covers %d executed tests "
            "(%d from Allure results, %d without usable results)",
            input.test_run_id,
            used + synthesized,
            used,
            synthesized,
        )
        if used + synthesized == 0:
            return None

        subprocess.run(
            [_resolve_bin("npx"), "allure", "generate", final_dir.name],
            cwd=project_dir,
            check=True,
            capture_output=True,
            timeout=ALLURE_GENERATE_TIMEOUT_SECONDS,
            env={**os.environ, REPORT_TITLE_ENV: title},
        )
        report_path = project_dir / "allure-report" / "index.html"
        if not report_path.is_file():
            logger.warning(
                "GenerateAllureReportActivity: test_run_id=%s produced no %s",
                input.test_run_id,
                report_path,
            )
            return None
        size = report_path.stat().st_size
        if size > ALLURE_REPORT_MAX_BYTES:
            logger.warning(
                "GenerateAllureReportActivity: test_run_id=%s report is %d bytes, "
                "over the %d limit; not uploading",
                input.test_run_id,
                size,
                ALLURE_REPORT_MAX_BYTES,
            )
            return None

        key = ObjectStore().put_at_key(
            allure_report_key(input.test_run_id), report_path.read_bytes(), "text/html"
        )
        with Session(engine) as session:
            test_run = session.exec(
                select(TestRun).where(TestRun.external_id == uuid.UUID(input.test_run_id))
            ).one()
            test_run.allure_report_key = key
            session.add(test_run)
            session.commit()
        logger.info(
            "GenerateAllureReportActivity: test_run_id=%s uploaded report (%d bytes)",
            input.test_run_id,
            size,
        )
        return key
    except Exception:
        logger.exception(
            "GenerateAllureReportActivity: test_run_id=%s failed; continuing without a report",
            input.test_run_id,
        )
        return None


# --- Run-completed email (SendTestRunReportEmailActivity) -----------------


def _resolve_report_recipient(
    session: Session, test_run: TestRun, application: Application
) -> tuple[PlatformUser | None, str]:
    """(recipient, reason). A scheduled run — "Run now" included, which goes
    through the same ScheduledExecutionWorkflow — always goes to the
    schedule's creator, never to whoever clicked; a manual run goes to the
    user who clicked Run. No owner is ever inferred from a stored *name*."""
    if test_run.schedule_id is not None:
        schedule = session.get(Schedule, test_run.schedule_id)
        user_id = schedule.created_by_user_id if schedule is not None else None
        if user_id is None:
            # Seeded default schedules, schedules from before owners were
            # recorded, and schedules whose creator was removed (SET NULL).
            return None, "the schedule has no owner on record"
    else:
        user_id = test_run.triggered_by_user_id
        if user_id is None:
            # Runs from before starters were recorded, or the starter was
            # removed (SET NULL).
            return None, "the run has no starter on record"
    user = session.get(PlatformUser, user_id)
    if user is None:
        return None, "the recipient's account no longer exists"
    if user.organization_id != application.organization_id:
        return None, "the recipient isn't in the application's organization"
    return user, "ok"


def _test_failure_message(error_message: str | None) -> str | None:
    """The email shows final statuses only, never self-healing detail.

    ponytail: a heal attempt whose generated fix fails typecheck overwrites
    `TestResult.error_message` with that typecheck error, losing the test's
    own failure message — so the email drops it (the row still shows the test,
    and the report link has the run's own failure details). A fuller fix would
    store heal errors in their own field and leave `error_message` as the
    test's last real failure.
    """
    if error_message and error_message.startswith(HEAL_TYPECHECK_ERROR_PREFIX):
        return None
    return error_message


def _load_run_email_sync(
    test_run_id: str,
) -> tuple[TestRun, RunEmail, PlatformUser | None, str]:
    with Session(engine) as session:
        test_run = session.exec(
            select(TestRun).where(TestRun.external_id == uuid.UUID(test_run_id))
        ).one()
        application = session.exec(
            select(Application).where(Application.id == test_run.application_id)
        ).one()
        recipient, reason = _resolve_report_recipient(session, test_run, application)
        rows = session.exec(
            select(TestResult, Scenario, Journey)
            .join(Scenario, Scenario.id == TestResult.scenario_id)  # type: ignore[arg-type]
            .join(Journey, Journey.id == Scenario.journey_id, isouter=True)  # type: ignore[arg-type]
            .where(
                TestResult.test_run_id == test_run.id,
                TestResult.status.in_(("failed", "timed_out", "errored")),  # type: ignore[attr-defined]
            )
        ).all()
        email = RunEmail(
            application_id=str(application.external_id),
            test_run_id=str(test_run.external_id),
            app_name=application.name,
            run_number=test_run.run_number,
            counts=RunCounts(
                total=test_run.total_count,
                passed=test_run.passed_count,
                failed=test_run.failed_count,
                timed_out=test_run.timed_out_count,
                errored=test_run.errored_count,
                blocked=test_run.blocked_count,
            ),
            started_at=test_run.started_at,
            completed_at=test_run.completed_at,
            target_url=test_run.target_base_url_snapshot,
            triggered_by_name=test_run.triggered_by_name,
            scheduled=test_run.schedule_id is not None,
            report_available=test_run.allure_report_key is not None,
            base_url=FRONTEND_BASE_URL,
            failed_tests=[
                FailedTest(
                    name=scenario.name,
                    journey=journey.name if journey is not None else None,
                    status=result.status,
                    error_message=_test_failure_message(result.error_message),
                    duration_ms=result.duration_ms,
                )
                for result, scenario, journey in rows
            ],
        )
        session.expunge(test_run)
        if recipient is not None:
            session.expunge(recipient)
        return test_run, email, recipient, reason


def _claim_report_email_sync(test_run_pk: uuid.UUID) -> bool:
    """One conditional UPDATE, so two concurrent or retried activities can
    never both send: only the call that flips `report_email_claimed_at` from
    NULL proceeds."""
    with Session(engine) as session:
        result = session.execute(
            update(TestRun)
            .where(
                TestRun.id == test_run_pk,  # type: ignore[arg-type]
                TestRun.report_email_claimed_at.is_(None),  # type: ignore[union-attr]
                TestRun.report_emailed_at.is_(None),  # type: ignore[union-attr]
            )
            .values(report_email_claimed_at=datetime.now(UTC))
        )
        session.commit()
        return (result.rowcount or 0) > 0  # type: ignore[attr-defined]


def _set_report_email_state_sync(test_run_pk: uuid.UUID, *, sent: bool) -> None:
    values = (
        {"report_emailed_at": datetime.now(UTC)} if sent else {"report_email_claimed_at": None}
    )
    with Session(engine) as session:
        session.execute(
            update(TestRun).where(TestRun.id == test_run_pk).values(**values)  # type: ignore[arg-type]
        )
        session.commit()


@activity.defn(name="SendTestRunReportEmailActivity")
async def send_test_run_report_email_activity(
    input: SendTestRunReportEmailActivityInput,
) -> None:
    await asyncio.to_thread(_send_test_run_report_email_sync, input)


def _send_test_run_report_email_sync(input: SendTestRunReportEmailActivityInput) -> None:
    """Emails the run's owner (see `_resolve_report_recipient`) once the run
    has completed. Skips, with the reason logged, when the run isn't
    completed, the email was already sent or claimed, there's no recipient,
    or SMTP isn't configured.

    Delivery is at most once, not exactly once: claim
    (`_claim_report_email_sync`) → SMTP send → `report_emailed_at`. An SMTP
    error releases the claim and re-raises, so Temporal's retry can send.

    ponytail: two windows remain, accepted for this stage instead of an
    outbox/relay with message ids — (1) the worker dies after claiming but
    before the SMTP server accepts: the claim is never released, so the
    email is skipped (lost) rather than risking a duplicate; (2) the server
    accepts the message but the connection fails before its reply: that
    surfaces as an SMTP error, the claim is released, and a retry can send a
    duplicate. A crash after acceptance but before `report_emailed_at`
    commits sends no duplicate (the claim stays) but leaves the run marked
    claimed, not sent."""
    test_run, email, recipient, reason = _load_run_email_sync(input.test_run_id)
    if test_run.status != "completed":
        logger.warning(
            "run-completed email: test_run_id=%s is %r, not completed; skipping",
            input.test_run_id,
            test_run.status,
        )
        return
    if test_run.report_emailed_at is not None or test_run.report_email_claimed_at is not None:
        logger.info(
            "run-completed email: test_run_id=%s already sent or in progress; skipping",
            input.test_run_id,
        )
        return
    if recipient is None:
        logger.info(
            "run-completed email: test_run_id=%s has no recipient (%s); skipping",
            input.test_run_id,
            reason,
        )
        return
    subject, text, html = build_email(email)
    if not smtp_configured():
        # Same dev fallback as invites and password resets: log, don't send.
        logger.info(
            "run-completed email (SMTP not configured) to %s: %s — %s",
            recipient.email,
            subject,
            run_url(email),
        )
        return
    if not _claim_report_email_sync(test_run.id):
        logger.info(
            "run-completed email: test_run_id=%s claimed by another attempt; skipping",
            input.test_run_id,
        )
        return
    try:
        send_email(recipient.email, subject, text, html)
    except Exception:
        _set_report_email_state_sync(test_run.id, sent=False)
        raise
    _set_report_email_state_sync(test_run.id, sent=True)
    logger.info(
        "run-completed email: test_run_id=%s sent to %s", input.test_run_id, recipient.email
    )


@activity.defn(name="FinalizeTestRunActivity")
async def finalize_test_run_activity(input: FinalizeTestRunActivityInput) -> None:
    await asyncio.to_thread(_finalize_test_run_sync, input)


def _finalize_test_run_sync(input: FinalizeTestRunActivityInput) -> None:
    with Session(engine) as session:
        test_run = session.exec(
            select(TestRun).where(TestRun.external_id == uuid.UUID(input.test_run_id))
        ).one()
        if test_run.status == "completed":
            logger.info(
                "FinalizeTestRunActivity: test_run_id=%s already finalized, skipping",
                input.test_run_id,
            )
            return  # already finalized by a prior Temporal attempt — idempotent no-op

        results = session.exec(
            select(TestResult).where(TestResult.test_run_id == test_run.id)
        ).all()
        for result in results:
            if result.status == "pending":
                # ponytail: an ExecuteTestActivity that exhausted its own
                # RetryPolicy leaves its TestResult stuck at "pending" —
                # FinalizeTestRunActivity still always runs (the workflow's
                # asyncio.gather uses return_exceptions=True), so without this,
                # the result would silently vanish from every count below
                # rather than surface as a real outcome. Folded into
                # "errored" rather than a distinct status, since Temporal's
                # own retry-exhaustion detail isn't threaded back to the
                # TestResult row today — a fuller version would give this
                # its own status (e.g. "infra_failed") instead of overloading
                # "errored".
                result.status = "errored"
                result.error_message = (
                    result.error_message or "test did not complete (activity failed after retries)"
                )
                result.completed_at = datetime.now(UTC)
                session.add(result)

        counts = _tally_counts(results)
        test_run.total_count = len(results)
        test_run.passed_count = counts["passed"]
        test_run.failed_count = counts["failed"]
        test_run.timed_out_count = counts["timed_out"]
        test_run.errored_count = counts["errored"]
        test_run.blocked_count = counts["blocked"]
        test_run.status = "completed"
        test_run.completed_at = datetime.now(UTC)
        session.add(test_run)
        session.commit()

        external_id = test_run.external_id
        logger.info(
            "FinalizeTestRunActivity: test_run_id=%s finished passed=%d failed=%d "
            "timed_out=%d errored=%d blocked=%d",
            external_id,
            counts["passed"],
            counts["failed"],
            counts["timed_out"],
            counts["errored"],
            counts["blocked"],
        )

    cleanup_project_dir(external_id)


@activity.defn(name="ForceCompleteTestRunActivity")
async def force_complete_test_run_activity(input: ForceCompleteTestRunActivityInput) -> None:
    await asyncio.to_thread(_force_complete_test_run_sync, input)


def _force_complete_test_run_sync(input: ForceCompleteTestRunActivityInput) -> None:
    # Last-resort safety net, called only when FinalizeTestRunActivity itself
    # exhausted its retries — must never itself raise past the workflow, or
    # TestRun.status is stuck at "running" forever (no reconciliation job
    # exists to catch this later). Try the real finalize logic first (proper
    # counts), then fall back to a bare status flip if even that fails.
    try:
        _finalize_test_run_sync(FinalizeTestRunActivityInput(test_run_id=input.test_run_id))
        return
    except Exception:
        logger.exception(
            "ForceCompleteTestRunActivity: full finalize failed for test_run_id=%s, "
            "falling back to a bare status flip",
            input.test_run_id,
        )

    try:
        with Session(engine) as session:
            test_run = session.exec(
                select(TestRun).where(TestRun.external_id == uuid.UUID(input.test_run_id))
            ).one_or_none()
            if test_run is not None and test_run.status != "completed":
                test_run.status = "completed"
                test_run.completed_at = datetime.now(UTC)
                session.add(test_run)
                session.commit()
    except Exception:
        logger.exception(
            "ForceCompleteTestRunActivity: bare status flip also failed for test_run_id=%s",
            input.test_run_id,
        )


@activity.defn(name="ReconcileStaleTestRunsActivity")
def reconcile_stale_test_runs_activity() -> list[str]:
    return _reconcile_stale_test_runs_sync()


def _reconcile_stale_test_runs_sync() -> list[str]:
    """Periodic catch-all for the gap `_force_complete_test_run_sync`'s own
    docstring names: nothing re-scans a `TestRun` that never reached either
    `FinalizeTestRunActivity` or `ForceCompleteTestRunActivity` at all — a
    worker killed before either ran, or a Temporal cluster outage spanning
    the whole run. Finds every `TestRun` still `"running"` past
    `TEST_RUN_STALE_AFTER` and reuses `_force_complete_test_run_sync`
    unchanged (full finalize first, bare status flip as its own fallback,
    never raises) rather than a second implementation of "how to close out a
    TestRun."
    """
    cutoff = datetime.now(UTC) - TEST_RUN_STALE_AFTER
    with Session(engine) as session:
        stale_ids = [
            str(run.external_id)
            for run in session.exec(
                select(TestRun).where(
                    TestRun.status == "running",
                    TestRun.started_at.is_not(None),
                    TestRun.started_at <= cutoff,  # type: ignore[operator]
                )
            ).all()
        ]

    for test_run_id in stale_ids:
        _force_complete_test_run_sync(ForceCompleteTestRunActivityInput(test_run_id=test_run_id))

    if stale_ids:
        logger.info(
            "ReconcileStaleTestRunsActivity: reconciled %d stale test run(s): %s",
            len(stale_ids),
            stale_ids,
        )
    return stale_ids
