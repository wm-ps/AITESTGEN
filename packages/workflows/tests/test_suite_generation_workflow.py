"""SuiteGenerationWorkflow (Story 4.2) — runs against Temporal's in-memory
time-skipping test environment with fake Activities (no Postgres/AI provider
needed; those are covered by the real Activities' own tests in
apps/workers/generation). Verifies the orchestration shape itself: one
EnsureTestSuiteActivity call, then a fan-out of one PlaywrightGenerationActivity
call per Scenario, with one failure not failing the whole dispatch.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from workflows import (
    ENSURE_TEST_SUITE_ACTIVITY_NAME,
    GENERATION_TASK_QUEUE,
    PLAYWRIGHT_GENERATION_ACTIVITY_NAME,
    EnsureTestSuiteActivityInput,
    EnsureTestSuiteActivityResult,
    PlaywrightGenerationActivityInput,
    SuiteGenerationWorkflow,
)


@activity.defn(name=ENSURE_TEST_SUITE_ACTIVITY_NAME)
async def _fake_ensure_test_suite(input: EnsureTestSuiteActivityInput) -> EnsureTestSuiteActivityResult:
    return EnsureTestSuiteActivityResult(
        test_suite_id="test-suite-1", scenario_ids=["scenario-1", "scenario-2", "scenario-3"]
    )


@activity.defn(name=PLAYWRIGHT_GENERATION_ACTIVITY_NAME)
async def _fake_playwright_generation(input: PlaywrightGenerationActivityInput) -> str:
    if input.scenario_id == "scenario-2":
        raise RuntimeError("simulated AI failure for scenario-2")
    return f"test-asset-for-{input.scenario_id}"


@pytest.mark.asyncio
async def test_suite_generation_workflow_fans_out_one_call_per_scenario() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=GENERATION_TASK_QUEUE,
            workflows=[SuiteGenerationWorkflow],
            activities=[_fake_ensure_test_suite, _fake_playwright_generation],
        ):
            result = await env.client.execute_workflow(
                SuiteGenerationWorkflow.run,
                "journey-1",
                id=f"suite-test-{uuid.uuid4()}",
                task_queue=GENERATION_TASK_QUEUE,
            )

    # scenario-2's Activity failed — its TestAsset is missing, but
    # scenario-1/scenario-3's still made it through (fault isolation).
    assert sorted(result) == ["test-asset-for-scenario-1", "test-asset-for-scenario-3"]


@pytest.mark.asyncio
async def test_suite_generation_workflow_recovers_a_scenario_in_a_later_wave() -> None:
    # scenario-2 fails its whole first wave (3 Activity attempts, matching
    # the real retry_policy) — a transient AI-proxy timeout under real fan-out
    # concurrency, not a permanent error. A single wave would drop it forever
    # (observed live: stuck at 107/159 with no way to resume). The Workflow
    # must re-wave it and pick up the TestAsset once the underlying call
    # starts succeeding again.
    call_counts: dict[str, int] = {}

    @activity.defn(name=PLAYWRIGHT_GENERATION_ACTIVITY_NAME)
    async def _fake_playwright_generation_recovers_later(
        input: PlaywrightGenerationActivityInput,
    ) -> str:
        call_counts[input.scenario_id] = call_counts.get(input.scenario_id, 0) + 1
        if input.scenario_id == "scenario-2" and call_counts[input.scenario_id] <= 3:
            raise RuntimeError("simulated transient failure — exhausts wave 1's 3 attempts")
        return f"test-asset-for-{input.scenario_id}"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=GENERATION_TASK_QUEUE,
            workflows=[SuiteGenerationWorkflow],
            activities=[_fake_ensure_test_suite, _fake_playwright_generation_recovers_later],
        ):
            result = await env.client.execute_workflow(
                SuiteGenerationWorkflow.run,
                "journey-1",
                id=f"suite-test-{uuid.uuid4()}",
                task_queue=GENERATION_TASK_QUEUE,
            )

    assert sorted(result) == [
        "test-asset-for-scenario-1",
        "test-asset-for-scenario-2",
        "test-asset-for-scenario-3",
    ]
    # 3 failed attempts (wave 1, exhausting retry_policy) + 1 successful
    # attempt (wave 2) — proves the recovery came from a second wave, not
    # from retry_policy alone.
    assert call_counts["scenario-2"] == 4


@pytest.mark.asyncio
async def test_suite_generation_workflow_threads_grounding_feedback_into_next_wave_input() -> None:
    """Locator-grounding hardening: a Scenario whose Activity attempt raises
    `ValueError("GROUNDING_VIOLATION: ...")` (generation_worker.
    playwright_generation_activity's in-process retries exhausted) must have
    that specific feedback carried into its next-wave input — a blind,
    unchanged retry would just reproduce the same rejected locator."""
    received_feedback: dict[str, list[str | None]] = {}

    @activity.defn(name=PLAYWRIGHT_GENERATION_ACTIVITY_NAME)
    async def _fake_playwright_generation_raises_grounding_violation_once(
        input: PlaywrightGenerationActivityInput,
    ) -> str:
        received_feedback.setdefault(input.scenario_id, []).append(input.grounding_feedback)
        if input.scenario_id == "scenario-2" and input.grounding_feedback is None:
            raise ValueError(
                "GROUNDING_VIOLATION: - page.locator('#invented') — '#invented' does not "
                "match any locator actually discovered on this application during crawling."
            )
        return f"test-asset-for-{input.scenario_id}"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=GENERATION_TASK_QUEUE,
            workflows=[SuiteGenerationWorkflow],
            activities=[
                _fake_ensure_test_suite,
                _fake_playwright_generation_raises_grounding_violation_once,
            ],
        ):
            result = await env.client.execute_workflow(
                SuiteGenerationWorkflow.run,
                "journey-1",
                id=f"suite-test-{uuid.uuid4()}",
                task_queue=GENERATION_TASK_QUEUE,
            )

    assert sorted(result) == [
        "test-asset-for-scenario-1",
        "test-asset-for-scenario-2",
        "test-asset-for-scenario-3",
    ]
    # scenario-2's every wave-1 attempt (retry_policy exhausts all 3) saw
    # `grounding_feedback=None` (wave 1's default); its wave-2 attempt saw
    # the extracted feedback text, not another blind `None`.
    wave_1_feedback = received_feedback["scenario-2"][:3]
    wave_2_feedback = received_feedback["scenario-2"][3]
    assert all(f is None for f in wave_1_feedback)
    assert wave_2_feedback is not None
    assert "#invented" in wave_2_feedback
