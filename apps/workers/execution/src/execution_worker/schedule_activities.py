"""CheckScheduleGateActivity — the I/O half of ScheduledExecutionWorkflow's
fire-time guard (Schedules feature).

Sync (`def`, not `async def`) like the cleanup activities: two indexed
single-row reads and nothing else, serviced by the execution worker's
existing ThreadPoolExecutor. No new worker process, no new task queue —
same reasoning as CleanupWorkflow riding execution-task-queue.
"""

import logging
import uuid
from typing import Any, cast

from domain import Application, Schedule, TestRun
from sqlalchemy import ColumnElement
from sqlmodel import Session, select
from temporalio import activity
from workflows import ScheduleGateActivityInput, ScheduleGateActivityResult

from execution_worker.db import engine

logger = logging.getLogger(__name__)

# The statuses that mean "an execution is in flight for this Application".
# TestRunStatus is pending | running | completed | blocked; the first two
# are non-terminal.
IN_PROGRESS_TEST_RUN_STATUSES = ("pending", "running")


def _eq(column: Any, value: Any) -> ColumnElement[bool]:
    return cast("ColumnElement[bool]", column == value)


def _in(column: Any, values: tuple[Any, ...]) -> ColumnElement[bool]:
    return cast("ColumnElement[bool]", column.in_(values))


@activity.defn(name="CheckScheduleGateActivity")
def check_schedule_gate_activity(
    input: ScheduleGateActivityInput,
) -> ScheduleGateActivityResult:
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(
                _eq(Application.external_id, uuid.UUID(input.application_id)),
                Application.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        ).first()
        if application is None:
            # Application soft-delete pauses every associated Schedule as
            # its primary guard; this is the defensive equivalent of what
            # `_get_org_application` gives every manual run for free.
            logger.info(
                "CheckScheduleGateActivity: skipping schedule_id=%s — application %s "
                "is missing or soft-deleted",
                input.schedule_id,
                input.application_id,
            )
            return ScheduleGateActivityResult(proceed=False, reason="application_unavailable")

        schedule = session.exec(
            select(Schedule).where(
                _eq(Schedule.external_id, uuid.UUID(input.schedule_id)),
                Schedule.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        ).first()
        if schedule is None:
            # A Temporal Schedule that outlived its DB row (the API's
            # delete touches Temporal then Postgres, not atomically).
            # `Schedule.enabled` is deliberately NOT checked here: Temporal's
            # own paused state is the single source of truth for whether an
            # occurrence fires (see the Schedules API), and a second
            # enabled-check here would be a competing one.
            logger.info(
                "CheckScheduleGateActivity: skipping — schedule %s no longer exists",
                input.schedule_id,
            )
            return ScheduleGateActivityResult(proceed=False, reason="schedule_unavailable")

        in_progress = session.exec(
            select(TestRun.id)
            .where(
                _eq(TestRun.application_id, application.id),
                _in(TestRun.status, IN_PROGRESS_TEST_RUN_STATUSES),
            )
            .limit(1)
        ).first()
        if in_progress is not None:
            # A scheduled occurrence yields to an already-running execution
            # and is skipped, never queued. The reverse direction (a manual
            # click while a scheduled run is running) gets no new check at
            # all — `trigger_test_run` is untouched.
            logger.info(
                "CheckScheduleGateActivity: skipping schedule %s (%s) — a test run for "
                "application %s is already in progress",
                schedule.name,
                input.schedule_id,
                input.application_id,
            )
            return ScheduleGateActivityResult(proceed=False, reason="execution_in_progress")

        return ScheduleGateActivityResult(proceed=True)
