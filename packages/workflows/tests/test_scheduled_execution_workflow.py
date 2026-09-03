"""ScheduledExecutionWorkflow (Schedules feature) — runs against Temporal's
in-memory time-skipping test environment with fake Activities. Verifies the
orchestration shape: a gate that says "don't proceed" short-circuits before
the child `ApplicationTestExecutionWorkflow` ever starts (one case per skip
reason), and a gate that says "proceed" starts the child with the schedule's
name/id correctly forwarded all the way to `PrepareTestRunActivity`.

Both `ScheduledExecutionWorkflow` and `ApplicationTestExecutionWorkflow` are
registered on the test Worker — the child must be resolvable — plus fakes
for Prepare/Execute/Heal/Finalize (the child's own real workflow code calls
HealTestActivity unconditionally after every ExecuteTestActivity, so
omitting that fake would hang the test, per test_execution_workflow.py's
own note).
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from workflows import (
    CHECK_SCHEDULE_GATE_ACTIVITY_NAME,
    EXECUTE_TEST_ACTIVITY_NAME,
    EXECUTION_TASK_QUEUE,
    FINALIZE_TEST_RUN_ACTIVITY_NAME,
    HEAL_TEST_ACTIVITY_NAME,
    PREPARE_TEST_RUN_ACTIVITY_NAME,
    ApplicationTestExecutionWorkflow,
    ExecuteTestActivityInput,
    FinalizeTestRunActivityInput,
    HealTestActivityInput,
    PrepareTestRunActivityInput,
    PrepareTestRunActivityResult,
    ScheduledExecutionWorkflow,
    ScheduledExecutionWorkflowInput,
    ScheduleGateActivityInput,
    ScheduleGateActivityResult,
)


def _fake_gate(result: ScheduleGateActivityResult, calls: list[ScheduleGateActivityInput]):
    @activity.defn(name=CHECK_SCHEDULE_GATE_ACTIVITY_NAME)
    async def _gate(input: ScheduleGateActivityInput) -> ScheduleGateActivityResult:
        calls.append(input)
        return result

    return _gate


def _fake_heal():
    @activity.defn(name=HEAL_TEST_ACTIVITY_NAME)
    async def _heal(input: HealTestActivityInput) -> None:
        pass

    return _heal


def _fake_execute():
    @activity.defn(name=EXECUTE_TEST_ACTIVITY_NAME)
    async def _execute(input: ExecuteTestActivityInput) -> str:
        return input.test_result_id

    return _execute


def _fake_finalize():
    @activity.defn(name=FINALIZE_TEST_RUN_ACTIVITY_NAME)
    async def _finalize(input: FinalizeTestRunActivityInput) -> None:
        pass

    return _finalize


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason", ["application_unavailable", "schedule_unavailable", "execution_in_progress"]
)
async def test_gate_skip_never_starts_the_child_workflow(reason: str) -> None:
    gate_calls: list[ScheduleGateActivityInput] = []
    prepare_calls: list[PrepareTestRunActivityInput] = []

    @activity.defn(name=PREPARE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_prepare(input: PrepareTestRunActivityInput) -> PrepareTestRunActivityResult:
        prepare_calls.append(input)
        return PrepareTestRunActivityResult(test_run_id="run-1", blocked=False, executable=[])

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[ScheduledExecutionWorkflow, ApplicationTestExecutionWorkflow],
            activities=[
                _fake_gate(ScheduleGateActivityResult(proceed=False, reason=reason), gate_calls),
                _fake_prepare,
                _fake_execute(),
                _fake_heal(),
                _fake_finalize(),
            ],
        ):
            result = await env.client.execute_workflow(
                ScheduledExecutionWorkflow.run,
                ScheduledExecutionWorkflowInput(
                    application_id="app-1", schedule_id="sched-1", schedule_name="Nightly Regression"
                ),
                id=f"scheduled-execution-test-{uuid.uuid4()}",
                task_queue=EXECUTION_TASK_QUEUE,
            )

    assert result == f"skipped:{reason}"
    assert len(gate_calls) == 1
    assert gate_calls[0].application_id == "app-1"
    assert gate_calls[0].schedule_id == "sched-1"
    # The child never started — zero calls recorded on the fake Prepare.
    assert prepare_calls == []


@pytest.mark.asyncio
async def test_gate_proceed_starts_child_with_schedule_attribution() -> None:
    gate_calls: list[ScheduleGateActivityInput] = []
    prepare_calls: list[PrepareTestRunActivityInput] = []

    @activity.defn(name=PREPARE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_prepare(input: PrepareTestRunActivityInput) -> PrepareTestRunActivityResult:
        prepare_calls.append(input)
        return PrepareTestRunActivityResult(test_run_id="run-1", blocked=False, executable=[])

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[ScheduledExecutionWorkflow, ApplicationTestExecutionWorkflow],
            activities=[
                _fake_gate(ScheduleGateActivityResult(proceed=True), gate_calls),
                _fake_prepare,
                _fake_execute(),
                _fake_heal(),
                _fake_finalize(),
            ],
        ):
            result = await env.client.execute_workflow(
                ScheduledExecutionWorkflow.run,
                ScheduledExecutionWorkflowInput(
                    application_id="app-1", schedule_id="sched-1", schedule_name="Nightly Regression"
                ),
                id=f"scheduled-execution-test-{uuid.uuid4()}",
                task_queue=EXECUTION_TASK_QUEUE,
            )

    # The child ApplicationTestExecutionWorkflow's own result flows straight
    # through — proves this really is the unmodified execution path, not a
    # separate implementation.
    assert result == "run-1"
    assert len(prepare_calls) == 1
    # This is the assertion that proves the parent -> child -> activity hop
    # preserves attribution: the schedule name becomes triggered_by_name,
    # and schedule_id survives to the exact activity input a manual run's
    # PrepareTestRunActivity also receives (just with schedule_id=None there).
    assert prepare_calls[0].application_id == "app-1"
    assert prepare_calls[0].triggered_by_name == "Nightly Regression"
    assert prepare_calls[0].schedule_id == "sched-1"


@pytest.mark.asyncio
async def test_gate_exhausting_retries_never_starts_the_child() -> None:
    """A gate that can't be evaluated must not default to running — the
    workflow should fail rather than silently proceed."""
    prepare_calls: list[PrepareTestRunActivityInput] = []

    @activity.defn(name=CHECK_SCHEDULE_GATE_ACTIVITY_NAME)
    async def _always_fails(input: ScheduleGateActivityInput) -> ScheduleGateActivityResult:
        raise RuntimeError("simulated: gate activity can never complete")

    @activity.defn(name=PREPARE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_prepare(input: PrepareTestRunActivityInput) -> PrepareTestRunActivityResult:
        prepare_calls.append(input)
        return PrepareTestRunActivityResult(test_run_id="run-1", blocked=False, executable=[])

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[ScheduledExecutionWorkflow, ApplicationTestExecutionWorkflow],
            activities=[
                _always_fails,
                _fake_prepare,
                _fake_execute(),
                _fake_heal(),
                _fake_finalize(),
            ],
        ):
            with pytest.raises(Exception):  # noqa: B017 - Temporal wraps this in its own error type
                await env.client.execute_workflow(
                    ScheduledExecutionWorkflow.run,
                    ScheduledExecutionWorkflowInput(
                        application_id="app-1",
                        schedule_id="sched-1",
                        schedule_name="Nightly Regression",
                    ),
                    id=f"scheduled-execution-test-{uuid.uuid4()}",
                    task_queue=EXECUTION_TASK_QUEUE,
                )

    assert prepare_calls == []
