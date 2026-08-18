"""One-off setup script — creates the daily deleted-project cleanup Schedule.

First use of a Temporal Schedule in this codebase (no cron/APScheduler
precedent exists here — every other periodic-ish job in this repo is either
request-triggered or a startup-time sweep). Idempotent: run again any time
(after a Temporal namespace reset, or just to confirm it exists) — an
already-existing schedule id is left untouched, not duplicated or reset.

Run with: uv run --package api python -m api.scripts.create_cleanup_schedule
"""

import asyncio

from temporalio.client import (
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleSpec,
)
from temporalio.service import RPCError, RPCStatusCode
from workflows import EXECUTION_TASK_QUEUE, CleanupWorkflow

from api.temporal_client import get_temporal_client

SCHEDULE_ID = "cleanup-deleted-applications-daily"


async def main() -> None:
    client = await get_temporal_client()
    try:
        await client.create_schedule(
            SCHEDULE_ID,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    CleanupWorkflow.run,
                    id="cleanup-deleted-applications",
                    task_queue=EXECUTION_TASK_QUEUE,
                ),
                # IST has no DST, but time_zone_name (not a hardcoded UTC
                # offset) is what the Temporal server actually understands
                # and keeps this legible regardless.
                spec=ScheduleSpec(cron_expressions=["0 6 * * *"], time_zone_name="Asia/Kolkata"),
            ),
        )
        print(f"Created schedule {SCHEDULE_ID!r} — runs CleanupWorkflow daily at 06:00 IST")
    except RPCError as exc:
        if exc.status != RPCStatusCode.ALREADY_EXISTS:
            raise
        print(f"Schedule {SCHEDULE_ID!r} already exists — nothing to do")


if __name__ == "__main__":
    asyncio.run(main())
