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
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from domain import (
    Application,
    Journey,
    Scenario,
    TestAsset,
    TestResult,
    TestResultArtifact,
    TestRun,
    TestSuite,
)
from object_store import ObjectStore
from secrets_client.vault_client import SecretRef, VaultSecretsClient
from sqlmodel import Session, select
from temporalio import activity
from test_suite_assembler import (
    assemble_test_suite_project_to_dir,
    compute_spec_paths,
    find_login_page_evidence,
)
from workflows import (
    ExecutableTest,
    ExecuteTestActivityInput,
    FinalizeTestRunActivityInput,
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
    await _ensure_project_dir(uuid.UUID(input.test_run_id), uuid.UUID(input.application_id))
    env = await asyncio.to_thread(_build_subprocess_env, context.application)
    project_dir = project_dir_for(uuid.UUID(input.test_run_id))
    outcome = await _run_playwright_test(
        project_dir,
        context.spec_path,
        env,
        PLAYWRIGHT_RUN_TIMEOUT_SECONDS,
        input.test_result_id,
    )
    await asyncio.to_thread(_persist_test_result_sync, input, context, outcome)
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
    always depends on the `setup` project (`auth.setup.ts`), so a failed
    setup makes the target spec show up with `results: []` and a top-level
    `status: "skipped"` — never its own `results[-1]`, which is why this
    parser checks the *target file's own suite* specifically rather than
    just returning the first suite with any results (that would silently
    report the setup project's own outcome instead of the test's own).

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
                    error_obj = result.get("error") or next(
                        iter(result.get("errors") or []), None
                    )
                    error_message = None
                    stack_trace = None
                    if isinstance(error_obj, dict):
                        error_message = error_obj.get("message")
                        stack_trace = error_obj.get("stack")
                    elif error_obj:
                        error_message = str(error_obj)
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


def _persist_test_result_sync(
    input: ExecuteTestActivityInput, context: _ExecutionContext, outcome: dict
) -> None:
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

        for path in outcome.get("artifact_paths", []):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            artifact_type = "trace" if path.suffix == ".zip" else "screenshot"
            content_type = "application/zip" if artifact_type == "trace" else "image/png"
            key = ObjectStore().put_test_artifact(
                data, uuid.UUID(input.test_run_id), content_type=content_type
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
