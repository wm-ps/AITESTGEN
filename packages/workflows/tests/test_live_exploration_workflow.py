"""LiveExplorationTestWorkflow — runs against Temporal's in-memory
time-skipping test environment with fake Activities (no Postgres/AI
provider/real browser needed; those are covered by the real Activities' own
tests in apps/workers/generation). Verifies the orchestration shape itself:

- LiveExploreActivity/LiveHealActivity are dispatched on LIVE_EXPLORATION_TASK_QUEUE,
  never the default GENERATION_TASK_QUEUE — a real one spawns an MCP
  subprocess and shouldn't share a concurrency slot with the lightweight
  AI-only activities there.
- On a passing execution, LiveHealActivity is never called at all.
- On a failing execution, LiveHealActivity is called; when it reports
  `healed=True`, ExecuteTestActivity runs again with the new TestAsset id.
- Every internal execute+heal pass's TestRun(s) get discarded
  (DiscardTestRunActivity), never finalized into real history — and the
  workflow's own result never surfaces a per-scenario pass/fail/healed
  outcome (see live_exploration_workflow.py's module docstring for why).
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from workflows import (
    ANALYZE_PROMPT_ACTIVITY_NAME,
    DISCARD_TEST_RUN_ACTIVITY_NAME,
    ENSURE_TEST_SUITE_ACTIVITY_NAME,
    EXECUTE_TEST_ACTIVITY_NAME,
    EXECUTION_TASK_QUEUE,
    FINALIZE_SUITE_GENERATION_ACTIVITY_NAME,
    GENERATION_TASK_QUEUE,
    LIVE_EXPLORATION_TASK_QUEUE,
    LIVE_EXPLORE_ACTIVITY_NAME,
    LIVE_HEAL_ACTIVITY_NAME,
    PLAYWRIGHT_GENERATION_ACTIVITY_NAME,
    PREPARE_SINGLE_TEST_RUN_ACTIVITY_NAME,
    READ_TEST_RESULT_STATUS_ACTIVITY_NAME,
    SCENARIO_GENERATION_ACTIVITY_NAME,
    AnalyzePromptActivityInput,
    DiscardTestRunActivityInput,
    EnsureTestSuiteActivityInput,
    EnsureTestSuiteActivityResult,
    ExecuteTestActivityInput,
    FinalizeSuiteGenerationActivityInput,
    LiveExplorationTestWorkflow,
    LiveExplorationWorkflowInput,
    LiveExploreActivityInput,
    LiveExploreActivityResult,
    LiveHealActivityInput,
    LiveHealActivityResult,
    PlaywrightGenerationActivityInput,
    PrepareSingleTestRunActivityInput,
    PrepareSingleTestRunActivityResult,
    PromptAnalysisResult,
    ReadTestResultStatusActivityInput,
    ReadTestResultStatusResult,
    ScenarioGenerationActivityInput,
)
from workflows.live_exploration_workflow import MAX_VERIFIED_SCENARIOS_PER_JOURNEY

_execute_test_calls: list[str] = []
_heal_calls: list[str] = []
_read_status_results: list[str] = []
_prepare_calls: list[str] = []
_discard_calls: list[str] = []
_finalize_suite_statuses: list[str] = []
_playwright_generation_calls: list[str] = []
_scenario_ids_for_test: list[str] = ["scenario-1"]


@activity.defn(name=ANALYZE_PROMPT_ACTIVITY_NAME)
async def _fake_analyze_prompt(input: AnalyzePromptActivityInput) -> PromptAnalysisResult:
    return PromptAnalysisResult(
        is_relevant=True,
        functionality_summary="Create an MCP connection",
        requested_scenario_counts={"happy": 1, "negative": 1, "edge": 1},
    )


@activity.defn(name=LIVE_EXPLORE_ACTIVITY_NAME)
async def _fake_live_explore(input: LiveExploreActivityInput) -> LiveExploreActivityResult:
    assert input.functionality_summary == "Create an MCP connection"
    return LiveExploreActivityResult(
        discovery_run_id="discovery-run-1",
        page_ids=["page-1", "page-2"],
        goal_satisfied=True,
        journey_id="journey-1",
        journey_name="MCP connection",
    )


@activity.defn(name=SCENARIO_GENERATION_ACTIVITY_NAME)
async def _fake_scenario_generation(input: ScenarioGenerationActivityInput) -> list[str]:
    assert input.journey_id == "journey-1"
    assert input.requested_scenario_counts == {"happy": 1, "negative": 1, "edge": 1}
    return ["scenario-1"]


@activity.defn(name=ENSURE_TEST_SUITE_ACTIVITY_NAME)
async def _fake_ensure_test_suite(
    input: EnsureTestSuiteActivityInput,
) -> EnsureTestSuiteActivityResult:
    return EnsureTestSuiteActivityResult(
        test_suite_id="suite-1", scenario_ids=list(_scenario_ids_for_test)
    )


@activity.defn(name=PLAYWRIGHT_GENERATION_ACTIVITY_NAME)
async def _fake_playwright_generation(input: PlaywrightGenerationActivityInput) -> str:
    _playwright_generation_calls.append(input.scenario_id)
    return f"test-asset-{input.scenario_id}"


@activity.defn(name=FINALIZE_SUITE_GENERATION_ACTIVITY_NAME)
async def _fake_finalize_suite_generation(input: FinalizeSuiteGenerationActivityInput) -> None:
    _finalize_suite_statuses.append(input.status)


@activity.defn(name=PREPARE_SINGLE_TEST_RUN_ACTIVITY_NAME)
async def _fake_prepare_single_test_run(
    input: PrepareSingleTestRunActivityInput,
) -> PrepareSingleTestRunActivityResult:
    # A distinct run/result id per call — a real PrepareSingleTestRunActivity
    # always creates a fresh TestRun/TestResult row, and the workflow must
    # call this again (not reuse the first pair) for a post-heal re-run.
    _prepare_calls.append(input.test_asset_id)
    index = len(_prepare_calls)
    return PrepareSingleTestRunActivityResult(
        test_run_id=f"run-{index}", test_result_id=f"result-{index}"
    )


@activity.defn(name=EXECUTE_TEST_ACTIVITY_NAME)
async def _fake_execute_test(input: ExecuteTestActivityInput) -> str:
    _execute_test_calls.append(input.test_asset_id)
    return input.test_result_id


@activity.defn(name=DISCARD_TEST_RUN_ACTIVITY_NAME)
async def _fake_discard_test_run(input: DiscardTestRunActivityInput) -> None:
    _discard_calls.append(input.test_run_id)


@activity.defn(name=READ_TEST_RESULT_STATUS_ACTIVITY_NAME)
async def _fake_read_test_result_status(
    input: ReadTestResultStatusActivityInput,
) -> ReadTestResultStatusResult:
    status = _read_status_results[min(len(_execute_test_calls) - 1, len(_read_status_results) - 1)]
    return ReadTestResultStatusResult(status=status)


@activity.defn(name=LIVE_HEAL_ACTIVITY_NAME)
async def _fake_live_heal(input: LiveHealActivityInput) -> LiveHealActivityResult:
    _heal_calls.append(input.test_result_id)
    return LiveHealActivityResult(healed=True, test_asset_id="test-asset-scenario-1-healed")


async def _run(env: WorkflowEnvironment) -> object:
    async with (
        Worker(
            env.client,
            task_queue=GENERATION_TASK_QUEUE,
            workflows=[LiveExplorationTestWorkflow],
            activities=[
                _fake_analyze_prompt,
                _fake_scenario_generation,
                _fake_ensure_test_suite,
                _fake_playwright_generation,
                _fake_finalize_suite_generation,
            ],
        ),
        Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[],
            activities=[
                _fake_prepare_single_test_run,
                _fake_execute_test,
                _fake_discard_test_run,
                _fake_read_test_result_status,
            ],
        ),
        Worker(
            env.client,
            task_queue=LIVE_EXPLORATION_TASK_QUEUE,
            workflows=[],
            activities=[_fake_live_explore, _fake_live_heal],
        ),
    ):
        return await env.client.execute_workflow(
            LiveExplorationTestWorkflow.run,
            LiveExplorationWorkflowInput(
                application_id="app-1", prompt="Create a new MCP connection for a tenant."
            ),
            id=f"live-exploration-test-{uuid.uuid4()}",
            task_queue=GENERATION_TASK_QUEUE,
        )


@pytest.mark.asyncio
async def test_no_heal_when_execution_passes_first_try() -> None:
    _execute_test_calls.clear()
    _heal_calls.clear()
    _prepare_calls.clear()
    _discard_calls.clear()
    _finalize_suite_statuses.clear()
    _playwright_generation_calls.clear()
    _scenario_ids_for_test[:] = ["scenario-1"]
    _read_status_results[:] = ["passed"]

    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env)

    assert result.status == "complete"
    assert result.journey_id == "journey-1"
    assert result.journey_name == "MCP connection"
    assert _heal_calls == []
    assert _execute_test_calls == ["test-asset-scenario-1"]
    assert _prepare_calls == ["test-asset-scenario-1"]
    # The only TestRun this scenario touched is discarded, not finalized —
    # a passing internal check leaves no history behind either.
    assert _discard_calls == ["run-1"]
    assert _finalize_suite_statuses == ["complete"]


@pytest.mark.asyncio
async def test_heals_and_re_executes_on_a_failing_run() -> None:
    _execute_test_calls.clear()
    _heal_calls.clear()
    _prepare_calls.clear()
    _discard_calls.clear()
    _finalize_suite_statuses.clear()
    _playwright_generation_calls.clear()
    _scenario_ids_for_test[:] = ["scenario-1"]
    _read_status_results[:] = ["failed", "passed"]

    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env)

    assert result.status == "complete"
    assert result.journey_id == "journey-1"
    assert result.journey_name == "MCP connection"

    # LiveHealActivity ran once (after the first failing execution), and
    # ExecuteTestActivity ran a second time with the HEALED test_asset_id.
    assert _heal_calls == ["result-1"]
    assert _execute_test_calls == ["test-asset-scenario-1", "test-asset-scenario-1-healed"]

    # The post-heal re-run got its OWN fresh TestRun/TestResult (run-2),
    # never a replay of run-1's already-terminal one.
    assert _prepare_calls == ["test-asset-scenario-1", "test-asset-scenario-1-healed"]
    # Both the original, failed TestRun and the healed re-run's TestRun are
    # discarded — neither is finalized into real, user-visible history,
    # regardless of the healed run's own final outcome.
    assert _discard_calls == ["run-1", "run-2"]
    # Still "complete" — a healed-or-not internal check no longer decides
    # test_suite.status; every scenario got a TestAsset either way.
    assert _finalize_suite_statuses == ["complete"]


@pytest.mark.asyncio
async def test_only_the_capped_number_of_scenarios_get_execute_and_heal_verification() -> None:
    """`[ADDED]` MAX_VERIFIED_SCENARIOS_PER_JOURNEY bounds how many scenarios
    in a journey get the internal execute+heal pass — every scenario still
    gets its Playwright code generated regardless (the unconditional loop
    just before `_generate_and_verify_one`'s own loop); only the extra
    execute+heal verification is skipped past the cap, since each pass takes
    real minutes and an uncapped journey can otherwise take tens of minutes."""
    _execute_test_calls.clear()
    _heal_calls.clear()
    _prepare_calls.clear()
    _discard_calls.clear()
    _finalize_suite_statuses.clear()
    _playwright_generation_calls.clear()
    all_scenario_ids = [f"scenario-{i}" for i in range(1, 8)]
    _scenario_ids_for_test[:] = all_scenario_ids
    _read_status_results[:] = ["passed"]

    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env)

    assert result.status == "complete"
    # Every scenario gets its Playwright code generated...
    assert set(all_scenario_ids) <= set(_playwright_generation_calls)
    # ...but only the first MAX_VERIFIED_SCENARIOS_PER_JOURNEY are executed
    # (and could be healed) at all.
    verified_ids = [
        f"test-asset-{sid}" for sid in all_scenario_ids[:MAX_VERIFIED_SCENARIOS_PER_JOURNEY]
    ]
    assert _execute_test_calls == verified_ids
    assert _prepare_calls == verified_ids
    assert len(_discard_calls) == MAX_VERIFIED_SCENARIOS_PER_JOURNEY
    assert _finalize_suite_statuses == ["complete"]
