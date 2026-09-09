"""PrepareSingleTestRunActivity / ReadTestResultStatusActivity — shared NLM
building blocks, used by `LiveExplorationTestWorkflow` to assemble+execute
one already-generated TestAsset and read its outcome back.

`[REMOVED]` `ReadLatestTestResultActivity` — the "reuse_scenario matched an
already-executed TestAsset, report its last result instead of re-running"
fast path, exclusive to the now-removed `AddTestCaseWorkflow` (which matched
against already-crawled Journeys/Scenarios). `LiveExplorationTestWorkflow`
always explores fresh, so this path never applied to it.

`PrepareSingleTestRunActivity` is `_prepare_test_run_sync`'s (`activities.py`)
single-`TestAsset` sibling — same project-assembly/install/auth-setup calls,
duplicated rather than shared (matching this codebase's own stated convention
for this exact kind of near-duplicate; see `resolve_known_application_model_sync`'s
docstring in `generation_worker/activities.py`), because a "Run All Tests"
`TestRun` and an "Add Test Case" `TestRun` build their project directory from
a different, differently-scoped set of rows.

`ExecuteTestActivity`/`FinalizeTestRunActivity` (this package's own
`activities.py`) are reused **unmodified** afterwards — both are already
scoped to one `test_run_id`/`test_result_id` pair, so a lone ad hoc test
needs no changes there.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from domain import Application, Journey, Scenario, TestAsset, TestResult, TestRun, TestSuite
from sqlalchemy import update
from sqlmodel import Session, select
from temporalio import activity
from test_suite_assembler import assemble_test_suite_project_to_dir, find_login_page_evidence
from workflows import (
    PrepareSingleTestRunActivityInput,
    PrepareSingleTestRunActivityResult,
    ReadTestResultStatusActivityInput,
    ReadTestResultStatusResult,
)

from execution_worker.activities import (
    _AssemblyInputs,
    _install_project,
    _run_auth_setup_once,
)
from execution_worker.db import engine
from execution_worker.project_cache import project_dir_for

logger = logging.getLogger(__name__)


def _load_single_assembly_inputs_sync(
    session: Session, application: Application, test_asset: TestAsset
) -> _AssemblyInputs:
    test_suite = session.get(TestSuite, test_asset.test_suite_id)
    journey = session.get(Journey, test_suite.journey_id) if test_suite else None
    scenario = session.get(Scenario, test_asset.scenario_id)
    assert test_suite is not None and journey is not None and scenario is not None

    login_evidence = (
        find_login_page_evidence(session, application)
        if application.auth_method == "standard_login"
        else None
    )
    return _AssemblyInputs(
        test_assets=[test_asset],
        test_suites=[test_suite],
        journeys_by_id={journey.id: journey},
        assets_by_suite={test_suite.id: [test_asset]},
        scenario_name_by_asset_id={test_asset.id: scenario.name},
        login_evidence=login_evidence,
    )


def _prepare_single_test_run_sync(
    input: PrepareSingleTestRunActivityInput,
) -> PrepareSingleTestRunActivityResult:
    logger.info(
        "PrepareSingleTestRunActivity: starting for test_asset_id=%s", input.test_asset_id
    )
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(input.application_id))
        ).one()
        test_asset = session.exec(
            select(TestAsset).where(TestAsset.external_id == uuid.UUID(input.test_asset_id))
        ).one()

        # Claim this Application's next run_number atomically, same idiom
        # `_prepare_test_run_sync` (execution_worker/activities.py) uses —
        # `TestRun.run_number` is NOT NULL with a unique
        # `(application_id, run_number)` constraint, so a lone "Add Test
        # Case" TestRun needs one too, not just a "Run All Tests" one.
        run_number = session.execute(
            update(Application)
            .where(Application.id == application.id)  # type: ignore[arg-type]
            .values(next_test_run_number=Application.next_test_run_number + 1)
            .returning(Application.next_test_run_number - 1)  # type: ignore[arg-type]
        ).scalar_one()

        test_run = TestRun(
            application_id=application.id,
            run_number=run_number,
            status="running",
            environment_snapshot=application.environment,
            target_base_url_snapshot=application.url,
            triggered_by_name="Add Test Case",
            started_at=datetime.now(UTC),
            total_count=1,
        )
        session.add(test_run)
        session.commit()
        session.refresh(test_run)

        test_result = TestResult(
            test_run_id=test_run.id,
            test_asset_id=test_asset.id,
            scenario_id=test_asset.scenario_id,
            status="pending",
        )
        session.add(test_result)
        session.commit()
        session.refresh(test_result)

        try:
            inputs = _load_single_assembly_inputs_sync(session, application, test_asset)
            dest_dir = project_dir_for(test_run.external_id)
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
            if inputs.login_evidence is not None:
                _run_auth_setup_once(dest_dir, application)
        except Exception as exc:  # noqa: BLE001 — infra failure, not a test outcome
            test_result.status = "errored"
            test_result.error_message = f"failed to prepare the test project: {exc}"
            test_result.completed_at = datetime.now(UTC)
            session.add(test_result)
            test_run.errored_count = 1
            test_run.status = "completed"
            test_run.completed_at = datetime.now(UTC)
            session.add(test_run)
            session.commit()
            logger.error(
                "PrepareSingleTestRunActivity: test_run_id=%s failed to prepare project: %s",
                test_run.external_id,
                exc,
            )
            # Re-raised (unlike `_prepare_test_run_sync`'s own all-assets
            # version, which just returns an empty executable list) — there's
            # only ever one test here, so "prepare failed" and "nothing to
            # execute" are the same event; the workflow's own try/except
            # around this activity turns it into a `status="failed"` result.
            raise RuntimeError(f"failed to prepare the test project: {exc}") from exc

        logger.info(
            "PrepareSingleTestRunActivity: test_run_id=%s prepared test_result_id=%s",
            test_run.external_id,
            test_result.external_id,
        )
        return PrepareSingleTestRunActivityResult(
            test_run_id=str(test_run.external_id),
            test_result_id=str(test_result.external_id),
        )


@activity.defn(name="PrepareSingleTestRunActivity")
async def prepare_single_test_run_activity(
    input: PrepareSingleTestRunActivityInput,
) -> PrepareSingleTestRunActivityResult:
    return await asyncio.to_thread(_prepare_single_test_run_sync, input)


def _read_test_result_status_sync(
    input: ReadTestResultStatusActivityInput,
) -> ReadTestResultStatusResult:
    with Session(engine) as session:
        test_result = session.exec(
            select(TestResult).where(TestResult.external_id == uuid.UUID(input.test_result_id))
        ).one()
        return ReadTestResultStatusResult(
            status=test_result.status, error_message=test_result.error_message
        )


@activity.defn(name="ReadTestResultStatusActivity")
async def read_test_result_status_activity(
    input: ReadTestResultStatusActivityInput,
) -> ReadTestResultStatusResult:
    return await asyncio.to_thread(_read_test_result_status_sync, input)
