"""LiveExplorationTestWorkflow — NL requirement -> live browser exploration ->
test generation, with **zero** dependency on crawler/discovery data.

This is the only natural-language test-case creation path (see
`natural_language_flow.png`) — it works from nothing but the requirement
text and the real, live application, never a match against a prior crawl.
See `generation_worker.live_exploration.agent`/`materialize` for how.
`LiveExploreActivity` materializes what it found into a fresh, isolated
`DiscoveryRun(source="live_exploration")` + `Page`/`Component` set (never
reading any pre-existing one) and creates the Journey row itself — no
separate journey-generation step — persisting the literal live-exploration
transcript onto `Journey.captured_flow` so `ScenarioGenerationActivity`
(reused **unmodified** otherwise — it already works generically off those
tables regardless of who wrote them) can ground Scenarios in what actually
happened instead of only the crawler-shaped Form/Component reinterpretation.

`LiveHealActivity` replaces `HealTestActivity` for this workflow only (same
MCP-driven live re-exploration, narrower "find the current locator for this
one failed step" goal) — it never touches `ApplicationTestExecutionWorkflow`'s
own `HealTestActivity`. Unlike
`HealTestActivity` (which re-executes internally), `LiveHealActivity` only
finds the fix and regenerates code; re-execution is `ExecuteTestActivity`,
called again here with the new TestAsset id if healing produced one — kept
this way so no execution-subprocess logic is duplicated into
generation_worker.

`LiveExploreActivity`/`LiveHealActivity` run on `LIVE_EXPLORATION_TASK_QUEUE`,
not `GENERATION_TASK_QUEUE` — they spawn a Node/Playwright-MCP subprocess and
a multi-turn LLM loop, long enough (heartbeating, like `DiscoveryActivity`)
that sharing generation_worker's lightweight-activity concurrency slot would
starve normal scenario/code generation.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from workflows.add_test_case_workflow import (
    ANALYZE_PROMPT_ACTIVITY_NAME,
    PREPARE_SINGLE_TEST_RUN_ACTIVITY_NAME,
    READ_TEST_RESULT_STATUS_ACTIVITY_NAME,
    AnalyzePromptActivityInput,
    PrepareSingleTestRunActivityInput,
    PrepareSingleTestRunActivityResult,
    PromptAnalysisResult,
    ReadTestResultStatusActivityInput,
    ReadTestResultStatusResult,
)
from workflows.execution_workflow import (
    EXECUTE_TEST_ACTIVITY_NAME,
    EXECUTION_TASK_QUEUE,
    FINALIZE_TEST_RUN_ACTIVITY_NAME,
    ExecuteTestActivityInput,
    FinalizeTestRunActivityInput,
)
from workflows.generation_workflow import (
    GENERATION_TASK_QUEUE,
    SCENARIO_GENERATION_ACTIVITY_NAME,
    ScenarioGenerationActivityInput,
)
from workflows.suite_generation_workflow import (
    ENSURE_TEST_SUITE_ACTIVITY_NAME,
    FINALIZE_SUITE_GENERATION_ACTIVITY_NAME,
    PLAYWRIGHT_GENERATION_ACTIVITY_NAME,
    EnsureTestSuiteActivityInput,
    EnsureTestSuiteActivityResult,
    FinalizeSuiteGenerationActivityInput,
    PlaywrightGenerationActivityInput,
)

LIVE_EXPLORATION_TASK_QUEUE = "live-exploration-task-queue"
LIVE_EXPLORE_ACTIVITY_NAME = "LiveExploreActivity"
LIVE_HEAL_ACTIVITY_NAME = "LiveHealActivity"


@dataclass
class LiveExplorationWorkflowInput:
    application_id: str
    prompt: str


@dataclass
class LiveExploreActivityInput:
    application_id: str
    requirement: str
    # AnalyzePromptActivity's short business-language summary (e.g. "Verify
    # sign-in and sign-out both work") — used to name the Journey instead of
    # truncating the raw, often multi-line/instructional `requirement` text.
    functionality_summary: str = ""


@dataclass
class LiveExploreActivityResult:
    discovery_run_id: str
    page_ids: list[str]
    goal_satisfied: bool
    journey_id: str
    journey_name: str


@dataclass
class LiveHealActivityInput:
    application_id: str
    test_run_id: str
    test_result_id: str


@dataclass
class LiveHealActivityResult:
    healed: bool
    test_asset_id: str


@dataclass
class LiveExplorationScenarioResult:
    scenario_id: str
    test_result_status: str | None = None
    healed: bool = False
    error_message: str | None = None


@dataclass
class LiveExplorationResult:
    status: str  # rejected | complete
    journey_id: str | None = None
    journey_name: str | None = None
    rejection_reason: str | None = None
    scenarios: list[LiveExplorationScenarioResult] | None = None


@workflow.defn(name="LiveExplorationTestWorkflow")
class LiveExplorationTestWorkflow:
    def __init__(self) -> None:
        self._status = "exploring"

    @workflow.query
    def get_status(self) -> str:
        return self._status

    async def _generate_and_run_one(
        self, application_id: str, scenario_id: str, test_suite_id: str
    ) -> LiveExplorationScenarioResult:
        test_asset_id: str = await workflow.execute_activity(
            PLAYWRIGHT_GENERATION_ACTIVITY_NAME,
            PlaywrightGenerationActivityInput(scenario_id=scenario_id, test_suite_id=test_suite_id),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=str,
        )
        if not test_asset_id:
            return LiveExplorationScenarioResult(
                scenario_id=scenario_id, error_message="Code generation was skipped."
            )

        run_prep: PrepareSingleTestRunActivityResult = await workflow.execute_activity(
            PREPARE_SINGLE_TEST_RUN_ACTIVITY_NAME,
            PrepareSingleTestRunActivityInput(
                application_id=application_id, test_asset_id=test_asset_id
            ),
            task_queue=EXECUTION_TASK_QUEUE,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=2),
            result_type=PrepareSingleTestRunActivityResult,
        )
        await workflow.execute_activity(
            EXECUTE_TEST_ACTIVITY_NAME,
            ExecuteTestActivityInput(
                application_id=application_id,
                test_run_id=run_prep.test_run_id,
                test_result_id=run_prep.test_result_id,
                test_asset_id=test_asset_id,
            ),
            task_queue=EXECUTION_TASK_QUEUE,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=2),
            result_type=str,
        )

        status_result: ReadTestResultStatusResult = await workflow.execute_activity(
            READ_TEST_RESULT_STATUS_ACTIVITY_NAME,
            ReadTestResultStatusActivityInput(test_result_id=run_prep.test_result_id),
            task_queue=EXECUTION_TASK_QUEUE,
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=ReadTestResultStatusResult,
        )
        healed = False
        if status_result.status not in ("passed", "blocked"):
            heal_result: LiveHealActivityResult = await workflow.execute_activity(
                LIVE_HEAL_ACTIVITY_NAME,
                LiveHealActivityInput(
                    application_id=application_id,
                    test_run_id=run_prep.test_run_id,
                    test_result_id=run_prep.test_result_id,
                ),
                task_queue=LIVE_EXPLORATION_TASK_QUEUE,
                start_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(minutes=2),
                # 2, not 1 — a worker restart/crash mid-activity currently
                # surfaces as a heartbeat timeout with nothing left to retry,
                # failing the whole run over pure infra flakiness rather than
                # a real heal failure. One retry re-runs from scratch (a
                # fresh MCP session, fresh materialize) — safe here since a
                # genuine non-convergence still exhausts both attempts and
                # reports not-healed, same as before.
                retry_policy=RetryPolicy(maximum_attempts=2),
                result_type=LiveHealActivityResult,
            )
            healed = heal_result.healed
            if healed:
                # A fresh TestRun/TestResult, not a reuse of run_prep's —
                # ExecuteTestActivity's own idempotency guard skips a
                # test_result_id whose status isn't "pending" (it assumes a
                # repeat call is Temporal's at-least-once redelivery of the
                # SAME attempt), so replaying the original, already-"failed"
                # test_result_id here silently no-ops instead of actually
                # running the healed code — the healed asset would report
                # the pre-heal failure as final. This is the same
                # PrepareSingleTestRunActivity call used for the first
                # attempt, just re-invoked with the healed asset id.
                heal_run_prep: PrepareSingleTestRunActivityResult = await workflow.execute_activity(
                    PREPARE_SINGLE_TEST_RUN_ACTIVITY_NAME,
                    PrepareSingleTestRunActivityInput(
                        application_id=application_id, test_asset_id=heal_result.test_asset_id
                    ),
                    task_queue=EXECUTION_TASK_QUEUE,
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                    result_type=PrepareSingleTestRunActivityResult,
                )
                await workflow.execute_activity(
                    EXECUTE_TEST_ACTIVITY_NAME,
                    ExecuteTestActivityInput(
                        application_id=application_id,
                        test_run_id=heal_run_prep.test_run_id,
                        test_result_id=heal_run_prep.test_result_id,
                        test_asset_id=heal_result.test_asset_id,
                    ),
                    task_queue=EXECUTION_TASK_QUEUE,
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                    result_type=str,
                )
                status_result = await workflow.execute_activity(
                    READ_TEST_RESULT_STATUS_ACTIVITY_NAME,
                    ReadTestResultStatusActivityInput(test_result_id=heal_run_prep.test_result_id),
                    task_queue=EXECUTION_TASK_QUEUE,
                    start_to_close_timeout=timedelta(minutes=1),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                    result_type=ReadTestResultStatusResult,
                )
                await workflow.execute_activity(
                    FINALIZE_TEST_RUN_ACTIVITY_NAME,
                    FinalizeTestRunActivityInput(test_run_id=heal_run_prep.test_run_id),
                    task_queue=EXECUTION_TASK_QUEUE,
                    start_to_close_timeout=timedelta(minutes=1),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )

        await workflow.execute_activity(
            FINALIZE_TEST_RUN_ACTIVITY_NAME,
            FinalizeTestRunActivityInput(test_run_id=run_prep.test_run_id),
            task_queue=EXECUTION_TASK_QUEUE,
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        return LiveExplorationScenarioResult(
            scenario_id=scenario_id,
            test_result_status=status_result.status,
            healed=healed,
            error_message=status_result.error_message,
        )

    @workflow.run
    async def run(self, input: LiveExplorationWorkflowInput) -> LiveExplorationResult:
        analysis: PromptAnalysisResult = await workflow.execute_activity(
            ANALYZE_PROMPT_ACTIVITY_NAME,
            AnalyzePromptActivityInput(prompt=input.prompt),
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=PromptAnalysisResult,
        )
        if not analysis.is_relevant:
            self._status = "rejected"
            return LiveExplorationResult(
                status="rejected", rejection_reason=analysis.rejection_reason
            )

        explore_result: LiveExploreActivityResult = await workflow.execute_activity(
            LIVE_EXPLORE_ACTIVITY_NAME,
            LiveExploreActivityInput(
                application_id=input.application_id,
                requirement=input.prompt,
                functionality_summary=analysis.functionality_summary,
            ),
            task_queue=LIVE_EXPLORATION_TASK_QUEUE,
            start_to_close_timeout=timedelta(minutes=20),
            heartbeat_timeout=timedelta(minutes=2),
            # 2, not 1 — see LiveHealActivity's retry_policy comment below:
            # a worker restart/crash currently surfaces as an unrecoverable
            # heartbeat timeout otherwise. Journey creation's identity_key
            # dedup (live_exploration_activities.py) already makes a retry
            # safe — worst case a retry leaves one extra orphaned
            # DiscoveryRun/Page from the dead first attempt, never a
            # duplicate Journey.
            retry_policy=RetryPolicy(maximum_attempts=2),
            result_type=LiveExploreActivityResult,
        )

        self._status = "generating"

        await workflow.execute_activity(
            SCENARIO_GENERATION_ACTIVITY_NAME,
            ScenarioGenerationActivityInput(
                journey_id=explore_result.journey_id,
                source="nl",
                requested_scenario_counts=analysis.requested_scenario_counts,
                provided_test_data=analysis.provided_test_data,
            ),
            task_queue=GENERATION_TASK_QUEUE,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=list[str],
        )

        prep: EnsureTestSuiteActivityResult = await workflow.execute_activity(
            ENSURE_TEST_SUITE_ACTIVITY_NAME,
            EnsureTestSuiteActivityInput(journey_id=explore_result.journey_id),
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=EnsureTestSuiteActivityResult,
        )

        for scenario_id in prep.scenario_ids:
            await workflow.execute_activity(
                PLAYWRIGHT_GENERATION_ACTIVITY_NAME,
                PlaywrightGenerationActivityInput(
                    scenario_id=scenario_id, test_suite_id=prep.test_suite_id
                ),
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
                result_type=str,
            )

        self._status = "running"

        results = []
        for scenario_id in prep.scenario_ids:
            results.append(
                await self._generate_and_run_one(
                    input.application_id, scenario_id, prep.test_suite_id
                )
            )

        # `[FIXED]` regression: unlike SuiteGenerationWorkflow, this workflow
        # never finalized test_suite.status — it stayed at the column's
        # 'generating' default forever, so TestSuiteResults.tsx's isComplete
        # check (every suite's status must leave 'generating') never
        # flipped, and its count-so-far loader spun past the point this
        # workflow had actually finished.
        pending = any(r.test_result_status is None for r in results)
        await workflow.execute_activity(
            FINALIZE_SUITE_GENERATION_ACTIVITY_NAME,
            FinalizeSuiteGenerationActivityInput(
                test_suite_id=prep.test_suite_id,
                status="incomplete" if pending else "complete",
            ),
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        self._status = "complete"
        return LiveExplorationResult(
            status="complete",
            journey_id=explore_result.journey_id,
            journey_name=explore_result.journey_name,
            scenarios=results,
        )


__all__ = [
    "LIVE_EXPLORATION_TASK_QUEUE",
    "LIVE_EXPLORE_ACTIVITY_NAME",
    "LIVE_HEAL_ACTIVITY_NAME",
    "LiveExploreActivityInput",
    "LiveExploreActivityResult",
    "LiveExplorationResult",
    "LiveExplorationScenarioResult",
    "LiveExplorationTestWorkflow",
    "LiveExplorationWorkflowInput",
    "LiveHealActivityInput",
    "LiveHealActivityResult",
]
