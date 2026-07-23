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
