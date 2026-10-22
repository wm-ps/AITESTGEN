"""ApplicationTestExecutionWorkflow (Run All Tests feature) — runs against
Temporal's in-memory time-skipping test environment with fake Activities
(no Postgres/Playwright/Vault needed; those are covered by the real
Activities' own tests in apps/workers/execution). Verifies the
orchestration shape itself: a blocked Prepare result short-circuits before
any ExecuteTestActivity call, concurrency is bounded by max_concurrency, one
ExecuteTestActivity failure doesn't stop Finalize from running for the rest,
Finalize always runs when there's anything (or nothing) to finalize, and
HealTestActivity is invoked once per executable test right after its own
ExecuteTestActivity call (self-healing).

Every test registers a fake HealTestActivity alongside Prepare/Execute/
Finalize — real_one's workflow code now calls it unconditionally after every
ExecuteTestActivity, so a test that omitted it would hang waiting on an
activity task no worker in the test environment can service.
"""

import asyncio
import uuid
from datetime import timedelta

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import CancelledError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from workflows import (
    CHECK_SCHEDULE_GATE_ACTIVITY_NAME,
    CLEANUP_CANCELLED_TEST_RUN_ACTIVITY_NAME,
    EXECUTE_TEST_ACTIVITY_NAME,
    EXECUTION_TASK_QUEUE,
    FINALIZE_TEST_RUN_ACTIVITY_NAME,
    FORCE_COMPLETE_TEST_RUN_ACTIVITY_NAME,
    GENERATE_ALLURE_REPORT_ACTIVITY_NAME,
    HEAL_TEST_ACTIVITY_NAME,
    PREPARE_TEST_RUN_ACTIVITY_NAME,
    SEND_TEST_RUN_REPORT_EMAIL_ACTIVITY_NAME,
    ApplicationTestExecutionWorkflow,
    CleanupCancelledTestRunActivityInput,
    ExecutableTest,
    ExecuteTestActivityInput,
    ExecutionWorkflowInput,
    FinalizeTestRunActivityInput,
    ForceCompleteTestRunActivityInput,
    GenerateAllureReportActivityInput,
    HealTestActivityInput,
    PrepareTestRunActivityInput,
    PrepareTestRunActivityResult,
    ScheduledExecutionWorkflow,
    ScheduledExecutionWorkflowInput,
    ScheduleGateActivityInput,
    ScheduleGateActivityResult,
    SendTestRunReportEmailActivityInput,
)


def _fake_heal(heal_calls: list[str]):
    @activity.defn(name=HEAL_TEST_ACTIVITY_NAME)
    async def _heal(input: HealTestActivityInput) -> None:
        heal_calls.append(input.test_result_id)

    return _heal


@pytest.mark.asyncio
async def test_blocked_prepare_short_circuits_before_any_execute_or_finalize() -> None:
    execute_calls: list[str] = []
    finalize_calls: list[str] = []
    heal_calls: list[str] = []

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
            activities=[_fake_prepare, _fake_execute, _fake_finalize, _fake_heal(heal_calls)],
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
    assert heal_calls == []


@pytest.mark.asyncio
async def test_no_executable_tests_still_finalizes() -> None:
    finalize_calls: list[str] = []
    heal_calls: list[str] = []

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
            activities=[_fake_prepare, _fake_execute, _fake_finalize, _fake_heal(heal_calls)],
        ):
            result = await env.client.execute_workflow(
                ApplicationTestExecutionWorkflow.run,
                ExecutionWorkflowInput(application_id="app-1"),
                id=f"execution-test-{uuid.uuid4()}",
                task_queue=EXECUTION_TASK_QUEUE,
            )

    assert result == "run-1"
    assert finalize_calls == ["run-1"]
    assert heal_calls == []


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
    heal_calls: list[str] = []

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
            activities=[_fake_prepare, _fake_execute, _fake_finalize, _fake_heal(heal_calls)],
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
    assert sorted(heal_calls) == sorted(t.test_result_id for t in executable)


@pytest.mark.asyncio
async def test_one_execute_failure_does_not_block_finalize_or_siblings() -> None:
    executable = [
        ExecutableTest(test_result_id="result-1", test_asset_id="asset-1"),
        ExecutableTest(test_result_id="result-2", test_asset_id="asset-2"),
    ]
    executed: list[str] = []
    finalize_calls: list[str] = []
    heal_calls: list[str] = []

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
            activities=[_fake_prepare, _fake_execute, _fake_finalize, _fake_heal(heal_calls)],
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
    # result-1's ExecuteTestActivity exhausted its own retry_policy (a real
    # infra failure) — HealTestActivity is only reached for a test whose
    # ExecuteTestActivity call actually returned, per run_one's sequencing.
    assert heal_calls == ["result-2"]


@pytest.mark.asyncio
async def test_heal_test_activity_invoked_once_per_executable_test() -> None:
    """Self-healing: HealTestActivity must be called exactly once, after
    ExecuteTestActivity, for every executable test — regardless of that
    test's own pass/fail outcome (HealTestActivity itself is what decides
    whether a given result is actually eligible to be healed)."""
    executable = [
        ExecutableTest(test_result_id=f"result-{i}", test_asset_id=f"asset-{i}") for i in range(3)
    ]
    call_order: list[tuple[str, str]] = []

    @activity.defn(name=PREPARE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_prepare(input: PrepareTestRunActivityInput) -> PrepareTestRunActivityResult:
        return PrepareTestRunActivityResult(
            test_run_id="run-1", blocked=False, executable=executable
        )

    @activity.defn(name=EXECUTE_TEST_ACTIVITY_NAME)
    async def _fake_execute(input: ExecuteTestActivityInput) -> str:
        call_order.append(("execute", input.test_result_id))
        return input.test_result_id

    @activity.defn(name=HEAL_TEST_ACTIVITY_NAME)
    async def _fake_heal_ordered(input: HealTestActivityInput) -> None:
        call_order.append(("heal", input.test_result_id))

    @activity.defn(name=FINALIZE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_finalize(input: FinalizeTestRunActivityInput) -> None:
        pass

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[ApplicationTestExecutionWorkflow],
            activities=[_fake_prepare, _fake_execute, _fake_finalize, _fake_heal_ordered],
        ):
            result = await env.client.execute_workflow(
                ApplicationTestExecutionWorkflow.run,
                ExecutionWorkflowInput(application_id="app-1"),
                id=f"execution-test-{uuid.uuid4()}",
                task_queue=EXECUTION_TASK_QUEUE,
            )

    assert result == "run-1"
    heal_calls = [tid for kind, tid in call_order if kind == "heal"]
    assert sorted(heal_calls) == sorted(t.test_result_id for t in executable)
    # Each test's own heal call comes after its own execute call (not just
    # after all executes globally) — run_one awaits Execute then Heal
    # sequentially per test, inside the same semaphore slot.
    by_test: dict[str, list[str]] = {}
    for kind, tid in call_order:
        by_test.setdefault(tid, []).append(kind)
    for tid, kinds in by_test.items():
        assert kinds == ["execute", "heal"], f"{tid}: expected execute-then-heal, got {kinds}"


def _fake_prepare_with(executable: list[ExecutableTest], blocked: bool = False):
    @activity.defn(name=PREPARE_TEST_RUN_ACTIVITY_NAME)
    async def _prepare(input: PrepareTestRunActivityInput) -> PrepareTestRunActivityResult:
        return PrepareTestRunActivityResult(
            test_run_id="run-1", blocked=blocked, executable=executable
        )

    return _prepare


async def _run_with_allure(
    *,
    report_fails: bool = False,
    blocked: bool = False,
    email_fails: bool = False,
    finalize_fails: bool = False,
) -> list[str]:
    """Runs the workflow with fake GenerateAllureReport / SendTestRunReportEmail
    activities and returns the order activities ran in."""
    order: list[str] = []
    executable = [ExecutableTest(test_result_id="result-1", test_asset_id="asset-1")]

    @activity.defn(name=EXECUTE_TEST_ACTIVITY_NAME)
    async def _execute(input: ExecuteTestActivityInput) -> str:
        order.append("execute")
        return input.test_result_id

    @activity.defn(name=GENERATE_ALLURE_REPORT_ACTIVITY_NAME)
    async def _generate(input: GenerateAllureReportActivityInput) -> str | None:
        order.append("generate")
        if report_fails:
            raise RuntimeError("simulated allure failure")
        return "test-runs/run-1/allure-report.html"

    @activity.defn(name=FINALIZE_TEST_RUN_ACTIVITY_NAME)
    async def _finalize(input: FinalizeTestRunActivityInput) -> None:
        order.append("finalize")
        if finalize_fails:
            raise RuntimeError("simulated finalize failure")

    @activity.defn(name=FORCE_COMPLETE_TEST_RUN_ACTIVITY_NAME)
    async def _force_complete(input: ForceCompleteTestRunActivityInput) -> None:
        order.append("force_complete")

    @activity.defn(name=SEND_TEST_RUN_REPORT_EMAIL_ACTIVITY_NAME)
    async def _email(input: SendTestRunReportEmailActivityInput) -> None:
        order.append("email")
        if email_fails:
            raise RuntimeError("simulated SMTP failure")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[ApplicationTestExecutionWorkflow],
            activities=[
                _fake_prepare_with(executable, blocked=blocked),
                _execute,
                _generate,
                _finalize,
                _force_complete,
                _email,
                _fake_heal([]),
            ],
        ):
            try:
                result = await env.client.execute_workflow(
                    ApplicationTestExecutionWorkflow.run,
                    ExecutionWorkflowInput(application_id="app-1"),
                    id=f"execution-test-{uuid.uuid4()}",
                    task_queue=EXECUTION_TASK_QUEUE,
                )
            except WorkflowFailureError:
                order.append("workflow_failed")
            else:
                assert result == "run-1"
    return order


@pytest.mark.asyncio
async def test_allure_report_is_generated_after_tests_and_before_finalize() -> None:
    assert await _run_with_allure() == ["execute", "generate", "finalize", "email"]


@pytest.mark.asyncio
async def test_allure_report_failure_never_blocks_finalize() -> None:
    assert await _run_with_allure(report_fails=True) == [
        "execute",
        "generate",
        "finalize",
        "email",
    ]


@pytest.mark.asyncio
async def test_blocked_run_generates_no_allure_report() -> None:
    assert await _run_with_allure(report_fails=False, blocked=True) == []


@pytest.mark.asyncio
async def test_self_signing_in_tests_run_after_shared_session_tests() -> None:
    executable = [
        ExecutableTest(test_result_id="login", test_asset_id="a0", signs_in_itself=True),
        ExecutableTest(test_result_id="shared-1", test_asset_id="a1"),
        ExecutableTest(test_result_id="shared-2", test_asset_id="a2"),
    ]
    executed: list[str] = []
    heal_calls: list[str] = []

    @activity.defn(name=PREPARE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_prepare(input: PrepareTestRunActivityInput) -> PrepareTestRunActivityResult:
        return PrepareTestRunActivityResult(test_run_id="run-1", blocked=False, executable=executable)

    @activity.defn(name=EXECUTE_TEST_ACTIVITY_NAME)
    async def _fake_execute(input: ExecuteTestActivityInput) -> str:
        await asyncio.sleep(0.05)
        executed.append(input.test_result_id)
        return input.test_result_id

    @activity.defn(name=FINALIZE_TEST_RUN_ACTIVITY_NAME)
    async def _fake_finalize(input: FinalizeTestRunActivityInput) -> None:
        pass

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[ApplicationTestExecutionWorkflow],
            activities=[_fake_prepare, _fake_execute, _fake_finalize, _fake_heal(heal_calls)],
        ):
            await env.client.execute_workflow(
                ApplicationTestExecutionWorkflow.run,
                ExecutionWorkflowInput(application_id="app-1"),
                id=f"execution-test-{uuid.uuid4()}",
                task_queue=EXECUTION_TASK_QUEUE,
            )

    assert executed[-1] == "login"
    assert sorted(executed[:2]) == ["shared-1", "shared-2"]


@pytest.mark.asyncio
async def test_email_failure_never_fails_the_completed_run() -> None:
    order = await _run_with_allure(email_fails=True)
    # Retried (up to 3 attempts), then swallowed: the workflow still returns.
    assert order[:3] == ["execute", "generate", "finalize"]
    assert order[3:] == ["email"] * 3
    assert "workflow_failed" not in order


@pytest.mark.asyncio
async def test_no_email_when_finalize_fails() -> None:
    order = await _run_with_allure(finalize_fails=True)
    assert "email" not in order
    assert order[-2:] == ["force_complete", "workflow_failed"]


# --- Cancelling a run ---------------------------------------------------------


def _cancellable_activities(order: list[str], execute_started: asyncio.Event) -> list:
    """Execute heartbeats until it's cancelled (like the real one's
    `cancel_watch`); every later step just records that it ran."""

    @activity.defn(name=EXECUTE_TEST_ACTIVITY_NAME)
    async def _execute(input: ExecuteTestActivityInput) -> str:
        order.append("execute_started")
        execute_started.set()
        try:
            while True:
                activity.heartbeat()
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            order.append("execute_cancelled")
            raise

    @activity.defn(name=GENERATE_ALLURE_REPORT_ACTIVITY_NAME)
    async def _generate(input: GenerateAllureReportActivityInput) -> str | None:
        order.append("generate")
        return None

    @activity.defn(name=FINALIZE_TEST_RUN_ACTIVITY_NAME)
    async def _finalize(input: FinalizeTestRunActivityInput) -> None:
        order.append("finalize")

    @activity.defn(name=SEND_TEST_RUN_REPORT_EMAIL_ACTIVITY_NAME)
    async def _email(input: SendTestRunReportEmailActivityInput) -> None:
        order.append("email")

    @activity.defn(name=CLEANUP_CANCELLED_TEST_RUN_ACTIVITY_NAME)
    async def _cleanup(input: CleanupCancelledTestRunActivityInput) -> None:
        order.append("cleanup")

    @activity.defn(name=HEAL_TEST_ACTIVITY_NAME)
    async def _heal(input: HealTestActivityInput) -> None:
        order.append("heal")

    return [
        _fake_prepare_with([ExecutableTest(test_result_id="result-1", test_asset_id="asset-1")]),
        _execute,
        _generate,
        _finalize,
        _email,
        _cleanup,
        _heal,
    ]


@pytest.mark.asyncio
async def test_cancel_stops_execute_then_cleans_up_with_no_report_finalize_or_email() -> None:
    order: list[str] = []
    execute_started = asyncio.Event()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[ApplicationTestExecutionWorkflow],
            activities=_cancellable_activities(order, execute_started),
            # So the cancel reaches the heartbeating fake in well under the
            # production throttle (80% of the 15s heartbeat timeout).
            max_heartbeat_throttle_interval=timedelta(milliseconds=100),
            default_heartbeat_throttle_interval=timedelta(milliseconds=100),
        ):
            handle = await env.client.start_workflow(
                ApplicationTestExecutionWorkflow.run,
                ExecutionWorkflowInput(application_id="app-1"),
                id=f"execution-test-{uuid.uuid4()}",
                task_queue=EXECUTION_TASK_QUEUE,
            )
            await asyncio.wait_for(execute_started.wait(), timeout=30)
            await handle.cancel()
            with pytest.raises(WorkflowFailureError) as failure:
                await handle.result()

    assert isinstance(failure.value.cause, CancelledError)
    # WAIT_CANCELLATION_COMPLETED: cleanup only after Execute really stopped.
    assert order == ["execute_started", "execute_cancelled", "cleanup"]


@pytest.mark.asyncio
async def test_cancel_still_ends_the_run_when_the_step_in_flight_finishes_normally() -> None:
    """Observed live: the worker's DB watch stopped Prepare before Temporal's
    cancel reached it, Prepare *returned normally*, and the workflow went on
    to Allure/Finalize/email and ended Completed. A requested cancel must
    still end the run as Cancelled, with cleanup and nothing else."""
    order: list[str] = []
    prepare_started = asyncio.Event()
    release_prepare = asyncio.Event()
    activities = _cancellable_activities(order, asyncio.Event())

    @activity.defn(name=PREPARE_TEST_RUN_ACTIVITY_NAME)
    async def _prepare(input: PrepareTestRunActivityInput) -> PrepareTestRunActivityResult:
        order.append("prepare")
        prepare_started.set()
        await release_prepare.wait()  # no heartbeat: Temporal's cancel never arrives
        return PrepareTestRunActivityResult(
            test_run_id="run-1",
            blocked=False,
            executable=[ExecutableTest(test_result_id="result-1", test_asset_id="asset-1")],
        )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[ApplicationTestExecutionWorkflow],
            activities=[_prepare, *activities[1:]],
        ):
            handle = await env.client.start_workflow(
                ApplicationTestExecutionWorkflow.run,
                ExecutionWorkflowInput(application_id="app-1"),
                id=f"execution-test-{uuid.uuid4()}",
                task_queue=EXECUTION_TASK_QUEUE,
            )
            await asyncio.wait_for(prepare_started.wait(), timeout=30)
            await handle.cancel()
            await asyncio.sleep(0.5)
            release_prepare.set()
            with pytest.raises(WorkflowFailureError) as failure:
                await handle.result()

    assert isinstance(failure.value.cause, CancelledError)
    assert order == ["prepare", "cleanup"]


@pytest.mark.asyncio
async def test_a_cancelled_scheduled_run_does_not_fail_its_schedule_occurrence() -> None:
    order: list[str] = []
    execute_started = asyncio.Event()

    @activity.defn(name=CHECK_SCHEDULE_GATE_ACTIVITY_NAME)
    async def _gate(input: ScheduleGateActivityInput) -> ScheduleGateActivityResult:
        return ScheduleGateActivityResult(proceed=True)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=EXECUTION_TASK_QUEUE,
            workflows=[ApplicationTestExecutionWorkflow, ScheduledExecutionWorkflow],
            activities=[*_cancellable_activities(order, execute_started), _gate],
            max_heartbeat_throttle_interval=timedelta(milliseconds=100),
            default_heartbeat_throttle_interval=timedelta(milliseconds=100),
        ):
            parent_id = f"scheduled-test-{uuid.uuid4()}"
            parent = await env.client.start_workflow(
                ScheduledExecutionWorkflow.run,
                ScheduledExecutionWorkflowInput(
                    application_id="app-1", schedule_id="schedule-1", schedule_name="Nightly"
                ),
                id=parent_id,
                task_queue=EXECUTION_TASK_QUEUE,
            )
            await asyncio.wait_for(execute_started.wait(), timeout=30)
            # What the cancel endpoint does: cancel the run's own workflow.
            await env.client.get_workflow_handle(f"execution-{parent_id}").cancel()

            assert await parent.result() == "cancelled"

    assert "cleanup" in order
