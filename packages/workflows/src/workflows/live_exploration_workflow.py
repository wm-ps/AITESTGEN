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

Per-scenario execute+heal here is an internal correctness check only — it
exists so a broken locator gets caught and fixed before a test case ever
ships, never to report a result to the user. Its `TestRun`/`TestResult` rows
are discarded (`DiscardTestRunActivity`) the moment they've been read,
regardless of pass/fail/healed outcome, so they never leak into the
dashboard's run stats or the Runs tab (both list every `TestRun` for an
Application with no filter). The generated `TestAsset` — healed or not —
still becomes the Scenario's current code either way; the user's own
"Run All Tests" click is always the first *real*, visible execution, via the
regular `HealTestActivity` if it fails there.

`LiveExploreActivity`/`LiveHealActivity` run on `LIVE_EXPLORATION_TASK_QUEUE`,
not `GENERATION_TASK_QUEUE` — they spawn a Node/Playwright-MCP subprocess and
a multi-turn LLM loop, long enough (heartbeating, like `DiscoveryActivity`)
that sharing generation_worker's lightweight-activity concurrency slot would
starve normal scenario/code generation.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

from workflows.add_test_case_workflow import (
    ANALYZE_PROMPT_ACTIVITY_NAME,
    DISCARD_TEST_RUN_ACTIVITY_NAME,
    PREPARE_SINGLE_TEST_RUN_ACTIVITY_NAME,
    READ_TEST_RESULT_STATUS_ACTIVITY_NAME,
    AnalyzePromptActivityInput,
    DiscardTestRunActivityInput,
    PrepareSingleTestRunActivityInput,
    PrepareSingleTestRunActivityResult,
    PromptAnalysisResult,
    ReadTestResultStatusActivityInput,
    ReadTestResultStatusResult,
)
from workflows.execution_workflow import (
    EXECUTE_TEST_ACTIVITY_NAME,
    EXECUTION_TASK_QUEUE,
    ExecuteTestActivityInput,
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
MERGE_LIVE_JOURNEY_ACTIVITY_NAME = "MergeLiveJourneyActivity"
# ApplicationError type LiveExploreActivity raises when the saved credentials
# don't get past the login form — reported to the author, never retried.
LOGIN_FAILED_ERROR_TYPE = "LiveExplorationLoginFailed"
# Raised when the agent couldn't do a step the requirement asks for (a named
# item missing, a stall) — its message is plain language for the author.
EXPLORATION_BLOCKED_ERROR_TYPE = "LiveExplorationBlocked"
_AUTHOR_FACING_ERROR_TYPES = (LOGIN_FAILED_ERROR_TYPE, EXPLORATION_BLOCKED_ERROR_TYPE)

# Each internal verify+heal pass (execute -> heal -> re-execute) takes
# several real minutes (a live browser run, and on failure a whole second
# live-agent/MCP heal session) — for a journey with many scenarios this adds
# up to tens of minutes before the request ever shows "complete" (observed
# live: 8 scenarios, several needing a heal, ~35+ minutes total). Capping how
# many scenarios get this treatment bounds that wall-clock time; every
# scenario still gets its Playwright code generated (the loop just above
# `_generate_and_verify_one`'s own loop, unaffected by this cap) — only the
# extra execute+heal verification is skipped past the cap.
# `[TEMPORARY 2026-09-10]` Set to 1, not the originally-requested 5, at the
# user's explicit request while testing — expected to be raised again later.
MAX_VERIFIED_SCENARIOS_PER_JOURNEY = 1

# A flat 30-turn budget covers one flow; a prompt listing ten test cases ran
# out of turns a third of the way in and generated from a partial transcript.
# Scale by the analyzed action count (AnalyzePromptActivity's `actions`, one
# per distinct flow/step group). Timeout follows at ~40s/turn (an LLM call on
# a full snapshot plus the action and its settle).
# ponytail: linear per-action budget, a planner that explores each test case
# in its own session would scale better for very long prompts.
EXPLORE_MIN_TURNS = 30
EXPLORE_TURNS_PER_ACTION = 12
EXPLORE_MAX_TURNS_CAP = 150


def _live_scenario_counts(counts: dict[str, int], *, skipped: int, completed: int) -> dict[str, int]:
    """A prompt saying "create exactly 10" where only some cases were done live
    must ask for that many, or generation pads the set with invented ones.
    The completed count wins when the agent reported one ("Remaining test
    cases" can stand for several); otherwise skips come off. Applied to the
    largest bucket — listed test cases are almost always one type.
    ponytail: per-type attribution if mixed-type lists ever need it."""
    if not counts or not (skipped or completed):
        return counts
    largest = max(counts, key=lambda k: counts[k])
    target = completed or counts[largest] - skipped
    return {**counts, largest: max(1, target)}


def explore_turn_budget(action_count: int) -> int:
    return max(EXPLORE_MIN_TURNS, min(EXPLORE_MAX_TURNS_CAP, EXPLORE_TURNS_PER_ACTION * action_count))


@dataclass
class LiveExplorationWorkflowInput:
    application_id: str
    prompt: str
    # The author chooses where the test case lands — exactly one is set by
    # the API: an existing Journey's external id (the new Scenarios are
    # merged into it), or the name for a brand-new Journey. Both None only
    # for a request started before this existed (auto-named new Journey).
    journey_id: str | None = None
    journey_name: str | None = None


@dataclass
class LiveExploreActivityInput:
    application_id: str
    requirement: str
    # AnalyzePromptActivity's short business-language summary (e.g. "Verify
    # sign-in and sign-out both work") — used to name the Journey instead of
    # truncating the raw, often multi-line/instructional `requirement` text.
    functionality_summary: str = ""
    # User-given name for the new Journey; overrides `functionality_summary`.
    journey_name: str = ""
    # `explore_turn_budget(...)`; 0 = the activity's own default.
    max_turns: int = 0


@dataclass
class LiveExploreActivityResult:
    discovery_run_id: str
    page_ids: list[str]
    goal_satisfied: bool
    journey_id: str
    journey_name: str
    # "<case name>: <plain reason>" per listed test case the agent couldn't do.
    skipped_cases: list[str] = field(default_factory=list)
    # Listed test cases the agent saw through to their expected result; 0
    # for a single-flow requirement (nothing to count).
    completed_case_count: int = 0


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
class MergeLiveJourneyActivityInput:
    source_journey_id: str
    target_journey_id: str
    scenario_ids: list[str]


@dataclass
class MergeLiveJourneyActivityResult:
    journey_name: str


@dataclass
class LiveExplorationResult:
    status: str  # rejected | failed | complete
    journey_id: str | None = None
    journey_name: str | None = None
    rejection_reason: str | None = None
    error_message: str | None = None
    skipped_cases: list[str] = field(default_factory=list)
    # The Scenarios this request generated — a merged-into existing Journey
    # also holds older ones, so the status read filters to these.
    scenario_ids: list[str] = field(default_factory=list)


@workflow.defn(name="LiveExplorationTestWorkflow")
class LiveExplorationTestWorkflow:
    def __init__(self) -> None:
        self._status = "exploring"

    @workflow.query
    def get_status(self) -> str:
        return self._status

    async def _generate_and_verify_one(
        self, application_id: str, scenario_id: str, test_suite_id: str
    ) -> None:
        """Generates one Scenario's Playwright code, then runs+heals it once
        purely to catch and fix a broken locator before it ships — never to
        report a result. See the module docstring for why every `TestRun`
        this creates gets discarded rather than finalized."""
        test_asset_id: str = await workflow.execute_activity(
            PLAYWRIGHT_GENERATION_ACTIVITY_NAME,
            PlaywrightGenerationActivityInput(scenario_id=scenario_id, test_suite_id=test_suite_id),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=str,
        )
        if not test_asset_id:
            return

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
        test_run_ids_to_discard = [run_prep.test_run_id]
        try:
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
                if heal_result.healed:
                    # A fresh TestRun/TestResult, not a reuse of run_prep's —
                    # ExecuteTestActivity's own idempotency guard skips a
                    # test_result_id whose status isn't "pending" (it assumes a
                    # repeat call is Temporal's at-least-once redelivery of the
                    # SAME attempt), so replaying the original, already-"failed"
                    # test_result_id here silently no-ops instead of actually
                    # running the healed code. This is the same
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
                    test_run_ids_to_discard.append(heal_run_prep.test_run_id)
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
                    # No status read here on purpose — whether the healed
                    # re-execution actually passed is never checked. Whatever
                    # TestAsset this produced ships as the Scenario's current
                    # code either way; only the user's own "Run All Tests"
                    # click ever determines whether it really works.
        finally:
            # Internal verification only, done either way (passed, failed, or
            # never even attempted a heal) — every TestRun created above is
            # discarded, never finalized into real history. The healed-or-not
            # TestAsset this scenario ends up with is what ships; whether it
            # actually passes is something only the user's own "Run All Tests"
            # click ever surfaces.
            for test_run_id in test_run_ids_to_discard:
                await workflow.execute_activity(
                    DISCARD_TEST_RUN_ACTIVITY_NAME,
                    DiscardTestRunActivityInput(test_run_id=test_run_id),
                    task_queue=EXECUTION_TASK_QUEUE,
                    start_to_close_timeout=timedelta(minutes=1),
                    retry_policy=RetryPolicy(maximum_attempts=3),
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

        max_turns = explore_turn_budget(len(analysis.actions))
        try:
            explore_result: LiveExploreActivityResult = await workflow.execute_activity(
                LIVE_EXPLORE_ACTIVITY_NAME,
                LiveExploreActivityInput(
                    application_id=input.application_id,
                    requirement=input.prompt,
                    functionality_summary=analysis.functionality_summary,
                    journey_name=input.journey_name or "",
                    max_turns=max_turns,
                ),
                task_queue=LIVE_EXPLORATION_TASK_QUEUE,
                start_to_close_timeout=max(
                    timedelta(minutes=20), timedelta(seconds=40 * max_turns)
                ),
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
        except ActivityError as err:
            cause = err.cause
            if isinstance(cause, ApplicationError) and cause.type in _AUTHOR_FACING_ERROR_TYPES:
                self._status = "failed"
                return LiveExplorationResult(status="failed", error_message=cause.message)
            raise

        self._status = "generating"

        scenario_ids: list[str] = await workflow.execute_activity(
            SCENARIO_GENERATION_ACTIVITY_NAME,
            ScenarioGenerationActivityInput(
                journey_id=explore_result.journey_id,
                source="nl",
                requested_scenario_counts=_live_scenario_counts(
                    analysis.requested_scenario_counts,
                    skipped=len(explore_result.skipped_cases),
                    completed=explore_result.completed_case_count,
                ),
                provided_test_data=analysis.provided_test_data,
            ),
            task_queue=GENERATION_TASK_QUEUE,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=list[str],
        )

        # Explored as its own Journey either way (so Scenario generation
        # sees exactly this flow), then folded into the author's chosen
        # existing Journey before any code is generated.
        journey_id, journey_name = explore_result.journey_id, explore_result.journey_name
        if input.journey_id:
            merge_result: MergeLiveJourneyActivityResult = await workflow.execute_activity(
                MERGE_LIVE_JOURNEY_ACTIVITY_NAME,
                MergeLiveJourneyActivityInput(
                    source_journey_id=explore_result.journey_id,
                    target_journey_id=input.journey_id,
                    scenario_ids=scenario_ids,
                ),
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=3),
                result_type=MergeLiveJourneyActivityResult,
            )
            journey_id, journey_name = input.journey_id, merge_result.journey_name

        prep: EnsureTestSuiteActivityResult = await workflow.execute_activity(
            ENSURE_TEST_SUITE_ACTIVITY_NAME,
            EnsureTestSuiteActivityInput(journey_id=journey_id),
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=EnsureTestSuiteActivityResult,
        )

        # `[FIXED]` A TestSuite row exists from here on (`prep.test_suite_id`,
        # written 'generating' by EnsureTestSuiteActivity above) — if
        # anything below exhausts its retries and the workflow itself ends
        # up failed, that row previously stayed at 'generating' forever
        # (nothing ever finalizes it on the way out via an exception), which
        # permanently wedges TestSuiteTab.tsx's "is anything still
        # generating" check for the WHOLE application, not just this one
        # journey — every other, already-complete suite included. Finalizing
        # as "incomplete" here (the same terminal value SuiteGenerationWorkflow
        # already uses for an unfinished run) before re-raising fixes that
        # generically for any failure in this section, not just one cause.
        try:
            # Only this request's Scenarios — `prep.scenario_ids` is every
            # current one on the Journey, which for an existing Journey
            # would regenerate its older test cases' code too.
            for scenario_id in scenario_ids:
                await workflow.execute_activity(
                    PLAYWRIGHT_GENERATION_ACTIVITY_NAME,
                    PlaywrightGenerationActivityInput(
                        scenario_id=scenario_id, test_suite_id=prep.test_suite_id
                    ),
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                    result_type=str,
                )

            for scenario_id in scenario_ids[:MAX_VERIFIED_SCENARIOS_PER_JOURNEY]:
                # Best-effort: every test case is already generated and saved
                # by now, so a verify-pass failure (observed live: the
                # target app's login page timing out on the post-heal re-run)
                # must never fail the whole request — the user's own run
                # surfaces whether the test really works.
                try:
                    await self._generate_and_verify_one(
                        input.application_id, scenario_id, prep.test_suite_id
                    )
                except ActivityError:
                    workflow.logger.warning(
                        "LiveExplorationTestWorkflow: verify pass for scenario_id=%s failed, "
                        "keeping its generated test case as-is",
                        scenario_id,
                        exc_info=True,
                    )
        except BaseException:
            await workflow.execute_activity(
                FINALIZE_SUITE_GENERATION_ACTIVITY_NAME,
                FinalizeSuiteGenerationActivityInput(
                    test_suite_id=prep.test_suite_id,
                    status="incomplete",
                ),
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            raise

        # Always "complete" here — the internal verify+heal pass above no
        # longer reports a per-scenario outcome to key "incomplete" off of;
        # every scenario got a TestAsset either way, healed or not.
        await workflow.execute_activity(
            FINALIZE_SUITE_GENERATION_ACTIVITY_NAME,
            FinalizeSuiteGenerationActivityInput(
                test_suite_id=prep.test_suite_id,
                status="complete",
            ),
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        self._status = "complete"
        return LiveExplorationResult(
            status="complete",
            journey_id=journey_id,
            journey_name=journey_name,
            scenario_ids=scenario_ids,
            skipped_cases=explore_result.skipped_cases,
        )


__all__ = [
    "LIVE_EXPLORATION_TASK_QUEUE",
    "LIVE_EXPLORE_ACTIVITY_NAME",
    "LIVE_HEAL_ACTIVITY_NAME",
    "LOGIN_FAILED_ERROR_TYPE",
    "EXPLORATION_BLOCKED_ERROR_TYPE",
    "MERGE_LIVE_JOURNEY_ACTIVITY_NAME",
    "LiveExploreActivityInput",
    "LiveExploreActivityResult",
    "LiveExplorationResult",
    "LiveExplorationTestWorkflow",
    "LiveExplorationWorkflowInput",
    "LiveHealActivityInput",
    "LiveHealActivityResult",
    "MAX_VERIFIED_SCENARIOS_PER_JOURNEY",
    "MergeLiveJourneyActivityInput",
    "MergeLiveJourneyActivityResult",
]
