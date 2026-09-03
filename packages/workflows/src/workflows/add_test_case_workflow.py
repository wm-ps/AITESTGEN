"""AddTestCaseWorkflow — NLM "Add Test Case" feature.

Turns a user's plain-English description into one **or several** real
`Journey`/`Scenario`/`TestAsset` rows — a single prompt can decompose into
multiple distinct Scenarios (e.g. "test that login and logout both work"),
spanning one or more Journeys. Each is generated and executed independently
through the exact same Playwright generation/execution pipeline
`SuiteGenerationWorkflow`/`ApplicationTestExecutionWorkflow` already use
(`EnsureTestSuiteActivity`, `PlaywrightGenerationActivity`,
`ExecuteTestActivity`, `FinalizeTestRunActivity` are dispatched here **by
name, unmodified** — this workflow adds new Activities around them, it never
edits the existing ones), fanned out with the same fault-isolation
convention `SuiteGenerationWorkflow` already uses: one Scenario's failure
never blocks the others.

No new DB table backs a "request" here (explicit product decision — every
domain fact lands in the existing `journey`/`scenario`/`test_suite`/
`test_asset`/`test_run`/`test_result` tables). Instead, this is the first
workflow in this codebase to use `@workflow.query`: a plain instance
attribute tracks in-flight status (`_status`) for `apps/api`'s polling
endpoint to read via `query("get_status")` while running. This is still
AD-2-clean: the query handler only ever touches local Python attributes, no I/O.

Test data is never asked of the user mid-flow: `CreateScenarioActivity`
resolves whatever it can from user-supplied data (mandatory, always wins —
extracted straight from the prompt by AnalyzePromptActivity, no separate
data-entry form) and the existing Test Data Pool, and leaves anything still
unresolved for `PlaywrightGenerationActivity`'s own existing default-value
synthesis (`_resolve_scenario_defaults_sync`) to fill in — exactly how every
normal-flow Scenario already gets its test data, no "needs more data" pause.

New-Journey grouping: two or more Scenarios that all need the same brand-new
Journey (same `proposed_journey_name`) must land under ONE Journey, not one
each — `CreateJourneyActivity` creates it exactly once per distinct group,
*before* the per-Scenario fan-out, and every Scenario in that group is then
rewritten to `mode="new_scenario"` pointing at the real `journey_id`. Without
this, two concurrent `CreateScenarioActivity` calls each independently
planning "their own" new Journey would either race (harmless, the DB
constraint resolves it — see `_create_journey_sync`) or, worse, silently
create two separate Journeys for what the user asked for as one workflow.

`[FIXED]` Two more redundancy bugs, both observed live with a 6-Scenario
prompt: (1) `EnsureTestSuiteActivity` was called once *per Scenario* rather
than once per distinct Journey — several Scenarios matched to the same
existing Journey each redundantly re-resolved the same TestSuite. (2) a
`reuse_scenario` match whose Scenario already has a current TestAsset (the
common case — it was matched *because* it already covers the request) still
went through the full PlaywrightGenerationActivity + real npm-install +
browser-execution pipeline as if it were brand new, multiplying a 6-Scenario
prompt into up to 6 concurrent Playwright generations/executions even when
most of them needed none. Both are fixed by resolving each distinct Journey's
TestSuite exactly once (§ "Ensure TestSuite once per Journey" below) and by
skipping generation+execution entirely for a Scenario whose
`CreateScenarioResult.existing_test_asset_id` is already set — that Scenario
is reported `status="complete"` immediately, using its TestAsset's most
recent execution result (`ReadLatestTestResultActivity`) instead of running
a new one. This is what makes "Treat a Scenario as completed when reused
Scenario's TestAsset already exists" true, and is exactly why the workflow
used to appear stuck: it wasn't hung, it was doing 2-3x the real work a
6-Scenario request actually needed, on top of the concurrency ceiling
`GENERATION_WORKER_MAX_CONCURRENT_ACTIVITIES`/`EXECUTION_WORKER_MAX_CONCURRENT_ACTIVITIES`
already impose on this worker process.

Workflow id convention: `add-test-case-{application_id}-{request_id}`
(`request_id` a fresh `uuid4()` `apps/api` mints per submission, not a DB id) —
mirrors `suite-{journey_id}-{attempt}`'s uniqueness-not-content-derived id
scheme, just without a domain row to derive one from.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from workflows.execution_workflow import (
    EXECUTE_TEST_ACTIVITY_NAME,
    EXECUTION_TASK_QUEUE,
    FINALIZE_TEST_RUN_ACTIVITY_NAME,
    HEAL_TEST_ACTIVITY_NAME,
    ExecuteTestActivityInput,
    FinalizeTestRunActivityInput,
    HealTestActivityInput,
)
from workflows.generation_workflow import GENERATION_TASK_QUEUE
from workflows.suite_generation_workflow import (
    ENSURE_TEST_SUITE_ACTIVITY_NAME,
    PLAYWRIGHT_GENERATION_ACTIVITY_NAME,
    EnsureTestSuiteActivityInput,
    EnsureTestSuiteActivityResult,
    PlaywrightGenerationActivityInput,
)

ANALYZE_PROMPT_ACTIVITY_NAME = "AnalyzePromptActivity"
IDENTIFY_SCENARIOS_ACTIVITY_NAME = "IdentifyScenariosActivity"
CREATE_JOURNEY_ACTIVITY_NAME = "CreateJourneyActivity"
CREATE_SCENARIO_ACTIVITY_NAME = "CreateScenarioActivity"
PREPARE_SINGLE_TEST_RUN_ACTIVITY_NAME = "PrepareSingleTestRunActivity"
READ_TEST_RESULT_STATUS_ACTIVITY_NAME = "ReadTestResultStatusActivity"
READ_LATEST_TEST_RESULT_ACTIVITY_NAME = "ReadLatestTestResultActivity"


@dataclass
class AddTestCaseWorkflowInput:
    # Everything is prompt-based — no separate test-data input. Any concrete
    # value the user wants used is extracted from `prompt` itself by
    # AnalyzePromptActivity (see PromptAnalysisResult.provided_test_data).
    application_id: str
    prompt: str


@dataclass
class AnalyzePromptActivityInput:
    prompt: str


@dataclass
class PromptAnalysisResult:
    is_relevant: bool
    functionality_summary: str = ""
    actions: list[str] = field(default_factory=list)
    expected_result: str = ""
    rejection_reason: str | None = None
    # Test Data Priority: mandatory when the user stated it directly in
    # their prompt; never asked for otherwise — see this module's own
    # docstring.
    provided_test_data: dict[str, str] = field(default_factory=dict)


@dataclass
class IdentifyScenariosActivityInput:
    application_id: str
    prompt: str
    prompt_analysis: PromptAnalysisResult


@dataclass
class ScenarioRequirement:
    """One distinct Scenario a prompt decomposed into, with its own
    Journey/Scenario Decision — a single request can produce several of
    these (Multiple Test Cases)."""

    mode: str  # reuse_scenario | new_scenario | new_journey
    journey_id: str | None = None
    scenario_id: str | None = None
    proposed_journey_name: str | None = None
    proposed_capability_name: str | None = None
    proposed_scenario_name: str = ""
    functionality_summary: str = ""
    actions: list[str] = field(default_factory=list)
    expected_result: str = ""
    rationale: str = ""


@dataclass
class CreateJourneyActivityInput:
    application_id: str
    # Every requirement in this list shares one brand-new Journey (same
    # `proposed_journey_name`) — planned and created once, holistically,
    # not once per Scenario.
    requirements: list[ScenarioRequirement]


@dataclass
class CreateJourneyActivityResult:
    journey_id: str
    journey_name: str


@dataclass
class CreateScenarioActivityInput:
    application_id: str
    requirement: ScenarioRequirement
    # Test Data Priority: mandatory if the user supplied it; never asked for
    # otherwise — see this module's own docstring.
    user_provided_data: dict[str, str]


@dataclass
class CreateScenarioResult:
    journey_id: str
    scenario_id: str
    journey_name: str
    scenario_name: str
    # Duplicate Prevention / "already exists" fast path — set only for a
    # `reuse_scenario` match whose Scenario already has a current TestAsset.
    # When set, the workflow skips PlaywrightGenerationActivity and
    # execution entirely (see this module's own docstring on why).
    existing_test_asset_id: str | None = None
    # Set by `run()` (not by CreateScenarioActivity itself — the Activity has
    # no reason to know this) for every Scenario whose requirement started
    # out as `new_journey` and whose CreateJourneyActivity succeeded — lets
    # the final result say *which* Journey was newly created, not just that
    # generation succeeded.
    is_new_journey: bool = False
    # Set by `_create_scenario_safe` (not by CreateScenarioActivity itself)
    # from the resolved `requirement.mode` at call time — True for a
    # brand-new Scenario (whether under an existing Journey or one just
    # created for it; `is_new_journey` above is the tiebreaker between those
    # two in display), False for a genuine `reuse_scenario` match. Distinct
    # from `existing_test_asset_id`/`already_existed`: a reused Scenario can
    # still need a first TestAsset generated for it.
    is_new_scenario: bool = False


@dataclass
class PrepareSingleTestRunActivityInput:
    application_id: str
    test_asset_id: str


@dataclass
class PrepareSingleTestRunActivityResult:
    test_run_id: str
    test_result_id: str


@dataclass
class ReadTestResultStatusActivityInput:
    test_result_id: str


@dataclass
class ReadTestResultStatusResult:
    status: str
    error_message: str | None = None


@dataclass
class ReadLatestTestResultActivityInput:
    test_asset_id: str


@dataclass
class AddTestCaseStatus:
    status: str
    functionality_summary: str = ""
    rejection_reason: str | None = None
    # Set once IdentifyScenariosActivity returns — lets the UI say "Building
    # 3 test cases…" instead of leaving a multi-scenario request looking
    # identical to a single one while it runs.
    scenario_count: int = 0


@dataclass
class TestCaseGenerationResult:
    """One Scenario's own outcome — a single request can produce several of
    these (Multiple Test Cases), each independently PASS/FAIL."""

    # `[FIXED]` Creation vs. execution are two different questions —
    # `status` answers only the first ("was a Scenario + linked test case
    # actually created/matched and added to its Suite?"). It used to also
    # flip to "failed" when *execution* couldn't complete (an infra hiccup
    # preparing/running the already-generated test), which told the user
    # their test case didn't exist when it actually did. `status="failed"`
    # now means exactly one thing: nothing was created/added at all
    # (CreateScenarioActivity/CreateJourneyActivity/PlaywrightGenerationActivity
    # itself failed). Once a TestAsset is generated and linked, this is
    # always "complete" — a failed/errored/timed-out *run* is reported via
    # `test_result_status` instead, same vocabulary the normal Run All Tests
    # flow already uses.
    status: str  # complete | failed
    journey_name: str | None = None
    scenario_name: str | None = None
    test_result_status: str | None = None
    error_message: str | None = None
    # True only via `_report_existing` — this Scenario already had a current
    # TestAsset and was matched/reused as-is, never (re)generated or re-run.
    # Lets the UI say "matched to an existing test case" instead of implying
    # something new was just built (Requirement: an appropriate result when
    # every requested test case turns out to already exist).
    already_existed: bool = False
    # Set only for a genuinely new Journey this request created (not an
    # existing one it added a Scenario under) — lets the UI say which
    # Journey was newly created instead of just naming it like any other.
    is_new_journey: bool = False
    # NLM Matching and Creation Rules — distinguishes the "matched an
    # existing Scenario, generated its first Test Case" case from "created a
    # brand-new Scenario" for a `status="complete"` result that isn't
    # `already_existed`. Meaningless (left False) once `already_existed` or
    # `is_new_journey` is True — those already say more precisely what
    # happened, per this field's own priority order in the UI.
    is_new_scenario: bool = False
    # Set only for a `status="failed"` result (nothing was created/added) —
    # names which step actually blocked creation, so the UI can show it next
    # to `error_message` instead of the message being the only clue. Never
    # set once a TestAsset exists (a "complete" result is never "blocked" by
    # anything, whatever its `test_result_status`).
    stage: str | None = None


@dataclass
class AddTestCaseResult:
    status: str  # complete | failed | rejected — overall request outcome
    rejection_reason: str | None = None
    error_message: str | None = None
    results: list[TestCaseGenerationResult] = field(default_factory=list)


def _activity_failure_message(exc: BaseException) -> str:
    """`workflow.execute_activity`'s own raised exception is always a bare
    `ActivityError`, whose own `str()` is the content-free "Activity task
    failed" — the real detail is one level down, in `__cause__`: exactly the
    message the failing Activity itself composed (e.g.
    `_prepare_single_test_run_sync`'s "failed to prepare the test project:
    <the real Playwright/auth.setup.ts output>").

    `[FIXED]` This detail used to be returned straight to the user in
    `TestCaseGenerationResult.error_message` (raw RuntimeError/ProgrammingError
    text, full Playwright stdout/stderr, screenshot/trace file paths, SQL —
    exactly the kind of thing a user-facing "Add Test Case" summary should
    never show). It's log-only now — every catch site below logs it via
    `workflow.logger.warning` and returns one of the short, plain-language
    reasons in `_simple_test_result_reason`/its own inline string instead."""
    cause = exc.__cause__
    return str(cause) if cause is not None else str(exc)


def _simple_test_result_reason(status: str) -> str | None:
    """Short, plain-language reason for a `test_result_status` that already
    ran (as opposed to a workflow/activity-level failure — see the catch
    sites below) — replaces the raw `TestResult.error_message` DB column
    (real Playwright stdout/stderr, screenshot/trace paths, stack traces),
    which is exactly the raw detail this feature must never surface. `passed`
    and `not_run` need no explanation — the StatusPill already says it all."""
    if status == "failed":
        return "The test ran, but one or more steps did not produce the expected result."
    if status == "timed_out":
        return "The test did not finish within the allotted time."
    if status == "errored":
        return "The test could not run due to an environment or setup issue."
    return None


# `_create_journey_sync`'s own two known failure causes (add_test_case_activities.py)
# — matched by substring against the raw (log-only) failure message so the
# *actual* reason a Journey couldn't be created reaches the user in plain
# language, not just "something went wrong". Anything else falls back to the
# generic reason below — new failure causes degrade safely instead of ever
# leaking their own raw text.
_NO_MATCHING_PAGES_MARKER = "selected no valid pages"
_NO_DISCOVERY_RUN_MARKER = "no DiscoveryRun yet"


def _journey_creation_failure_reason(raw_message: str) -> str:
    if _NO_MATCHING_PAGES_MARKER in raw_message:
        return (
            "No matching screen was found in the app for this request. Try naming the "
            "specific page or flow you want tested."
        )
    if _NO_DISCOVERY_RUN_MARKER in raw_message:
        return (
            "This app hasn't been crawled yet, so a new journey can't be created. "
            "Run Discovery first."
        )
    return "Could not create the new journey needed for this test case."


@workflow.defn(name="AddTestCaseWorkflow")
class AddTestCaseWorkflow:
    def __init__(self) -> None:
        self._status = "analyzing"
        self._functionality_summary = ""
        self._rejection_reason: str | None = None
        self._scenario_count = 0

    @workflow.query
    def get_status(self) -> AddTestCaseStatus:
        return AddTestCaseStatus(
            status=self._status,
            functionality_summary=self._functionality_summary,
            rejection_reason=self._rejection_reason,
            scenario_count=self._scenario_count,
        )

    async def _create_scenario_safe(
        self,
        application_id: str,
        requirement: ScenarioRequirement,
        user_provided_data: dict[str, str],
    ) -> CreateScenarioResult | TestCaseGenerationResult:
        """`CreateScenarioActivity`, isolated so one Scenario's failure never
        blocks its siblings — same fault-isolation convention
        `SuiteGenerationWorkflow` already uses. A failure here is returned
        already-shaped as a terminal `TestCaseGenerationResult`; success
        returns the raw `CreateScenarioResult` for the caller to route
        (already-exists fast path vs. needs generation)."""
        try:
            created: CreateScenarioResult = await workflow.execute_activity(
                CREATE_SCENARIO_ACTIVITY_NAME,
                CreateScenarioActivityInput(
                    application_id=application_id,
                    requirement=requirement,
                    user_provided_data=user_provided_data,
                ),
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(maximum_attempts=3),
                result_type=CreateScenarioResult,
            )
            created.is_new_scenario = requirement.mode == "new_scenario"
            return created
        except Exception as exc:  # noqa: BLE001 — surfaced in the result, not re-raised
            workflow.logger.warning(
                "AddTestCaseWorkflow: CreateScenarioActivity failed for %r: %s",
                requirement.proposed_scenario_name,
                _activity_failure_message(exc),
            )
            return TestCaseGenerationResult(
                status="failed",
                scenario_name=requirement.proposed_scenario_name or None,
                stage="Scenario match",
                # `[FIXED]` — this is the earliest possible failure point
                # (before CreateJourneyActivity's Scenario even exists), so
                # explicitly saying nothing was added removes the ambiguity
                # "Could not create a scenario" alone left about whether
                # anything landed in the Suite.
                error_message=(
                    "Could not create or match a scenario for this test case — "
                    "nothing was added to the suite."
                ),
            )

    async def _report_existing(self, created: CreateScenarioResult) -> TestCaseGenerationResult:
        """Duplicate Prevention fast path — this Scenario already has a
        current TestAsset (it was matched *because* it already covers the
        request), so it's reported complete immediately using its most
        recent execution result, never regenerated or re-run."""
        try:
            status_result: ReadTestResultStatusResult = await workflow.execute_activity(
                READ_LATEST_TEST_RESULT_ACTIVITY_NAME,
                ReadLatestTestResultActivityInput(test_asset_id=created.existing_test_asset_id),
                task_queue=EXECUTION_TASK_QUEUE,
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=3),
                result_type=ReadTestResultStatusResult,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced in the result, not re-raised
            workflow.logger.warning(
                "AddTestCaseWorkflow: ReadLatestTestResultActivity failed for asset %r: %s",
                created.existing_test_asset_id,
                _activity_failure_message(exc),
            )
            return TestCaseGenerationResult(
                status="complete",
                journey_name=created.journey_name,
                scenario_name=created.scenario_name,
                test_result_status="not_run",
                error_message=(
                    "Attached to its Suite, but its last execution result could not be read."
                ),
                already_existed=True,
            )
        return TestCaseGenerationResult(
            status="complete",
            journey_name=created.journey_name,
            scenario_name=created.scenario_name,
            test_result_status=status_result.status,
            error_message=_simple_test_result_reason(status_result.status),
            already_existed=True,
        )

    async def _generate_and_run(
        self, application_id: str, created: CreateScenarioResult, test_suite_id: str | None
    ) -> TestCaseGenerationResult:
        """The real Playwright Planner -> Generator -> Execute pipeline, for
        a Scenario that genuinely needs it (no current TestAsset yet)."""
        if test_suite_id is None:
            # This Scenario's Journey never got a TestSuite — the shared
            # EnsureTestSuiteActivity call for that Journey (see `run()`)
            # already failed and was reported there; nothing more to do for
            # this Scenario specifically.
            return TestCaseGenerationResult(
                status="failed",
                journey_name=created.journey_name,
                scenario_name=created.scenario_name,
                stage="Test suite setup",
                error_message="Failed to prepare the TestSuite for this Journey.",
            )

        try:
            test_asset_id: str = await workflow.execute_activity(
                PLAYWRIGHT_GENERATION_ACTIVITY_NAME,
                PlaywrightGenerationActivityInput(
                    scenario_id=created.scenario_id, test_suite_id=test_suite_id
                ),
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
                result_type=str,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced in the result, not re-raised
            workflow.logger.warning(
                "AddTestCaseWorkflow: PlaywrightGenerationActivity failed for scenario %r: %s",
                created.scenario_name,
                _activity_failure_message(exc),
            )
            return TestCaseGenerationResult(
                status="failed",
                journey_name=created.journey_name,
                scenario_name=created.scenario_name,
                stage="Code generation",
                error_message="Could not generate the Playwright test for this scenario.",
            )

        # The TestAsset above is already persisted and linked to its
        # TestSuite — "Attach Test Case regardless of PASS/FAIL" already
        # holds from here on, even if execution below fails outright.
        try:
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
            # `[FIXED]` Self-healing — missing entirely from this pipeline
            # before, so a failing NLM-generated test never got the "Auto
            # Healing"/"Self Healed" badges (RunsTab.tsx) a normal-flow
            # TestAsset already gets. `HealTestActivity` is reused
            # unmodified, dispatched exactly the same way
            # `ApplicationTestExecutionWorkflow.run_one` already does for
            # every "Run All Tests" test: called unconditionally right after
            # execution, before FinalizeTestRunActivity — it no-ops on its
            # own for a passed/blocked/budget-exhausted result, so this adds
            # no new gating logic here.
            await workflow.execute_activity(
                HEAL_TEST_ACTIVITY_NAME,
                HealTestActivityInput(
                    application_id=application_id,
                    test_run_id=run_prep.test_run_id,
                    test_result_id=run_prep.test_result_id,
                ),
                task_queue=EXECUTION_TASK_QUEUE,
                start_to_close_timeout=timedelta(minutes=25),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            await workflow.execute_activity(
                FINALIZE_TEST_RUN_ACTIVITY_NAME,
                FinalizeTestRunActivityInput(test_run_id=run_prep.test_run_id),
                task_queue=EXECUTION_TASK_QUEUE,
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            status_result: ReadTestResultStatusResult = await workflow.execute_activity(
                READ_TEST_RESULT_STATUS_ACTIVITY_NAME,
                ReadTestResultStatusActivityInput(test_result_id=run_prep.test_result_id),
                task_queue=EXECUTION_TASK_QUEUE,
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=3),
                result_type=ReadTestResultStatusResult,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced in the result, not re-raised
            workflow.logger.warning(
                "AddTestCaseWorkflow: execution pipeline failed for scenario %r: %s",
                created.scenario_name,
                _activity_failure_message(exc),
            )
            # `[FIXED]` — unlike the catch above (PlaywrightGenerationActivity
            # itself failing, before any TestAsset exists), this one only
            # ever fires *after* the TestAsset was already persisted and
            # linked to its Suite ("Attach Test Case regardless of
            # PASS/FAIL" — see this method's own comment above). Creation
            # succeeded; only the run itself couldn't complete (an infra
            # hiccup preparing/running it, not a test outcome) — `status`
            # stays "complete" (per `TestCaseGenerationResult`'s own
            # docstring on the creation/execution split) with
            # `test_result_status="errored"` carrying the run outcome,
            # exactly the vocabulary the normal Run All Tests flow already
            # uses for the same situation.
            return TestCaseGenerationResult(
                status="complete",
                journey_name=created.journey_name,
                scenario_name=created.scenario_name,
                test_result_status="errored",
                is_new_journey=created.is_new_journey,
                is_new_scenario=created.is_new_scenario,
                error_message="The test case was added successfully, but execution failed.",
            )

        return TestCaseGenerationResult(
            status="complete",
            journey_name=created.journey_name,
            scenario_name=created.scenario_name,
            test_result_status=status_result.status,
            is_new_journey=created.is_new_journey,
            is_new_scenario=created.is_new_scenario,
            error_message=_simple_test_result_reason(status_result.status),
        )

    @workflow.run
    async def run(self, input: AddTestCaseWorkflowInput) -> AddTestCaseResult:
        analysis: PromptAnalysisResult = await workflow.execute_activity(
            ANALYZE_PROMPT_ACTIVITY_NAME,
            AnalyzePromptActivityInput(prompt=input.prompt),
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=PromptAnalysisResult,
        )
        self._functionality_summary = analysis.functionality_summary
        if not analysis.is_relevant:
            # Out-of-Scope Validation — rejected before any Journey/Scenario/
            # TestSuite work happens, no DB write beyond the (existing-table)
            # reads AnalyzePromptActivity itself makes.
            self._status = "rejected"
            self._rejection_reason = analysis.rejection_reason
            return AddTestCaseResult(status="rejected", rejection_reason=analysis.rejection_reason)

        # Identify Journeys / Identify Scenarios — decomposes the prompt into
        # every distinct Scenario it implies (Multiple Test Cases), each
        # already carrying its own Journey/Scenario Decision.
        requirements: list[ScenarioRequirement] = await workflow.execute_activity(
            IDENTIFY_SCENARIOS_ACTIVITY_NAME,
            IdentifyScenariosActivityInput(
                application_id=input.application_id, prompt=input.prompt, prompt_analysis=analysis
            ),
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=list[ScenarioRequirement],
        )
        if not requirements:
            self._status = "failed"
            return AddTestCaseResult(
                status="failed",
                error_message="Could not identify a testable scenario from this request.",
            )
        self._scenario_count = len(requirements)
        self._status = "generating"

        # New Journey grouping — every requirement destined for the same
        # brand-new Journey (same `proposed_journey_name`) must share ONE
        # real Journey, created once here, *before* the per-Scenario
        # fan-out below (see this module's own docstring on why).
        new_journey_groups: dict[str, list[int]] = {}
        for i, req in enumerate(requirements):
            if req.mode == "new_journey":
                key = (
                    req.proposed_journey_name or req.proposed_scenario_name or "untitled"
                ).strip().lower()
                new_journey_groups.setdefault(key, []).append(i)

        results: list[TestCaseGenerationResult] = []
        skip_indices: set[int] = set()
        # Populated below only for requirements whose brand-new Journey
        # actually got created (a failed group is already reported via
        # `skip_indices` above and never reaches Scenario creation at all) —
        # read back after `created_outcomes` to mark each resulting
        # `CreateScenarioResult.is_new_journey`.
        new_journey_indices: set[int] = set()
        if new_journey_groups:

            async def _create_group_journey(indices: list[int]) -> CreateJourneyActivityResult:
                return await workflow.execute_activity(
                    CREATE_JOURNEY_ACTIVITY_NAME,
                    CreateJourneyActivityInput(
                        application_id=input.application_id,
                        requirements=[requirements[i] for i in indices],
                    ),
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                    result_type=CreateJourneyActivityResult,
                )

            group_items = list(new_journey_groups.items())
            group_outcomes = await asyncio.gather(
                *[_create_group_journey(indices) for _, indices in group_items],
                return_exceptions=True,
            )
            for (_key, indices), outcome in zip(group_items, group_outcomes, strict=True):
                if isinstance(outcome, BaseException):
                    raw_message = _activity_failure_message(outcome)
                    workflow.logger.warning(
                        "AddTestCaseWorkflow: CreateJourneyActivity failed for group %r: %s",
                        _key,
                        raw_message,
                    )
                    reason = _journey_creation_failure_reason(raw_message)
                    for i in indices:
                        skip_indices.add(i)
                        results.append(
                            TestCaseGenerationResult(
                                status="failed",
                                scenario_name=requirements[i].proposed_scenario_name or None,
                                stage="Journey creation",
                                error_message=reason,
                            )
                        )
                    continue
                for i in indices:
                    # Now fully resolved to an existing Journey — everything
                    # below never has to know it was ever a "new_journey"
                    # requirement, except `new_journey_indices` (read back
                    # after Scenario creation, purely for display).
                    requirements[i].mode = "new_scenario"
                    requirements[i].journey_id = outcome.journey_id
                    new_journey_indices.add(i)

        # Create/reuse every Scenario first (Duplicate Prevention: also
        # discovers which ones already have a current TestAsset). Indices
        # kept alongside `pending`, aligned by position, purely to read
        # `new_journey_indices` back after the fan-out below.
        pending_indices = [i for i in range(len(requirements)) if i not in skip_indices]
        pending = [requirements[i] for i in pending_indices]
        created_outcomes = await asyncio.gather(
            *[
                self._create_scenario_safe(input.application_id, req, analysis.provided_test_data)
                for req in pending
            ]
        )
        for i, outcome in zip(pending_indices, created_outcomes, strict=True):
            if isinstance(outcome, CreateScenarioResult) and i in new_journey_indices:
                outcome.is_new_journey = True
        created_list = [o for o in created_outcomes if isinstance(o, CreateScenarioResult)]
        results.extend(o for o in created_outcomes if isinstance(o, TestCaseGenerationResult))

        already_done = [c for c in created_list if c.existing_test_asset_id]
        needs_generation = [c for c in created_list if not c.existing_test_asset_id]

        # Ensure TestSuite once per distinct Journey — `[FIXED]` this used to
        # run once *per Scenario*, so several Scenarios sharing one existing
        # Journey each redundantly re-resolved the same TestSuite (see this
        # module's own docstring).
        test_suite_by_journey: dict[str, str] = {}
        if needs_generation:
            distinct_journey_ids = list(dict.fromkeys(c.journey_id for c in needs_generation))

            async def _ensure_one(journey_id: str) -> EnsureTestSuiteActivityResult:
                return await workflow.execute_activity(
                    ENSURE_TEST_SUITE_ACTIVITY_NAME,
                    EnsureTestSuiteActivityInput(journey_id=journey_id),
                    start_to_close_timeout=timedelta(minutes=1),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                    result_type=EnsureTestSuiteActivityResult,
                )

            ensure_outcomes = await asyncio.gather(
                *[_ensure_one(jid) for jid in distinct_journey_ids], return_exceptions=True
            )
            for journey_id, outcome in zip(distinct_journey_ids, ensure_outcomes, strict=True):
                if not isinstance(outcome, BaseException):
                    test_suite_by_journey[journey_id] = outcome.test_suite_id
                # A failed Ensure call simply leaves this Journey's entry
                # missing from `test_suite_by_journey` — `_generate_and_run`
                # reports every Scenario under it as failed individually
                # (fault isolation), the same as any other per-Scenario
                # failure.

        # Independent Generation — the real Playwright Planner -> Generator
        # -> Execute pipeline, only for Scenarios that actually need it;
        # already-existing ones (`_report_existing`) never touch it at all.
        fanout_results = await asyncio.gather(
            *[
                self._generate_and_run(
                    input.application_id, c, test_suite_by_journey.get(c.journey_id)
                )
                for c in needs_generation
            ],
            *[self._report_existing(c) for c in already_done],
        )
        results.extend(fanout_results)

        # Requirement: "When all requested test cases are processed, return
        # a final completed status" — every requirement identified above is
        # accounted for in `results` (generated, matched/reused, or failed)
        # by this point; nothing is left pending, so this is genuinely final.
        self._status = "complete"
        return AddTestCaseResult(status="complete", results=results)


__all__ = [
    "ANALYZE_PROMPT_ACTIVITY_NAME",
    "CREATE_JOURNEY_ACTIVITY_NAME",
    "CREATE_SCENARIO_ACTIVITY_NAME",
    "GENERATION_TASK_QUEUE",
    "IDENTIFY_SCENARIOS_ACTIVITY_NAME",
    "PREPARE_SINGLE_TEST_RUN_ACTIVITY_NAME",
    "READ_LATEST_TEST_RESULT_ACTIVITY_NAME",
    "READ_TEST_RESULT_STATUS_ACTIVITY_NAME",
    "AddTestCaseResult",
    "AddTestCaseStatus",
    "AddTestCaseWorkflow",
    "AddTestCaseWorkflowInput",
    "AnalyzePromptActivityInput",
    "CreateJourneyActivityInput",
    "CreateJourneyActivityResult",
    "CreateScenarioActivityInput",
    "CreateScenarioResult",
    "IdentifyScenariosActivityInput",
    "PrepareSingleTestRunActivityInput",
    "PrepareSingleTestRunActivityResult",
    "PromptAnalysisResult",
    "ReadLatestTestResultActivityInput",
    "ReadTestResultStatusActivityInput",
    "ReadTestResultStatusResult",
    "ScenarioRequirement",
    "TestCaseGenerationResult",
]
