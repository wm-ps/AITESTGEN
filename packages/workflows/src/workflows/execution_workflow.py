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

DEFAULT_MAX_CONCURRENCY = 5


@dataclass
class ExecutionWorkflowInput:
    application_id: str
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    triggered_by_name: str | None = None


@dataclass
class PrepareTestRunActivityInput:
    application_id: str
    triggered_by_name: str | None = None


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


@workflow.defn(name="ApplicationTestExecutionWorkflow")
class ApplicationTestExecutionWorkflow:
    @workflow.run
    async def run(self, input: ExecutionWorkflowInput) -> str:
        prep: PrepareTestRunActivityResult = await workflow.execute_activity(
            PREPARE_TEST_RUN_ACTIVITY_NAME,
            PrepareTestRunActivityInput(
                application_id=input.application_id,
                triggered_by_name=input.triggered_by_name,
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
                    return await workflow.execute_activity(
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

            await asyncio.gather(
                *[run_one(item) for item in prep.executable], return_exceptions=True
            )

        await workflow.execute_activity(
            FINALIZE_TEST_RUN_ACTIVITY_NAME,
            FinalizeTestRunActivityInput(test_run_id=prep.test_run_id),
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        return prep.test_run_id


__all__ = [
    "DEFAULT_MAX_CONCURRENCY",
    "EXECUTE_TEST_ACTIVITY_NAME",
    "EXECUTION_TASK_QUEUE",
    "FINALIZE_TEST_RUN_ACTIVITY_NAME",
    "PREPARE_TEST_RUN_ACTIVITY_NAME",
    "ApplicationTestExecutionWorkflow",
    "ExecutableTest",
    "ExecuteTestActivityInput",
    "ExecutionWorkflowInput",
    "FinalizeTestRunActivityInput",
    "PrepareTestRunActivityInput",
    "PrepareTestRunActivityResult",
]
