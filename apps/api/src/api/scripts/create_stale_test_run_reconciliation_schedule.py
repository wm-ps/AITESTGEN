"""One-off setup script — creates the stale-TestRun-reconciliation Schedule.

Same Temporal Schedule pattern as `create_cleanup_schedule.py` (that script's
own docstring has the "first use of a Schedule" context), fired every 15
minutes rather than daily — this closes a user-visible gap (a TestRun stuck
"running" forever after a crash), not a background-cleanup one, so it can't
wait a full day. Idempotent: run again any time (after a Temporal namespace
reset, or just to confirm it exists) — an already-existing schedule id is
left untouched, not duplicated or reset.

Run with: uv run --package api python -m api.scripts.create_stale_test_run_reconciliation_schedule
"""

import asyncio

from temporalio.client import (
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleSpec,
)
from temporalio.service import RPCError, RPCStatusCode
from workflows import EXECUTION_TASK_QUEUE, ReconcileStaleTestRunsWorkflow

from api.temporal_client import get_temporal_client

SCHEDULE_ID = "reconcile-stale-test-runs-every-15-min"


async def main() -> None:
    client = await get_temporal_client()
    try:
        await client.create_schedule(
            SCHEDULE_ID,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    ReconcileStaleTestRunsWorkflow.run,
                    id="reconcile-stale-test-runs",
                    task_queue=EXECUTION_TASK_QUEUE,
                ),
                spec=ScheduleSpec(cron_expressions=["*/15 * * * *"]),
            ),
        )
        print(f"Created schedule {SCHEDULE_ID!r} — runs ReconcileStaleTestRunsWorkflow every 15 min")
    except RPCError as exc:
        if exc.status != RPCStatusCode.ALREADY_EXISTS:
            raise
        print(f"Schedule {SCHEDULE_ID!r} already exists — nothing to do")


if __name__ == "__main__":
    asyncio.run(main())
