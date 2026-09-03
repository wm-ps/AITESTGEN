"""ApplicationTestExecutionWorkflow — Run All Tests feature.

Unit of execution is the whole Application (per the grill-me design
review): one click runs every current `TestAsset` across every current
`TestSuite`/Journey for the Application, not one suite/test at a time.

`PrepareTestRunActivity` creates the `TestRun`/`TestResult` rows for every
current `TestAsset` before any Playwright process ever runs — there is no
execution-policy/safety-classification gating anymore (removed per explicit
request, see `execution_worker.activities._prepare_test_run_sync`'s own
ponytail note; `prep.blocked` below is dead code kept only in case that gate
is reintroduced). `ExecuteTestActivity` runs once per executable test,
fanned out through an `asyncio.Semaphore` (bounds concurrency *within* this
one run — a separate concern from the execution worker's own
`Worker(max_concurrent_activities=...)`, which bounds concurrency *across*
concurrent runs on that worker process; see `apps/workers/execution`).

Individual test outcomes (pass/fail/timeout/error) never raise out of
`ExecuteTestActivity` — they're recorded as `TestResult` rows and the
workflow keeps going, mirroring `SuiteGenerationWorkflow`'s own
fault-isolation fan-out. `return_exceptions=True` on the `asyncio.gather`
below is a backstop for genuine infra failures (an activity that exhausts
its own retries) so one test's tooling failure still can't block
`FinalizeTestRunActivity` from running for the rest.

Every "Run All Tests" click starts a brand-new `TestRun` — there is no
rerun-scoped/failed-only mode and no natural idempotency key the way
`suite-{journey_id}-{attempt}` has, so the workflow id
(`execution-{application_id}-{test_run_external_id}`) only needs to be
unique, not deterministic/replayable.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

EXECUTION_TASK_QUEUE = "execution-task-queue"
PREPARE_TEST_RUN_ACTIVITY_NAME = "PrepareTestRunActivity"
EXECUTE_TEST_ACTIVITY_NAME = "ExecuteTestActivity"
FINALIZE_TEST_RUN_ACTIVITY_NAME = "FinalizeTestRunActivity"
FORCE_COMPLETE_TEST_RUN_ACTIVITY_NAME = "ForceCompleteTestRunActivity"
HEAL_TEST_ACTIVITY_NAME = "HealTestActivity"

DEFAULT_MAX_CONCURRENCY = 5

# Self-healing for failed generated Playwright test cases. "blocked" is
# excluded — a safety-policy gate, not a code defect, never healable.
HEALABLE_STATUSES = {"failed", "timed_out", "errored"}

# Generous margin over HealTestActivity's own 28-minute
# start_to_close_timeout below — a TestResult.heal_started_at claim older
# than this is a crashed/abandoned attempt, not a real in-progress one.
# Shared (not duplicated) between execution_worker's own claim/release logic
# and the manual-retry API endpoint's pre-check, so the two can never
# disagree about what counts as "still in progress." (Was 30 min against a
# 25-min timeout; bumped by the same +3 min the timeout below gained for
# self-heal's live inspection, to preserve the original 5-min margin.)
HEAL_CLAIM_STALE_AFTER = timedelta(minutes=33)


@dataclass
class ExecutionWorkflowInput:
    application_id: str
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    triggered_by_name: str | None = None
    # Schedules feature: `Schedule.external_id` when this run was started by
    # a Temporal Schedule (via ScheduledExecutionWorkflow), None for every
    # manual run. Defaulted so `trigger_test_run` is untouched — it simply
    # doesn't pass it, and every existing call site stays byte-identical.
    schedule_id: str | None = None


@dataclass
class PrepareTestRunActivityInput:
    application_id: str
    triggered_by_name: str | None = None
    schedule_id: str | None = None


@dataclass
class ExecutableTest:
    test_result_id: str
    test_asset_id: str


@dataclass
class PrepareTestRunActivityResult:
    test_run_id: str
    blocked: bool
    executable: list[ExecutableTest] = field(default_factory=list)


@dataclass
class ExecuteTestActivityInput:
    application_id: str
    test_run_id: str
    test_result_id: str
    test_asset_id: str


@dataclass
class FinalizeTestRunActivityInput:
    test_run_id: str


@dataclass
class ForceCompleteTestRunActivityInput:
    test_run_id: str


@dataclass
class HealTestActivityInput:
    application_id: str
    test_run_id: str
    test_result_id: str


@workflow.defn(name="ApplicationTestExecutionWorkflow")
class ApplicationTestExecutionWorkflow:
    @workflow.run
    async def run(self, input: ExecutionWorkflowInput) -> str:
        prep: PrepareTestRunActivityResult = await workflow.execute_activity(
            PREPARE_TEST_RUN_ACTIVITY_NAME,
            PrepareTestRunActivityInput(
                application_id=input.application_id,
                triggered_by_name=input.triggered_by_name,
                schedule_id=input.schedule_id,
            ),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=PrepareTestRunActivityResult,
        )
        if prep.blocked:
            # PrepareTestRunActivity already set TestRun.status="blocked"
            # with a blocked_reason — the browser/Playwright path is never
            # touched.
            return prep.test_run_id

        if prep.executable:
            semaphore = asyncio.Semaphore(max(1, input.max_concurrency))

            async def run_one(item: ExecutableTest) -> str:
                async with semaphore:
                    result_id = await workflow.execute_activity(
                        EXECUTE_TEST_ACTIVITY_NAME,
                        ExecuteTestActivityInput(
                            application_id=input.application_id,
                            test_run_id=prep.test_run_id,
                            test_result_id=item.test_result_id,
                            test_asset_id=item.test_asset_id,
                        ),
                        # Generous: a real browser launch + full scenario
                        # walkthrough, not just an LLM call.
                        start_to_close_timeout=timedelta(minutes=10),
                        # Retries here are for infra failures only (the
                        # subprocess couldn't even start, a DB write
                        # failed) — a test's own pass/fail/timeout never
                        # raises, so it never consumes a retry.
                        retry_policy=RetryPolicy(maximum_attempts=2),
                        result_type=str,
                    )
                    # Always called — HealTestActivity itself no-ops for
                    # passed/blocked/budget-exhausted results (see its own
                    # docstring), so no branching is needed here. A "Run All
                    # Tests" click can now take up to max_heal_attempts×
                    # longer per failing test while this runs.
                    await workflow.execute_activity(
                        HEAL_TEST_ACTIVITY_NAME,
                        HealTestActivityInput(
                            application_id=input.application_id,
                            test_run_id=prep.test_run_id,
                            test_result_id=result_id,
                        ),
                        # Up to max_heal_attempts (default 3) attempts x (AI
                        # call + typecheck + ~8min run) + the bounded infra
                        # retries. +3 min over the original 25 for self-heal's
                        # targeted live inspection (its own ~45s budget,
                        # gated to at most once per attempt — ~150s worst
                        # case across 3 attempts, well inside this margin).
                        start_to_close_timeout=timedelta(minutes=28),
                        # Infra-failure retries at the Temporal level only,
                        # same convention as ExecuteTestActivity above.
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )
                    return result_id

            await asyncio.gather(
                *[run_one(item) for item in prep.executable], return_exceptions=True
            )

        try:
            await workflow.execute_activity(
                FINALIZE_TEST_RUN_ACTIVITY_NAME,
                FinalizeTestRunActivityInput(test_run_id=prep.test_run_id),
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except Exception:
            # FinalizeTestRunActivity exhausted its retries — every
            # TestResult may already be terminal, but TestRun.status would
            # otherwise stay "running" forever (no reconciliation job exists
            # to catch this later). Force-close it, then re-raise so the
            # workflow still shows Failed in Temporal for observability.
            await workflow.execute_activity(
                FORCE_COMPLETE_TEST_RUN_ACTIVITY_NAME,
                ForceCompleteTestRunActivityInput(test_run_id=prep.test_run_id),
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            raise
        return prep.test_run_id


@workflow.defn(name="HealTestExecutionWorkflow")
class HealTestExecutionWorkflow:
    """Thin one-activity workflow for the manual "Retry with self-heal"
    path — same HealTestActivity, same logic, as the automatic path inside
    ApplicationTestExecutionWorkflow.run_one above; there is exactly one
    implementation of "heal a test," never two.

    Started with a deterministic workflow id (`heal-{test_result_external_id}`,
    no random suffix — see the manual-retry endpoint in apps/api) so a
    duplicate/rapid double-click naturally rejects via Temporal's
    WorkflowAlreadyStartedError, the same idempotency convention
    SuiteGenerationWorkflow's `suite-{journey_id}-{attempt}` already uses,
    instead of a separate manual-use boolean flag. HealTestActivity's own
    `heal_started_at` DB-level claim (see execution_worker/activities.py)
    is the second, independent guard that also covers the narrower race
    against an automatic heal already in flight for the same TestResult —
    the workflow id alone only dedupes two manual starts."""

    @workflow.run
    async def run(self, input: HealTestActivityInput) -> None:
        await workflow.execute_activity(
            HEAL_TEST_ACTIVITY_NAME,
            input,
            # Kept identical to the automatic path's own HealTestActivity
            # timeout above — same activity, same logic, same budget.
            start_to_close_timeout=timedelta(minutes=28),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )


__all__ = [
    "DEFAULT_MAX_CONCURRENCY",
    "EXECUTE_TEST_ACTIVITY_NAME",
    "EXECUTION_TASK_QUEUE",
    "FINALIZE_TEST_RUN_ACTIVITY_NAME",
    "HEALABLE_STATUSES",
    "HEAL_CLAIM_STALE_AFTER",
    "HEAL_TEST_ACTIVITY_NAME",
    "PREPARE_TEST_RUN_ACTIVITY_NAME",
    "ApplicationTestExecutionWorkflow",
    "ExecutableTest",
    "ExecuteTestActivityInput",
    "ExecutionWorkflowInput",
    "FinalizeTestRunActivityInput",
    "HealTestActivityInput",
    "HealTestExecutionWorkflow",
    "PrepareTestRunActivityInput",
    "PrepareTestRunActivityResult",
]
