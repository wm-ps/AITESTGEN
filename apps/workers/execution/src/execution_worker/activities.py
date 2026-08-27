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
    Scenario,
    TestAsset,
    TestResult,
    TestResultArtifact,
    TestRun,
    TestSuite,
)
from generation_worker.activities import (
    resolve_known_application_model_sync,
    supersede_test_asset,
)
from generation_worker.typecheck import typecheck_playwright_code
from object_store import ObjectStore
from secrets_client.vault_client import SecretRef, VaultSecretsClient
from sqlalchemy import or_, update
from sqlmodel import Session, select
from temporalio import activity
from test_suite_assembler import (
    assemble_test_suite_project_to_dir,
    compute_spec_paths,
    find_login_page_evidence,
)
from workflows import (
    HEAL_CLAIM_STALE_AFTER,
    HEALABLE_STATUSES,
    ExecutableTest,
    ExecuteTestActivityInput,
    FinalizeTestRunActivityInput,
    HealTestActivityInput,
    PrepareTestRunActivityInput,
    PrepareTestRunActivityResult,
)

from execution_worker.db import engine
from execution_worker.project_cache import cleanup_project_dir, project_dir_for

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


def _load_assembly_inputs_sync(session: Session, application: Application) -> _AssemblyInputs:
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

    test_assets = (
        session.exec(
            select(TestAsset).where(
                TestAsset.test_suite_id.in_(suite_ids),  # type: ignore[attr-defined]
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).all()
        if suite_ids
        else []
    )
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
        inputs = _load_assembly_inputs_sync(session, application)
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

        test_run = TestRun(
            application_id=application.id,
            status="running",
            environment_snapshot=application.environment,
            target_base_url_snapshot=application.url,
            triggered_by_name=input.triggered_by_name,
            started_at=datetime.now(UTC),
        )
        session.add(test_run)
        session.commit()
        session.refresh(test_run)

        inputs = _load_assembly_inputs_sync(session, application)
        test_assets = inputs.test_assets
        assets_by_suite = inputs.assets_by_suite
        scenario_name_by_asset_id = inputs.scenario_name_by_asset_id

        # Per-test-result rows first — every TestAsset gets a row before any
        # project assembly/install so a slow npm install never delays the
        # "why is my count already showing" moment for the poller. Every
        # TestAsset is executable unconditionally (see this function's own
        # ponytail note above).
        executable: list[ExecutableTest] = []
        test_results_by_asset_id: dict[uuid.UUID, TestResult] = {}
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
        try:
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
            for asset in pending_assets:
                test_result = test_results_by_asset_id[asset.id]
                test_result.status = "errored"
                test_result.error_message = f"failed to prepare the test project: {exc}"
                test_result.completed_at = datetime.now(UTC)
                session.add(test_result)
            test_run.errored_count = len(pending_assets)
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
            [_resolve_bin("npx"), "playwright", "test", "--project=setup"],
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
        test_suite = session.exec(
            select(TestSuite).where(TestSuite.id == test_asset.test_suite_id)
        ).one()
        journey = session.exec(select(Journey).where(Journey.id == test_suite.journey_id)).one()
        scenario = session.exec(select(Scenario).where(Scenario.id == test_asset.scenario_id)).one()

        # Recomputed fresh from the same DB-sourced inputs Prepare used —
        # never persisted, never relies on in-memory state surviving across
        # separate Activity invocations (see compute_spec_paths' docstring).
        spec_path_by_asset_id = compute_spec_paths(
            test_suites=[test_suite],
            journeys_by_id={journey.id: journey},
            assets_by_suite={test_suite.id: [test_asset]},
            scenario_name_by_asset_id={test_asset.id: scenario.name},
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
    if application.auth_method == "sso_session_reuse":
        env["AITESTGEN_STORAGE_STATE"] = credential.decode()
    else:
        creds = json.loads(credential.decode())
        env["AITESTGEN_LOGIN_USERNAME"] = creds["username"]
        env["AITESTGEN_LOGIN_PASSWORD"] = creds["password"]
    return env


async def _run_playwright_test(
    project_dir: Path,
    spec_path: str,
    env: dict,
    timeout_seconds: float,
    test_result_id: str,
) -> dict:
    """Runs `npx playwright test <spec_path> --reporter=json` in
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
    proc = await asyncio.create_subprocess_exec(
        _resolve_bin("npx"),
        "playwright",
        "test",
        spec_path,
        "--reporter=json",
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
        }

    result = _parse_playwright_report(stdout, stderr, spec_path)
    result["artifact_paths"] = (
        _find_artifacts(project_dir / output_dir) if result["status"] != "passed" else []
    )
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

        for path in outcome.get("artifact_paths", []):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            artifact_type = "trace" if path.suffix == ".zip" else "screenshot"
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


# --- Self-healing (HealTestActivity) --------------------------------------

# A same-code, no-AI-call rerun when the *current* failure is infra, not a
# code defect — bounds a persistently-down target application to one extra
# rerun per check rather than spinning this activity forever. Never
# increments TestResult.heal_attempt_count.
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
    spec_path: str
    max_heal_attempts: int


def _load_heal_context_sync(input: HealTestActivityInput) -> _HealContext | None:
    with Session(engine) as session:
        test_result = session.exec(
            select(TestResult).where(TestResult.external_id == uuid.UUID(input.test_result_id))
        ).one()
        discovery_settings = session.exec(select(DiscoverySettings)).one()
        if (
            test_result.status not in HEALABLE_STATUSES
            or test_result.heal_attempt_count >= discovery_settings.max_heal_attempts
        ):
            # Not eligible — already passed/blocked, or the shared budget is
            # already spent. Safe no-op: this is what lets HealTestActivity
            # be called unconditionally after every ExecuteTestActivity with
            # no branching in workflow code.
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
        known_pages, known_locators, _, _ = resolve_known_application_model_sync(session, journey.id)
        spec_path_by_asset_id = compute_spec_paths(
            test_suites=[test_suite],
            journeys_by_id={journey.id: journey},
            assets_by_suite={test_suite.id: [test_asset]},
            scenario_name_by_asset_id={test_asset.id: scenario.name},
        )
        return _HealContext(
            test_result_pk=test_result.id,
            application=application,
            scenario=scenario,
            known_pages=known_pages,
            known_locators=known_locators,
            spec_path=spec_path_by_asset_id[test_asset.id],
            max_heal_attempts=discovery_settings.max_heal_attempts,
        )


@dataclass
class _HealLoopState:
    status: str
    error_message: str | None
    stack_trace: str | None
    console_output: str | None
    heal_attempt_count: int
    test_asset: TestAsset


def _load_heal_loop_state_sync(test_result_pk: uuid.UUID, scenario_id: uuid.UUID) -> _HealLoopState:
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
            heal_attempt_count=test_result.heal_attempt_count,
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


def _record_typecheck_failure_sync(test_result_pk: uuid.UUID, tsc_errors: list[str]) -> None:
    with Session(engine) as session:
        test_result = session.exec(select(TestResult).where(TestResult.id == test_result_pk)).one()
        test_result.heal_attempt_count += 1
        test_result.error_message = "generated fix failed typecheck: " + "; ".join(tsc_errors[:5])
        session.add(test_result)
        session.commit()


def _record_heal_supersede_sync(test_result_pk: uuid.UUID, prior_test_asset_id: uuid.UUID, code: str) -> None:
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
        test_result.heal_attempt_count += 1
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

    The heal loop, one iteration:
      real execution -> failure evidence -> AI diagnosis -> targeted edit ->
      typecheck -> update current TestAsset -> real re-execution -> new
      failure evidence -> (pass | no-progress stop | loop again), bounded by
      the configurable DiscoverySettings.max_heal_attempts.
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
        # leaving heal_attempt_count untouched for a later trigger once the
        # environment issue clears.
        initial_state = await asyncio.to_thread(
            _load_heal_loop_state_sync, ctx.test_result_pk, ctx.scenario.id
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
        while True:
            state = await asyncio.to_thread(
                _load_heal_loop_state_sync, ctx.test_result_pk, ctx.scenario.id
            )
            if state.status not in HEALABLE_STATUSES or state.heal_attempt_count >= ctx.max_heal_attempts:
                break
            if _is_infra_failure(state.status, state.error_message):
                # Already resolved by the step-2 pre-check above; landing
                # here again is unexpected but safe to stop on rather than
                # spend an attempt against an environment problem.
                break

            pre_attempt_signature = _normalize_failure_signature(state.error_message)
            screenshot_png = await asyncio.to_thread(_fetch_latest_screenshot_sync, ctx.test_result_pk)

            try:
                code_result = await HostedAIProvider().generate_playwright(
                    ctx.scenario,
                    ctx.known_pages,
                    ctx.known_locators,
                    requires_auth=state.test_asset.requires_auth,
                    previous_code=state.test_asset.code,
                    failure_error_message=state.error_message,
                    failure_stack_trace=state.stack_trace,
                    failure_console_output=state.console_output,
                    target_url=ctx.application.url,
                    failure_screenshot_png=screenshot_png,
                )
            except Exception:
                logger.exception(
                    "HealTestActivity: test_result_id=%s AI generation call failed, stopping "
                    "heal loop",
                    input.test_result_id,
                )
                break

            tsc_errors = await typecheck_playwright_code(code_result.code)
            if tsc_errors:
                # An attempt is "an AI generation call was made" — already
                # counted here regardless of what typecheck does with it.
                await asyncio.to_thread(_record_typecheck_failure_sync, ctx.test_result_pk, tsc_errors)
                continue

            await asyncio.to_thread(
                _record_heal_supersede_sync, ctx.test_result_pk, state.test_asset.id, code_result.code
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
