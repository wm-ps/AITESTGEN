"""ScheduledExecutionWorkflow — the entry point a Temporal Schedule targets
(Schedules feature).

A Temporal Schedule's action bypasses the API layer entirely, so the two
guards `trigger_test_run` gets for free from `_get_org_application` and from
a human looking at the screen have to exist somewhere on the workflow side.
This is that somewhere — and it is a *separate* workflow precisely so that
nothing on the manually-triggered path changes: `ApplicationTestExecution
Workflow` below is invoked as an unmodified child, exactly the definition a
"Run All Tests" click starts.

Two checks, in `CheckScheduleGateActivity`:
  * the Application is still active (`deleted_at IS NULL`) — pausing every
    Schedule on Application soft-delete is the primary guard; this is the
    defensive one that also covers an orphaned/paused-then-triggered
    Schedule;
  * no TestRun for that Application is currently pending/running — a
    scheduled occurrence yields to an in-flight manual run and is
    *skipped*, never queued. The reverse direction (a manual click while a
    scheduled run is running) gets no new check at all — `trigger_test_run`
    is untouched.
Plus one cheap third check: the `Schedule` row still exists and isn't
soft-deleted. That is the only backstop against a Temporal Schedule that
outlived its DB row (the API's delete touches Temporal then Postgres, not
atomically).

Deliberately check-then-act: a manual run started in the microseconds after
the gate returns still races through. That is fine and not worth
engineering around — `_prepare_test_run_sync`'s atomic
`UPDATE ... RETURNING` on `Application.next_test_run_number` already makes
concurrent runs numerically safe, and two concurrent runs is exactly what
two manual clicks already produce today.

A skip returns *normally* (`"skipped:<reason>"`), it does not raise: a
skipped occurrence is expected behavior, not a failure, and raising would
paint the schedule red in the Temporal UI and interact badly with
`pause_on_failure`. See `schedule_spec.build_schedule_policy`'s docstring
for how a stuck-open occurrence (execution worker down) interacts with the
schedule's `overlap=SKIP` policy — that is a Temporal-server-side effect,
nothing this workflow needs to handle itself.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from workflows.execution_workflow import (
    ApplicationTestExecutionWorkflow,
    ExecutionWorkflowInput,
)

CHECK_SCHEDULE_GATE_ACTIVITY_NAME = "CheckScheduleGateActivity"


@dataclass
class ScheduledExecutionWorkflowInput:
    application_id: str  # Application.external_id
    schedule_id: str  # Schedule.external_id
    schedule_name: str  # snapshot: becomes TestRun.triggered_by_name


@dataclass
class ScheduleGateActivityInput:
    application_id: str
    schedule_id: str


@dataclass
class ScheduleGateActivityResult:
    proceed: bool
    # "application_unavailable" | "schedule_unavailable" | "execution_in_progress"
    reason: str | None = None


@workflow.defn(name="ScheduledExecutionWorkflow")
class ScheduledExecutionWorkflow:
    @workflow.run
    async def run(self, input: ScheduledExecutionWorkflowInput) -> str:
        gate: ScheduleGateActivityResult = await workflow.execute_activity(
            CHECK_SCHEDULE_GATE_ACTIVITY_NAME,
            ScheduleGateActivityInput(
                application_id=input.application_id, schedule_id=input.schedule_id
            ),
            # Two indexed single-row lookups — generous but not the 5-minute
            # budget PrepareTestRunActivity needs.
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=ScheduleGateActivityResult,
        )
        if not gate.proceed:
            return f"skipped:{gate.reason}"

        # The identical workflow a manual "Run All Tests" click starts —
        # one execution implementation, never two. Deterministic child id
        # derived from this workflow's own id, which Temporal already
        # suffixes with the scheduled time, so it is unique per occurrence
        # and stable across replay.
        #
        # task_queue is this workflow's *own* task_queue
        # (`workflow.info().task_queue`), not a hardcoded EXECUTION_TASK_QUEUE
        # constant — in production those are the same value (this workflow is
        # only ever registered on EXECUTION_TASK_QUEUE, see worker.py), but
        # hardcoding it here silently breaks test isolation: a test Worker
        # registered on its own throwaway queue would still have its child
        # routed to the real EXECUTION_TASK_QUEUE, picked up by whatever real
        # execution worker happens to be running rather than the test's own
        # fake activities (confirmed the hard way — see test_schedule_firing.py).
        return await workflow.execute_child_workflow(
            ApplicationTestExecutionWorkflow.run,  # type: ignore[arg-type]
            ExecutionWorkflowInput(
                application_id=input.application_id,
                triggered_by_name=input.schedule_name,
                schedule_id=input.schedule_id,
            ),
            id=f"execution-{workflow.info().workflow_id}",
            task_queue=workflow.info().task_queue,
            result_type=str,
        )


__all__ = [
    "CHECK_SCHEDULE_GATE_ACTIVITY_NAME",
    "ScheduleGateActivityInput",
    "ScheduleGateActivityResult",
    "ScheduledExecutionWorkflow",
    "ScheduledExecutionWorkflowInput",
]
