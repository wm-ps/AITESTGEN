"""AddTestCaseWorkflow — runs against Temporal's in-memory time-skipping test
environment with fake Activities (no Postgres/AI provider needed; those are
covered by the real Activities' own tests in apps/workers/generation and
apps/workers/execution). Verifies the orchestration shape itself:

- Everything is prompt-based — no separate test-data input and no "needs
  more test data" pause. `AnalyzePromptActivity` extracts any concrete value
  the user stated directly in their prompt, threaded straight into
  `CreateScenarioActivity`.
- Multiple Test Cases: a single prompt can decompose into several Scenarios,
  each independently generated, executed, and reported (Independent
  Generation) — one Scenario's failure never blocks its siblings.
- New Journey grouping: two Scenarios that both need the same brand-new
  Journey share exactly one real Journey — `CreateJourneyActivity` runs once
  per distinct group, not once per Scenario.
- `[FIXED]` A Scenario matched to an existing one that already has a current
  TestAsset is reported complete immediately, using its latest execution
  result — PlaywrightGenerationActivity and a fresh execution are never
  triggered for it (this used to make a multi-Scenario request take several
  times longer than necessary, reading as "stuck").
- `[FIXED]` `EnsureTestSuiteActivity` runs at most once per *distinct*
  Journey among the Scenarios that actually need generation, not once per
  Scenario.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from workflows import (
    ANALYZE_PROMPT_ACTIVITY_NAME,
    CREATE_JOURNEY_ACTIVITY_NAME,
    CREATE_SCENARIO_ACTIVITY_NAME,
    ENSURE_TEST_SUITE_ACTIVITY_NAME,
    EXECUTE_TEST_ACTIVITY_NAME,
    EXECUTION_TASK_QUEUE,
    FINALIZE_TEST_RUN_ACTIVITY_NAME,
    GENERATION_TASK_QUEUE,
    HEAL_TEST_ACTIVITY_NAME,
    IDENTIFY_SCENARIOS_ACTIVITY_NAME,
    PLAYWRIGHT_GENERATION_ACTIVITY_NAME,
    PREPARE_SINGLE_TEST_RUN_ACTIVITY_NAME,
    READ_LATEST_TEST_RESULT_ACTIVITY_NAME,
    READ_TEST_RESULT_STATUS_ACTIVITY_NAME,
    AddTestCaseWorkflow,
    AddTestCaseWorkflowInput,
    AnalyzePromptActivityInput,
    CreateJourneyActivityInput,
    CreateJourneyActivityResult,
    CreateScenarioActivityInput,
    CreateScenarioResult,
    EnsureTestSuiteActivityInput,
    EnsureTestSuiteActivityResult,
    ExecuteTestActivityInput,
    FinalizeTestRunActivityInput,
    HealTestActivityInput,
    IdentifyScenariosActivityInput,
    PlaywrightGenerationActivityInput,
    PrepareSingleTestRunActivityInput,
    PrepareSingleTestRunActivityResult,
    PromptAnalysisResult,
    ReadLatestTestResultActivityInput,
    ReadTestResultStatusActivityInput,
    ReadTestResultStatusResult,
    ScenarioRequirement,
)


@activity.defn(name=ANALYZE_PROMPT_ACTIVITY_NAME)
async def _fake_analyze_prompt(input: AnalyzePromptActivityInput) -> PromptAnalysisResult:
    return PromptAnalysisResult(
        is_relevant=True,
        functionality_summary="Verify sign-in and sign-out both work",
        actions=["sign in", "sign out"],
        expected_result="each action succeeds",
        provided_test_data={"password": "Secret123!"},
    )


@activity.defn(name=IDENTIFY_SCENARIOS_ACTIVITY_NAME)
async def _fake_identify_scenarios(
    input: IdentifyScenariosActivityInput,
) -> list[ScenarioRequirement]:
    # Two Scenarios: one reuses an existing Scenario, one needs a brand-new
    # Journey — exercises both the reuse path and the new-journey-creation
    # path in a single run (Multiple Test Cases).
    return [
        ScenarioRequirement(
            mode="reuse_scenario",
            journey_id="journey-existing",
            scenario_id="scenario-existing",
            proposed_scenario_name="Sign in with valid credentials",
            functionality_summary="Sign in",
            actions=["sign in"],
            expected_result="the user reaches the dashboard",
        ),
        ScenarioRequirement(
            mode="new_journey",
            proposed_journey_name="Sign out",
            proposed_scenario_name="Sign out from the dashboard",
            functionality_summary="Sign out",
            actions=["sign out"],
            expected_result="the user is returned to the login page",
        ),
    ]


_create_journey_call_count = {"n": 0}


@activity.defn(name=CREATE_JOURNEY_ACTIVITY_NAME)
async def _fake_create_journey(input: CreateJourneyActivityInput) -> CreateJourneyActivityResult:
    _create_journey_call_count["n"] += 1
    return CreateJourneyActivityResult(journey_id="journey-new-signout", journey_name="Sign out")


_create_scenario_calls: list[CreateScenarioActivityInput] = []


@activity.defn(name=CREATE_SCENARIO_ACTIVITY_NAME)
async def _fake_create_scenario(input: CreateScenarioActivityInput) -> CreateScenarioResult:
    _create_scenario_calls.append(input)
    if input.requirement.mode == "reuse_scenario":
        # This existing Scenario already has a current TestAsset — the
        # common case for a genuine reuse match.
        return CreateScenarioResult(
            journey_id="journey-existing",
            scenario_id="scenario-existing",
            journey_name="Sign in",
            scenario_name="Sign in with valid credentials",
            existing_test_asset_id="asset-existing",
        )
    assert input.requirement.mode == "new_scenario"
    assert input.requirement.journey_id == "journey-new-signout"
    return CreateScenarioResult(
        journey_id=input.requirement.journey_id,
        scenario_id="scenario-new-signout",
        journey_name="Sign out",
        scenario_name="Sign out from the dashboard",
    )


_ensure_test_suite_calls: list[str] = []


@activity.defn(name=ENSURE_TEST_SUITE_ACTIVITY_NAME)
async def _fake_ensure_test_suite(
    input: EnsureTestSuiteActivityInput,
) -> EnsureTestSuiteActivityResult:
    _ensure_test_suite_calls.append(input.journey_id)
    return EnsureTestSuiteActivityResult(
        test_suite_id=f"suite-{input.journey_id}", scenario_ids=["ignored"]
    )


@activity.defn(name=PLAYWRIGHT_GENERATION_ACTIVITY_NAME)
async def _fake_playwright_generation(input: PlaywrightGenerationActivityInput) -> str:
    return f"test-asset-{input.scenario_id}"


@activity.defn(name=PREPARE_SINGLE_TEST_RUN_ACTIVITY_NAME)
async def _fake_prepare_single_test_run(
    input: PrepareSingleTestRunActivityInput,
) -> PrepareSingleTestRunActivityResult:
    return PrepareSingleTestRunActivityResult(
        test_run_id=f"run-{input.test_asset_id}", test_result_id=f"result-{input.test_asset_id}"
    )


@activity.defn(name=EXECUTE_TEST_ACTIVITY_NAME)
async def _fake_execute_test(input: ExecuteTestActivityInput) -> str:
    return input.test_result_id


@activity.defn(name=FINALIZE_TEST_RUN_ACTIVITY_NAME)
async def _fake_finalize_test_run(input: FinalizeTestRunActivityInput) -> None:
    return None


# `[FIXED]` — the real workflow now dispatches HealTestActivity unconditionally
# after every ExecuteTestActivity, same as ApplicationTestExecutionWorkflow's
# normal Run-All-Tests path, so the "Auto Healing"/"Self Healed" badges
# (RunsTab.tsx) also populate for NLM-generated test cases. A no-op fake here
# is enough — the real activity's own eligibility/no-op behavior is already
# covered by execution_worker's own tests.
@activity.defn(name=HEAL_TEST_ACTIVITY_NAME)
async def _fake_heal_test(input: HealTestActivityInput) -> None:
    return None


@activity.defn(name=READ_TEST_RESULT_STATUS_ACTIVITY_NAME)
async def _fake_read_test_result_status(
    input: ReadTestResultStatusActivityInput,
) -> ReadTestResultStatusResult:
    return ReadTestResultStatusResult(status="failed", error_message="assertion mismatch")


@activity.defn(name=READ_LATEST_TEST_RESULT_ACTIVITY_NAME)
async def _fake_read_latest_test_result(
    input: ReadLatestTestResultActivityInput,
) -> ReadTestResultStatusResult:
    assert input.test_asset_id == "asset-existing"
    return ReadTestResultStatusResult(status="passed")


@pytest.mark.asyncio
async def test_add_test_case_workflow_generates_multiple_independent_test_cases() -> None:
    _create_journey_call_count["n"] = 0
    _create_scenario_calls.clear()
    _ensure_test_suite_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=GENERATION_TASK_QUEUE,
                workflows=[AddTestCaseWorkflow],
                activities=[
                    _fake_analyze_prompt,
                    _fake_identify_scenarios,
                    _fake_create_journey,
                    _fake_create_scenario,
                    _fake_ensure_test_suite,
                    _fake_playwright_generation,
                ],
            ),
            Worker(
                env.client,
                task_queue=EXECUTION_TASK_QUEUE,
                workflows=[],
                activities=[
                    _fake_prepare_single_test_run,
                    _fake_execute_test,
                    _fake_finalize_test_run,
                    _fake_read_test_result_status,
                    _fake_read_latest_test_result,
                    _fake_heal_test,
                ],
            ),
        ):
            result = await env.client.execute_workflow(
                AddTestCaseWorkflow.run,
                AddTestCaseWorkflowInput(
                    application_id="app-1",
                    prompt="verify that sign in and sign out both work, using password Secret123!",
                ),
                id=f"add-test-case-test-{uuid.uuid4()}",
                task_queue=GENERATION_TASK_QUEUE,
            )

    assert result.status == "complete"
    assert len(result.results) == 2
    by_scenario = {r.scenario_name: r for r in result.results}

    # Sign-in already had a TestAsset — reported via its latest result,
    # PlaywrightGenerationActivity/execution never touched.
    sign_in = by_scenario["Sign in with valid credentials"]
    assert sign_in.status == "complete"
    assert sign_in.already_existed is True
    assert sign_in.test_result_status == "passed"
    assert sign_in.is_new_journey is False
    assert sign_in.is_new_scenario is False

    # Sign-out is genuinely new — goes through real generation + execution.
    # `status` stays "complete" even though the test itself failed — per
    # `TestCaseGenerationResult`'s own docstring, `status` answers only
    # "was it created/added", `test_result_status` answers "did it pass".
    sign_out = by_scenario["Sign out from the dashboard"]
    assert sign_out.status == "complete"
    assert sign_out.already_existed is False
    assert sign_out.journey_name == "Sign out"
    assert sign_out.test_result_status == "failed"
    # It needed a brand-new Journey ("Sign out" didn't exist before this
    # request) — `is_new_journey` says so. `is_new_scenario` is also True
    # here (the requirement's mode was rewritten "new_journey" ->
    # "new_scenario" once its Journey was created — see `run()`'s own
    # comment) but the UI's priority order checks `is_new_journey` first,
    # so this doesn't change what's displayed.
    assert sign_out.is_new_journey is True
    assert sign_out.is_new_scenario is True

    # CreateJourneyActivity ran exactly once for the "Sign out" group.
    assert _create_journey_call_count["n"] == 1
    assert len(_create_scenario_calls) == 2
    # EnsureTestSuiteActivity only ever runs for Scenarios that actually
    # need generation — the already-existing sign-in Scenario never
    # triggers it at all.
    assert _ensure_test_suite_calls == ["journey-new-signout"]


@pytest.mark.asyncio
async def test_add_test_case_workflow_dedupes_ensure_test_suite_per_journey() -> None:
    """Several Scenarios matched to the SAME existing Journey must resolve
    its TestSuite exactly once, not once per Scenario — the exact bug
    reported live with a 6-Scenario prompt."""
    _ensure_test_suite_calls.clear()

    @activity.defn(name=IDENTIFY_SCENARIOS_ACTIVITY_NAME)
    async def _fake_identify_three_new_under_one_journey(
        input: IdentifyScenariosActivityInput,
    ) -> list[ScenarioRequirement]:
        return [
            ScenarioRequirement(
                mode="new_scenario",
                journey_id="journey-shared",
                proposed_scenario_name=f"Scenario {i}",
                functionality_summary=f"Functionality {i}",
            )
            for i in range(3)
        ]

    call_count = {"n": 0}

    @activity.defn(name=CREATE_SCENARIO_ACTIVITY_NAME)
    async def _fake_create_scenario_shared_journey(
        input: CreateScenarioActivityInput,
    ) -> CreateScenarioResult:
        call_count["n"] += 1
        return CreateScenarioResult(
            journey_id="journey-shared",
            scenario_id=f"scenario-{call_count['n']}",
            journey_name="Shared Journey",
            scenario_name=input.requirement.proposed_scenario_name,
        )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=GENERATION_TASK_QUEUE,
                workflows=[AddTestCaseWorkflow],
                activities=[
                    _fake_analyze_prompt,
                    _fake_identify_three_new_under_one_journey,
                    _fake_create_scenario_shared_journey,
                    _fake_ensure_test_suite,
                    _fake_playwright_generation,
                ],
            ),
            Worker(
                env.client,
                task_queue=EXECUTION_TASK_QUEUE,
                workflows=[],
                activities=[
                    _fake_prepare_single_test_run,
                    _fake_execute_test,
                    _fake_finalize_test_run,
                    _fake_read_test_result_status,
                    _fake_heal_test,
                ],
            ),
        ):
            result = await env.client.execute_workflow(
                AddTestCaseWorkflow.run,
                AddTestCaseWorkflowInput(application_id="app-1", prompt="test three things"),
                id=f"add-test-case-test-{uuid.uuid4()}",
                task_queue=GENERATION_TASK_QUEUE,
            )

    assert result.status == "complete"
    assert len(result.results) == 3
    assert all(r.status == "complete" for r in result.results)
    # New Scenarios under an EXISTING Journey (not a new one) — Case 3 of
    # the NLM Matching and Creation Rules: `is_new_scenario` true,
    # `is_new_journey` false, distinct from both the reuse case and the
    # new-Journey case covered elsewhere in this file.
    assert all(r.is_new_scenario is True for r in result.results)
    assert all(r.is_new_journey is False for r in result.results)
    # The one and only distinct Journey among all three Scenarios.
    assert _ensure_test_suite_calls == ["journey-shared"]


@pytest.mark.asyncio
async def test_add_test_case_workflow_reports_when_everything_already_exists() -> None:
    """Requirement: an appropriate result when every requested test case
    turns out to already exist — no generation, no execution, still a
    genuinely "complete" result for each."""

    @activity.defn(name=IDENTIFY_SCENARIOS_ACTIVITY_NAME)
    async def _fake_identify_all_reuse(
        input: IdentifyScenariosActivityInput,
    ) -> list[ScenarioRequirement]:
        return [
            ScenarioRequirement(
                mode="reuse_scenario",
                journey_id="journey-a",
                scenario_id="scenario-a",
                proposed_scenario_name="Scenario A",
            )
        ]

    @activity.defn(name=CREATE_SCENARIO_ACTIVITY_NAME)
    async def _fake_create_scenario_reuse(
        input: CreateScenarioActivityInput,
    ) -> CreateScenarioResult:
        return CreateScenarioResult(
            journey_id="journey-a",
            scenario_id="scenario-a",
            journey_name="Journey A",
            scenario_name="Scenario A",
            existing_test_asset_id="asset-a",
        )

    @activity.defn(name=READ_LATEST_TEST_RESULT_ACTIVITY_NAME)
    async def _fake_read_latest_passed(
        input: ReadLatestTestResultActivityInput,
    ) -> ReadTestResultStatusResult:
        return ReadTestResultStatusResult(status="passed")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=GENERATION_TASK_QUEUE,
                workflows=[AddTestCaseWorkflow],
                activities=[
                    _fake_analyze_prompt,
                    _fake_identify_all_reuse,
                    _fake_create_scenario_reuse,
                ],
            ),
            Worker(
                env.client,
                task_queue=EXECUTION_TASK_QUEUE,
                workflows=[],
                activities=[_fake_read_latest_passed],
            ),
        ):
            result = await env.client.execute_workflow(
                AddTestCaseWorkflow.run,
                AddTestCaseWorkflowInput(application_id="app-1", prompt="test A again"),
                id=f"add-test-case-test-{uuid.uuid4()}",
                task_queue=GENERATION_TASK_QUEUE,
            )

    assert result.status == "complete"
    assert len(result.results) == 1
    assert result.results[0].status == "complete"
    assert result.results[0].already_existed is True
    assert result.results[0].test_result_status == "passed"


@pytest.mark.asyncio
async def test_add_test_case_workflow_rejects_out_of_scope_prompt() -> None:
    @activity.defn(name=ANALYZE_PROMPT_ACTIVITY_NAME)
    async def _fake_analyze_prompt_rejects(
        input: AnalyzePromptActivityInput,
    ) -> PromptAnalysisResult:
        return PromptAnalysisResult(is_relevant=False, rejection_reason="not a test case request")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=GENERATION_TASK_QUEUE,
            workflows=[AddTestCaseWorkflow],
            activities=[_fake_analyze_prompt_rejects],
        ):
            result = await env.client.execute_workflow(
                AddTestCaseWorkflow.run,
                AddTestCaseWorkflowInput(application_id="app-1", prompt="write me a poem"),
                id=f"add-test-case-test-{uuid.uuid4()}",
                task_queue=GENERATION_TASK_QUEUE,
            )

    assert result.status == "rejected"
    assert result.rejection_reason == "not a test case request"
    assert result.results == []


@pytest.mark.asyncio
async def test_add_test_case_workflow_isolates_one_scenarios_failure_from_the_other() -> None:
    """One Scenario's CreateScenarioActivity failure must not take down its
    sibling — fault isolation, same convention SuiteGenerationWorkflow
    already uses for its own per-Scenario fan-out."""

    @activity.defn(name=IDENTIFY_SCENARIOS_ACTIVITY_NAME)
    async def _fake_identify_two_reuse(
        input: IdentifyScenariosActivityInput,
    ) -> list[ScenarioRequirement]:
        return [
            ScenarioRequirement(
                mode="reuse_scenario",
                journey_id="journey-a",
                scenario_id="scenario-a",
                proposed_scenario_name="Scenario A",
            ),
            ScenarioRequirement(
                mode="reuse_scenario",
                journey_id="journey-b",
                scenario_id="scenario-b",
                proposed_scenario_name="Scenario B",
            ),
        ]

    @activity.defn(name=CREATE_SCENARIO_ACTIVITY_NAME)
    async def _fake_create_scenario_one_fails(
        input: CreateScenarioActivityInput,
    ) -> CreateScenarioResult:
        if input.requirement.scenario_id == "scenario-a":
            raise RuntimeError("simulated failure for scenario-a")
        return CreateScenarioResult(
            journey_id="journey-b",
            scenario_id="scenario-b",
            journey_name="Journey B",
            scenario_name="Scenario B",
            existing_test_asset_id="asset-b",
        )

    @activity.defn(name=READ_LATEST_TEST_RESULT_ACTIVITY_NAME)
    async def _fake_read_latest_b(
        input: ReadLatestTestResultActivityInput,
    ) -> ReadTestResultStatusResult:
        return ReadTestResultStatusResult(status="passed")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=GENERATION_TASK_QUEUE,
                workflows=[AddTestCaseWorkflow],
                activities=[
                    _fake_analyze_prompt,
                    _fake_identify_two_reuse,
                    _fake_create_scenario_one_fails,
                ],
            ),
            Worker(
                env.client,
                task_queue=EXECUTION_TASK_QUEUE,
                workflows=[],
                activities=[_fake_read_latest_b],
            ),
        ):
            result = await env.client.execute_workflow(
                AddTestCaseWorkflow.run,
                AddTestCaseWorkflowInput(application_id="app-1", prompt="test A and B"),
                id=f"add-test-case-test-{uuid.uuid4()}",
                task_queue=GENERATION_TASK_QUEUE,
            )

    assert result.status == "complete"
    assert len(result.results) == 2
    by_scenario = {r.scenario_name: r for r in result.results}
    assert by_scenario["Scenario A"].status == "failed"
    # `[FIXED]` — the raw activity-failure cause ("simulated failure for
    # scenario-a") must never reach this user-facing result; only a short,
    # plain-language reason does (the raw detail still reaches
    # workflow.logger.warning, not asserted here — that's log plumbing, not
    # this workflow's own contract).
    assert by_scenario["Scenario A"].error_message == (
        "Could not create or match a scenario for this test case — nothing was added to the suite."
    )
    assert "simulated failure" not in (by_scenario["Scenario A"].error_message or "")
    assert by_scenario["Scenario B"].status == "complete"
    assert by_scenario["Scenario B"].already_existed is True


@pytest.mark.asyncio
async def test_add_test_case_workflow_reports_complete_when_only_execution_fails() -> None:
    """`[FIXED]` Creation and execution are two different questions — a
    Scenario whose TestAsset was genuinely generated and attached to its
    Suite must stay `status="complete"` even when the run itself can't
    complete (an infra hiccup preparing/executing it, not a test outcome).
    It used to report `status="failed"`, which told the user their test case
    didn't exist when it actually did."""

    @activity.defn(name=IDENTIFY_SCENARIOS_ACTIVITY_NAME)
    async def _fake_identify_one_new(
        input: IdentifyScenariosActivityInput,
    ) -> list[ScenarioRequirement]:
        return [
            ScenarioRequirement(
                mode="new_scenario",
                journey_id="journey-existing",
                proposed_scenario_name="Apply for a loan",
            )
        ]

    @activity.defn(name=CREATE_SCENARIO_ACTIVITY_NAME)
    async def _fake_create_scenario_new(
        input: CreateScenarioActivityInput,
    ) -> CreateScenarioResult:
        return CreateScenarioResult(
            journey_id="journey-existing",
            scenario_id="scenario-new",
            journey_name="Loans",
            scenario_name="Apply for a loan",
        )

    @activity.defn(name=PREPARE_SINGLE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_prepare_fails(
        input: PrepareSingleTestRunActivityInput,
    ) -> PrepareSingleTestRunActivityResult:
        # Mirrors `_prepare_single_test_run_sync`'s own real behavior: the
        # TestResult it already wrote is "errored" in the DB, but the
        # Activity still re-raises so the workflow's try/except handles it —
        # see that function's own comment.
        raise RuntimeError("failed to prepare the test project: auth.setup.ts failed")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=GENERATION_TASK_QUEUE,
                workflows=[AddTestCaseWorkflow],
                activities=[
                    _fake_analyze_prompt,
                    _fake_identify_one_new,
                    _fake_create_scenario_new,
                    _fake_ensure_test_suite,
                    _fake_playwright_generation,
                ],
            ),
            Worker(
                env.client,
                task_queue=EXECUTION_TASK_QUEUE,
                workflows=[],
                activities=[_fake_prepare_fails],
            ),
        ):
            result = await env.client.execute_workflow(
                AddTestCaseWorkflow.run,
                AddTestCaseWorkflowInput(application_id="app-1", prompt="test applying for a loan"),
                id=f"add-test-case-test-{uuid.uuid4()}",
                task_queue=GENERATION_TASK_QUEUE,
            )

    assert result.status == "complete"
    assert len(result.results) == 1
    only = result.results[0]
    # The TestAsset was generated and linked to its Suite before this
    # failure — `status` must say so, not "failed".
    assert only.status == "complete"
    assert only.scenario_name == "Apply for a loan"
    assert only.journey_name == "Loans"
    assert only.test_result_status == "errored"
    assert only.error_message == "The test case was added successfully, but execution failed."
    assert "auth.setup.ts" not in (only.error_message or "")
