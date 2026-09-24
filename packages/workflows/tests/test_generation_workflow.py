"""GenerationWorkflow — runs against Temporal's in-memory time-skipping test
environment with a fake ScenarioGenerationActivity (no Postgres/AI provider
needed; those are covered by the real Activity's own tests in
apps/workers/generation). Verifies the orchestration shape itself:

- On success, the Workflow returns whatever Scenario ids the Activity produced.
- `[FIXED]` On a failure that exhausts every one of the Activity's own retry
  attempts, the Workflow completes cleanly (returns `[]`) instead of itself
  ending up "Failed" — the Activity has already recorded the failure on the
  Journey by the time this happens (see that Activity's own test), so nothing
  is lost; this Workflow just must not get stuck.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.common import RetryPolicy
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from workflows import (
    GENERATION_TASK_QUEUE,
    SCENARIO_GENERATION_ACTIVITY_NAME,
    GenerationWorkflow,
    ScenarioGenerationActivityInput,
)

_attempt_counts: dict[str, int] = {}


@activity.defn(name=SCENARIO_GENERATION_ACTIVITY_NAME)
async def _fake_scenario_generation_succeeds(
    input: ScenarioGenerationActivityInput,
) -> list[str]:
    return ["scenario-1", "scenario-2"]


@activity.defn(name=SCENARIO_GENERATION_ACTIVITY_NAME)
async def _fake_scenario_generation_always_fails(
    input: ScenarioGenerationActivityInput,
) -> list[str]:
    _attempt_counts[input.journey_id] = _attempt_counts.get(input.journey_id, 0) + 1
    raise RuntimeError("AI provider timed out")


async def _run(env: WorkflowEnvironment, fake_activity) -> object:
    async with Worker(
        env.client,
        task_queue=GENERATION_TASK_QUEUE,
        workflows=[GenerationWorkflow],
        activities=[fake_activity],
    ):
        return await env.client.execute_workflow(
            GenerationWorkflow.run,
            "journey-external-1",
            id=f"generation-test-{uuid.uuid4()}",
            task_queue=GENERATION_TASK_QUEUE,
        )


@pytest.mark.asyncio
async def test_generation_workflow_returns_the_activitys_scenario_ids_on_success() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _fake_scenario_generation_succeeds)

    assert result == ["scenario-1", "scenario-2"]


@pytest.mark.asyncio
async def test_generation_workflow_completes_cleanly_once_retries_are_exhausted() -> None:
    _attempt_counts.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _fake_scenario_generation_always_fails)

    # Never raises out to the caller/Temporal — the Workflow itself
    # completes instead of ending up permanently "Failed".
    assert result == []
    # The Activity's own `RetryPolicy(maximum_attempts=3)` actually fired —
    # this is not a first-failure give-up.
    assert _attempt_counts["journey-external-1"] == 3
