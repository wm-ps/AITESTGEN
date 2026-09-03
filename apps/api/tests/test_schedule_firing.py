"""Deterministic Temporal Schedule *firing* tests (Schedules feature) — the
from-scratch test pattern item 14 of the design requires, since this repo
had zero precedent for testing Temporal Schedule firing before this.

**Cannot use `WorkflowEnvironment.start_time_skipping()` here.** Confirmed
directly (Step 0's spike): the time-skipping test server implements only
the workflow-service subset — `create_schedule` against it raises
`RPCError('...CreateSchedule is unimplemented')`. So these tests run
against the same real docker-compose Temporal every other test in
`apps/api/tests` already requires, with `trigger_immediately=True` (fires
one occurrence instantly, no wall-clock wait for the cadence itself) rather
than waiting for a real 2am.

Each test uses its own unique task queue so a developer's real running
execution worker (if any) can never steal these tasks, and fake activities
(gate + prepare/execute/heal/finalize) so this only proves the *Temporal
Schedule wiring* — the gate/prepare DB logic already has its own direct
tests (`test_schedule_activities.py`, `test_test_runs.py`, the execution
workflow's own orchestration tests).
"""

import asyncio
import uuid
from datetime import timedelta

import pytest
from api.schedule_spec import build_schedule_policy, build_schedule_spec
from api.temporal_client import get_temporal_client
from domain import Schedule
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from temporalio import activity
from temporalio.client import (
    Client,
    Schedule as TemporalSchedule,
    ScheduleActionExecutionStartWorkflow,
    ScheduleActionStartWorkflow,
    ScheduleIntervalSpec,
    ScheduleSpec,
)
from temporalio.service import RPCError
from temporalio.worker import Worker
from workflows import (
    CHECK_SCHEDULE_GATE_ACTIVITY_NAME,
    EXECUTE_TEST_ACTIVITY_NAME,
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

from api.db import engine


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


def _temporal_available() -> bool:
    async def _check() -> bool:
        try:
            await get_temporal_client()
            return True
        except Exception:
            return False

    return asyncio.run(_check())


pytestmark = pytest.mark.skipif(
    not (_db_available() and _temporal_available()),
    reason="requires PostgreSQL + Temporal reachable — start docker compose",
)


def _fake_prepare(calls: list[PrepareTestRunActivityInput]):
    @activity.defn(name=PREPARE_TEST_RUN_ACTIVITY_NAME)
    async def _prepare(input: PrepareTestRunActivityInput) -> PrepareTestRunActivityResult:
        calls.append(input)
        return PrepareTestRunActivityResult(test_run_id="run-1", blocked=False, executable=[])

    return _prepare


def _fake_execute():
    @activity.defn(name=EXECUTE_TEST_ACTIVITY_NAME)
    async def _execute(input: ExecuteTestActivityInput) -> str:
        return input.test_result_id

    return _execute


def _fake_heal():
    @activity.defn(name=HEAL_TEST_ACTIVITY_NAME)
    async def _heal(input: HealTestActivityInput) -> None:
        pass

    return _heal


def _fake_finalize():
    @activity.defn(name=FINALIZE_TEST_RUN_ACTIVITY_NAME)
    async def _finalize(input: FinalizeTestRunActivityInput) -> None:
        pass

    return _finalize


def _fake_gate_always_proceed():
    @activity.defn(name=CHECK_SCHEDULE_GATE_ACTIVITY_NAME)
    async def _gate(input: ScheduleGateActivityInput) -> ScheduleGateActivityResult:
        return ScheduleGateActivityResult(proceed=True)

    return _gate


def _fake_gate_always_skip():
    @activity.defn(name=CHECK_SCHEDULE_GATE_ACTIVITY_NAME)
    async def _gate(input: ScheduleGateActivityInput) -> ScheduleGateActivityResult:
        return ScheduleGateActivityResult(proceed=False, reason="execution_in_progress")

    return _gate


async def _delete_schedule_ignoring_not_found(client: Client, schedule_id: str) -> None:
    try:
        await client.get_schedule_handle(schedule_id).delete()
    except RPCError:
        pass


class TestImmediateFiring:
    def test_trigger_immediately_reaches_prepare_with_correct_attribution(self) -> None:
        """End-to-end proof, no mock between the Schedule and the activity:
        a real Temporal Schedule, built with the exact production
        ScheduleSpec/policy a real cadence would produce, fires and the
        attribution (schedule name/id) survives all the way to
        PrepareTestRunActivity's input."""

        async def _run() -> None:
            client = await get_temporal_client()
            task_queue = f"schedule-firing-test-{uuid.uuid4()}"
            schedule_id = f"firing-test-{uuid.uuid4()}"
            prepare_calls: list[PrepareTestRunActivityInput] = []

            schedule_row = Schedule(
                application_id=uuid.uuid4(),
                name="Nightly Regression",
                cadence_type="daily",
                hour=2,
                minute=30,
                time_zone="Asia/Kolkata",
                temporal_schedule_id=schedule_id,
            )

            try:
                async with Worker(
                    client,
                    task_queue=task_queue,
                    workflows=[ScheduledExecutionWorkflow, ApplicationTestExecutionWorkflow],
                    activities=[
                        _fake_gate_always_proceed(),
                        _fake_prepare(prepare_calls),
                        _fake_execute(),
                        _fake_heal(),
                        _fake_finalize(),
                    ],
                ):
                    await client.create_schedule(
                        schedule_id,
                        TemporalSchedule(
                            action=ScheduleActionStartWorkflow(
                                ScheduledExecutionWorkflow.run,
                                ScheduledExecutionWorkflowInput(
                                    application_id="app-1",
                                    schedule_id="sched-1",
                                    schedule_name="Nightly Regression",
                                ),
                                id=f"scheduled-execution-{schedule_id}",
                                task_queue=task_queue,
                            ),
                            # The exact production spec a real 02:30 IST
                            # daily schedule would produce.
                            spec=build_schedule_spec(schedule_row),
                            policy=build_schedule_policy(),
                        ),
                        trigger_immediately=True,
                    )

                    async def _wait_for_prepare_call() -> None:
                        while not prepare_calls:
                            await asyncio.sleep(0.1)

                    await asyncio.wait_for(_wait_for_prepare_call(), timeout=15)
            finally:
                await _delete_schedule_ignoring_not_found(client, schedule_id)

            assert len(prepare_calls) == 1
            assert prepare_calls[0].application_id == "app-1"
            assert prepare_calls[0].triggered_by_name == "Nightly Regression"
            assert prepare_calls[0].schedule_id == "sched-1"

        asyncio.run(_run())

    def test_gate_skip_still_records_a_completed_occurrence_not_a_failure(self) -> None:
        """A skip is expected behavior — the occurrence still shows up in
        Temporal's own action history as completed, and PrepareTestRunActivity
        is never reached."""

        async def _run() -> None:
            client = await get_temporal_client()
            task_queue = f"schedule-firing-test-{uuid.uuid4()}"
            schedule_id = f"firing-skip-test-{uuid.uuid4()}"
            prepare_calls: list[PrepareTestRunActivityInput] = []

            try:
                async with Worker(
                    client,
                    task_queue=task_queue,
                    workflows=[ScheduledExecutionWorkflow, ApplicationTestExecutionWorkflow],
                    activities=[
                        _fake_gate_always_skip(),
                        _fake_prepare(prepare_calls),
                        _fake_execute(),
                        _fake_heal(),
                        _fake_finalize(),
                    ],
                ):
                    await client.create_schedule(
                        schedule_id,
                        TemporalSchedule(
                            action=ScheduleActionStartWorkflow(
                                ScheduledExecutionWorkflow.run,
                                ScheduledExecutionWorkflowInput(
                                    application_id="app-1",
                                    schedule_id="sched-1",
                                    schedule_name="Nightly Regression",
                                ),
                                id=f"scheduled-execution-{schedule_id}",
                                task_queue=task_queue,
                            ),
                            spec=ScheduleSpec(
                                intervals=[ScheduleIntervalSpec(every=timedelta(hours=1))]
                            ),
                        ),
                        trigger_immediately=True,
                    )

                    async def _wait_for_one_action() -> None:
                        while True:
                            description = await client.get_schedule_handle(schedule_id).describe()
                            if description.info.num_actions >= 1:
                                return
                            await asyncio.sleep(0.2)

                    await asyncio.wait_for(_wait_for_one_action(), timeout=15)
                    await asyncio.sleep(0.5)  # let the skipped workflow finish closing out
            finally:
                await _delete_schedule_ignoring_not_found(client, schedule_id)

            assert prepare_calls == []

        asyncio.run(_run())


class TestOverlapPolicy:
    def test_overlap_skip_drops_occurrences_while_the_previous_one_is_open(self) -> None:
        """Item 5's whole claim, demonstrated rather than asserted in prose:
        a schedule firing every second, whose first occurrence is held open
        by a blocked gate — the SKIP policy must record subsequent
        occurrences as `num_actions_skipped_overlap`, not `num_actions`."""

        async def _run() -> None:
            client = await get_temporal_client()
            task_queue = f"schedule-firing-test-{uuid.uuid4()}"
            schedule_id = f"firing-overlap-test-{uuid.uuid4()}"
            release = asyncio.Event()
            gate_calls: list[ScheduleGateActivityInput] = []

            @activity.defn(name=CHECK_SCHEDULE_GATE_ACTIVITY_NAME)
            async def _blocking_gate(
                input: ScheduleGateActivityInput,
            ) -> ScheduleGateActivityResult:
                gate_calls.append(input)
                await release.wait()
                return ScheduleGateActivityResult(proceed=False, reason="execution_in_progress")

            try:
                async with Worker(
                    client,
                    task_queue=task_queue,
                    workflows=[ScheduledExecutionWorkflow, ApplicationTestExecutionWorkflow],
                    activities=[
                        _blocking_gate,
                        _fake_prepare([]),
                        _fake_execute(),
                        _fake_heal(),
                        _fake_finalize(),
                    ],
                ):
                    await client.create_schedule(
                        schedule_id,
                        TemporalSchedule(
                            action=ScheduleActionStartWorkflow(
                                ScheduledExecutionWorkflow.run,
                                ScheduledExecutionWorkflowInput(
                                    application_id="app-1",
                                    schedule_id="sched-1",
                                    schedule_name="Nightly Regression",
                                ),
                                id=f"scheduled-execution-{schedule_id}",
                                task_queue=task_queue,
                            ),
                            spec=ScheduleSpec(
                                intervals=[ScheduleIntervalSpec(every=timedelta(seconds=1))]
                            ),
                            policy=build_schedule_policy(),
                        ),
                        trigger_immediately=True,
                    )

                    async def _wait_for_a_skip() -> None:
                        while True:
                            description = await client.get_schedule_handle(schedule_id).describe()
                            if description.info.num_actions_skipped_overlap >= 1:
                                return
                            await asyncio.sleep(0.2)

                    await asyncio.wait_for(_wait_for_a_skip(), timeout=15)
                    description = await client.get_schedule_handle(schedule_id).describe()

                    assert description.info.num_actions == 1
                    assert description.info.num_actions_skipped_overlap >= 1

                    release.set()
                    await asyncio.sleep(0.5)  # let the first occurrence close out cleanly
            finally:
                await _delete_schedule_ignoring_not_found(client, schedule_id)

        asyncio.run(_run())


class TestWorkerRecovery:
    def test_occurrence_stays_open_until_a_worker_polls_it(self) -> None:
        """Empirical proof of item 4's corrected claim: with no `Worker`
        running on the task queue at all, the fired occurrence's workflow
        exists and stays `RUNNING` — it is not skipped, not failed, just
        waiting. Once a `Worker` starts, it completes normally."""

        async def _run() -> None:
            client = await get_temporal_client()
            task_queue = f"schedule-firing-test-{uuid.uuid4()}"
            schedule_id = f"firing-recovery-test-{uuid.uuid4()}"

            try:
                # No Worker started yet — the occurrence fires into a task
                # queue nothing is polling.
                await client.create_schedule(
                    schedule_id,
                    TemporalSchedule(
                        action=ScheduleActionStartWorkflow(
                            ScheduledExecutionWorkflow.run,
                            ScheduledExecutionWorkflowInput(
                                application_id="app-1",
                                schedule_id="sched-1",
                                schedule_name="Nightly Regression",
                            ),
                            id=f"scheduled-execution-{schedule_id}",
                            task_queue=task_queue,
                        ),
                        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(hours=1))]),
                    ),
                    trigger_immediately=True,
                )

                async def _wait_for_one_action() -> str:
                    while True:
                        description = await client.get_schedule_handle(schedule_id).describe()
                        if description.info.recent_actions:
                            action = description.info.recent_actions[-1].action
                            assert isinstance(action, ScheduleActionExecutionStartWorkflow)
                            return action.workflow_id
                        await asyncio.sleep(0.2)

                workflow_id = await asyncio.wait_for(_wait_for_one_action(), timeout=15)

                # Confirm it's genuinely stuck open — no worker has touched it.
                handle = client.get_workflow_handle(workflow_id)
                description = await handle.describe()
                assert description.status is not None
                assert description.status.name == "RUNNING"

                prepare_calls: list[PrepareTestRunActivityInput] = []
                async with Worker(
                    client,
                    task_queue=task_queue,
                    workflows=[ScheduledExecutionWorkflow, ApplicationTestExecutionWorkflow],
                    activities=[
                        _fake_gate_always_proceed(),
                        _fake_prepare(prepare_calls),
                        _fake_execute(),
                        _fake_heal(),
                        _fake_finalize(),
                    ],
                ):
                    result = await handle.result()

                assert result == "run-1"
                assert len(prepare_calls) == 1
            finally:
                await _delete_schedule_ignoring_not_found(client, schedule_id)

        asyncio.run(_run())
