"""ApplicationTestExecutionWorkflow (Run All Tests feature) — runs against
Temporal's in-memory time-skipping test environment with fake Activities
(no Postgres/Playwright/Vault needed; those are covered by the real
Activities' own tests in apps/workers/execution). Verifies the
orchestration shape itself: a blocked Prepare result short-circuits before
any ExecuteTestActivity call, concurrency is bounded by max_concurrency, one
ExecuteTestActivity failure doesn't stop Finalize from running for the rest,
and Finalize always runs when there's anything (or nothing) to finalize.
"""

import asyncio
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from workflows import (
    EXECUTE_TEST_ACTIVITY_NAME,
    EXECUTION_TASK_QUEUE,
    FINALIZE_TEST_RUN_ACTIVITY_NAME,
    PREPARE_TEST_RUN_ACTIVITY_NAME,
    ApplicationTestExecutionWorkflow,
    ExecutableTest,
    ExecuteTestActivityInput,
    ExecutionWorkflowInput,
    FinalizeTestRunActivityInput,
    PrepareTestRunActivityInput,
    PrepareTestRunActivityResult,
)


@pytest.mark.asyncio
async def test_blocked_prepare_short_circuits_before_any_execute_or_finalize() -> None:
    execute_calls: list[str] = []
    finalize_calls: list[str] = []

    @activity.defn(name=PREPARE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_prepare(input: PrepareTestRunActivityInput) -> PrepareTestRunActivityResult:
        return PrepareTestRunActivityResult(test_run_id="run-1", blocked=True, executable=[])

    @activity.defn(name=EXECUTE_TEST_ACTIVITY_NAME)
    async def _fake_execute(input: ExecuteTestActivityInput) -> str:
        execute_calls.append(input.test_result_id)
        return input.test_result_id

    @activity.defn(name=FINALIZE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_finalize(input: FinalizeTestRunActivityInput) -> None:
        finalize_calls.append(input.test_run_id)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[ApplicationTestExecutionWorkflow],
            activities=[_fake_prepare, _fake_execute, _fake_finalize],
        ):
            result = await env.client.execute_workflow(
                ApplicationTestExecutionWorkflow.run,
                ExecutionWorkflowInput(application_id="app-1"),
                id=f"execution-test-{uuid.uuid4()}",
                task_queue=EXECUTION_TASK_QUEUE,
            )

    assert result == "run-1"
    assert execute_calls == []
    assert finalize_calls == []


@pytest.mark.asyncio
async def test_no_executable_tests_still_finalizes() -> None:
    finalize_calls: list[str] = []

    @activity.defn(name=PREPARE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_prepare(input: PrepareTestRunActivityInput) -> PrepareTestRunActivityResult:
        return PrepareTestRunActivityResult(test_run_id="run-1", blocked=False, executable=[])

    @activity.defn(name=EXECUTE_TEST_ACTIVITY_NAME)
    async def _fake_execute(input: ExecuteTestActivityInput) -> str:
        raise AssertionError("should never be called when there is nothing executable")

    @activity.defn(name=FINALIZE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_finalize(input: FinalizeTestRunActivityInput) -> None:
        finalize_calls.append(input.test_run_id)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[ApplicationTestExecutionWorkflow],
            activities=[_fake_prepare, _fake_execute, _fake_finalize],
        ):
            result = await env.client.execute_workflow(
                ApplicationTestExecutionWorkflow.run,
                ExecutionWorkflowInput(application_id="app-1"),
                id=f"execution-test-{uuid.uuid4()}",
                task_queue=EXECUTION_TASK_QUEUE,
            )

    assert result == "run-1"
    assert finalize_calls == ["run-1"]


@pytest.mark.asyncio
async def test_fans_out_one_execute_call_per_test_and_bounds_concurrency() -> None:
    executable = [
        ExecutableTest(test_result_id=f"result-{i}", test_asset_id=f"asset-{i}") for i in range(6)
    ]
    max_concurrency = 2
    in_flight = 0
    max_observed_in_flight = 0
    executed: list[str] = []
    finalize_calls: list[str] = []

    @activity.defn(name=PREPARE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_prepare(input: PrepareTestRunActivityInput) -> PrepareTestRunActivityResult:
        return PrepareTestRunActivityResult(
            test_run_id="run-1", blocked=False, executable=executable
        )

    @activity.defn(name=EXECUTE_TEST_ACTIVITY_NAME)
    async def _fake_execute(input: ExecuteTestActivityInput) -> str:
        nonlocal in_flight, max_observed_in_flight
        in_flight += 1
        max_observed_in_flight = max(max_observed_in_flight, in_flight)
        await asyncio.sleep(0.05)
        executed.append(input.test_result_id)
        in_flight -= 1
        return input.test_result_id

    @activity.defn(name=FINALIZE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_finalize(input: FinalizeTestRunActivityInput) -> None:
        finalize_calls.append(input.test_run_id)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[ApplicationTestExecutionWorkflow],
            activities=[_fake_prepare, _fake_execute, _fake_finalize],
        ):
            result = await env.client.execute_workflow(
                ApplicationTestExecutionWorkflow.run,
                ExecutionWorkflowInput(application_id="app-1", max_concurrency=max_concurrency),
                id=f"execution-test-{uuid.uuid4()}",
                task_queue=EXECUTION_TASK_QUEUE,
            )

    assert result == "run-1"
    assert sorted(executed) == sorted(t.test_result_id for t in executable)
    assert max_observed_in_flight <= max_concurrency
    assert finalize_calls == ["run-1"]


@pytest.mark.asyncio
async def test_one_execute_failure_does_not_block_finalize_or_siblings() -> None:
    executable = [
        ExecutableTest(test_result_id="result-1", test_asset_id="asset-1"),
        ExecutableTest(test_result_id="result-2", test_asset_id="asset-2"),
    ]
    executed: list[str] = []
    finalize_calls: list[str] = []

    @activity.defn(name=PREPARE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_prepare(input: PrepareTestRunActivityInput) -> PrepareTestRunActivityResult:
        return PrepareTestRunActivityResult(
            test_run_id="run-1", blocked=False, executable=executable
        )

    @activity.defn(name=EXECUTE_TEST_ACTIVITY_NAME)
    async def _fake_execute(input: ExecuteTestActivityInput) -> str:
        if input.test_result_id == "result-1":
            raise RuntimeError("simulated infra failure — exhausts retry_policy")
        executed.append(input.test_result_id)
        return input.test_result_id

    @activity.defn(name=FINALIZE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_finalize(input: FinalizeTestRunActivityInput) -> None:
        finalize_calls.append(input.test_run_id)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[ApplicationTestExecutionWorkflow],
            activities=[_fake_prepare, _fake_execute, _fake_finalize],
        ):
            result = await env.client.execute_workflow(
                ApplicationTestExecutionWorkflow.run,
                ExecutionWorkflowInput(application_id="app-1"),
                id=f"execution-test-{uuid.uuid4()}",
                task_queue=EXECUTION_TASK_QUEUE,
            )

    assert result == "run-1"
    assert executed == ["result-2"]
    assert finalize_calls == ["run-1"]
