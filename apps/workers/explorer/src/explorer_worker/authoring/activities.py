"""Temporal activities only authoring has; every other step is one of
Explorer's own activities (explorer_worker.activities), called as it is."""

import logging
import uuid

from temporalio import activity

from explorer_worker.activities import _fail_run
from explorer_worker.authoring import plan, promote, request
from explorer_worker.journal import Journal

logger = logging.getLogger(__name__)

READ_REQUEST_ACTIVITY = "authoring_read_request"
START_ACTIVITY = "authoring_start"
PLAN_MISSIONS_ACTIVITY = "authoring_plan_missions"
QUEUED_MISSIONS_ACTIVITY = "authoring_queued_missions"
FINISH_EXPLORING_ACTIVITY = "authoring_finish_exploring"
RETRY_BLANK_ACTIVITY = "authoring_retry_if_nothing_seen"
DONE_ACTIVITY = "authoring_say_done"
PLANNED_TESTS_ACTIVITY = "authoring_planned_tests"
PLAN_TESTS_ACTIVITY = "authoring_plan_tests"
PROMOTE_ACTIVITY = "authoring_add_test_cases"


@activity.defn(name=READ_REQUEST_ACTIVITY)
async def read_request_activity(run_id: str) -> None:
    try:
        await request.read_and_keep(uuid.UUID(run_id))
    except Exception:  # the summary falls back to the request as written
        logger.exception("authoring: reading the request failed")


@activity.defn(name=START_ACTIVITY)
async def start_activity(run_id: str) -> str:
    """Instead of Explorer's first look: the request becomes the run's summary."""
    try:
        return request.start(uuid.UUID(run_id))
    except Exception as exc:
        logger.exception("authoring start failed")
        return _fail_run(uuid.UUID(run_id), exc)


@activity.defn(name=PLAN_MISSIONS_ACTIVITY)
async def plan_missions_activity(run_id: str) -> int:
    try:
        return await plan.plan_missions(uuid.UUID(run_id))
    except Exception as exc:
        logger.exception("authoring mission planning failed")
        _fail_run(uuid.UUID(run_id), exc)
        return 0


@activity.defn(name=QUEUED_MISSIONS_ACTIVITY)
async def queued_missions_activity(run_id: str) -> list[str]:
    return plan.queued_missions(uuid.UUID(run_id))


@activity.defn(name=RETRY_BLANK_ACTIVITY)
async def retry_blank_activity(run_id: str) -> bool:
    return plan.retry_if_nothing_seen(uuid.UUID(run_id))


@activity.defn(name=PLANNED_TESTS_ACTIVITY)
async def planned_tests_activity(run_id: str) -> list[str]:
    return plan.planned_tests(uuid.UUID(run_id))


@activity.defn(name=DONE_ACTIVITY)
async def done_activity(run_id: str) -> None:
    plan.say_done(uuid.UUID(run_id))


@activity.defn(name=FINISH_EXPLORING_ACTIVITY)
async def finish_exploring_activity(run_id: str) -> None:
    plan.finish_exploring(uuid.UUID(run_id))


@activity.defn(name=PLAN_TESTS_ACTIVITY)
async def plan_tests_activity(run_id: str) -> int:
    try:
        return await plan.plan_tests(uuid.UUID(run_id))
    except Exception as exc:
        logger.exception("authoring scenario planning failed")
        _fail_run(uuid.UUID(run_id), exc)
        return 0


@activity.defn(name=PROMOTE_ACTIVITY)
async def promote_activity(run_id: str) -> list[str]:
    try:
        return await promote.promote(uuid.UUID(run_id))
    except Exception as exc:
        logger.exception("authoring hand-off failed")
        Journal(uuid.UUID(run_id)).event(
            "error",
            "Couldn't add the test cases",
            (str(exc).splitlines() or ["?"])[0][:300],
        )
        return []


ACTIVITIES = [
    read_request_activity,
    start_activity,
    plan_missions_activity,
    queued_missions_activity,
    finish_exploring_activity,
    retry_blank_activity,
    done_activity,
    planned_tests_activity,
    plan_tests_activity,
    promote_activity,
]
