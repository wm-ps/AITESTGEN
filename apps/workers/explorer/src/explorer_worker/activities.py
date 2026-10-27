"""Temporal activities for Vantage Explorer."""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator

from temporalio import activity

from explorer_worker import breadth, hunt, missions, promote, reel, resume, tests_stage
from explorer_worker.journal import Journal
from explorer_worker.understand import understand_app

logger = logging.getLogger(__name__)

UNDERSTAND_ACTIVITY = "explorer_understand_app"
PLAN_MISSIONS_ACTIVITY = "explorer_plan_missions"
QUEUED_MISSIONS_ACTIVITY = "explorer_queued_missions"
RUN_MISSION_ACTIVITY = "explorer_run_mission"
FINISH_ACTIVITY = "explorer_finish_exploring"
REQUEUE_MISSION_ACTIVITY = "explorer_requeue_mission"
PLAN_TESTS_ACTIVITY = "explorer_plan_tests"
PLANNED_TESTS_ACTIVITY = "explorer_planned_tests"
BUILD_TEST_ACTIVITY = "explorer_build_test"
REQUEUE_TEST_ACTIVITY = "explorer_requeue_test"
FINISH_TESTING_ACTIVITY = "explorer_finish_testing"
HUNT_ACTIVITY = "explorer_hunt_hidden_screens"
BREADTH_ACTIVITY = "explorer_breadth"
REEL_ACTIVITY = "explorer_highlight_video"
PROMOTE_ACTIVITY = "explorer_send_to_vantage"
RESUME_POINT_ACTIVITY = "explorer_resume_point"
FAIL_RUN_ACTIVITY = "explorer_fail_run"
EXPIRE_RUN_ACTIVITY = "explorer_expire_run"


@contextlib.asynccontextmanager
async def kept_alive() -> AsyncIterator[None]:
    """Heartbeat every 30 s while a long step runs. A slow model call or page
    can take minutes without the step calling heartbeat itself; Temporal must
    only time out a worker that has really died (then this stops too)."""

    async def tick() -> None:
        while True:
            activity.heartbeat()
            await asyncio.sleep(30)

    ticker = asyncio.create_task(tick())
    try:
        yield
    finally:
        ticker.cancel()


def _fail_run(run_id: uuid.UUID, exc: Exception) -> str:
    reason = (str(exc).splitlines() or [type(exc).__name__])[0][:300]
    journal = Journal(run_id)
    journal.event("error", "Exploration stopped unexpectedly", reason)
    journal.update_run(status="failed", headline="Exploration stopped unexpectedly", error=reason)
    return "failed"


@activity.defn(name=UNDERSTAND_ACTIVITY)
async def understand_app_activity(run_id: str) -> str:
    try:
        async with kept_alive():
            return await understand_app(uuid.UUID(run_id), activity.heartbeat)
    except Exception as exc:  # any crash must end as a visible failed run, never a silent hang
        logger.exception("explorer understand failed")
        return _fail_run(uuid.UUID(run_id), exc)


@activity.defn(name=RESUME_POINT_ACTIVITY)
async def resume_point_activity(run_id: str) -> str:
    return resume.resume_point(uuid.UUID(run_id))


@activity.defn(name=PLAN_MISSIONS_ACTIVITY)
async def plan_missions_activity(run_id: str) -> int:
    try:
        return await missions.plan_missions(uuid.UUID(run_id))
    except Exception as exc:
        logger.exception("explorer mission planning failed")
        _fail_run(uuid.UUID(run_id), exc)
        return 0


@activity.defn(name=QUEUED_MISSIONS_ACTIVITY)
async def queued_missions_activity(run_id: str) -> list[str]:
    return missions.queued_missions(uuid.UUID(run_id))


@activity.defn(name=RUN_MISSION_ACTIVITY)
async def run_mission_activity(run_id: str, mission_id: str) -> str:
    try:
        async with kept_alive():
            return await missions.run_mission(
                uuid.UUID(run_id), uuid.UUID(mission_id), activity.heartbeat
            )
    except Exception as exc:
        # One mission failing never stops the others.
        logger.exception("explorer mission failed")
        reason = (str(exc).splitlines() or [type(exc).__name__])[0][:300]
        journal = Journal(uuid.UUID(run_id), uuid.UUID(mission_id))
        journal.event("error", "This mission stopped unexpectedly", reason)
        journal.update_mission(status="failed", outcome=reason)
        return "failed"


@activity.defn(name=REQUEUE_MISSION_ACTIVITY)
async def requeue_mission_activity(mission_id: str) -> None:
    missions.requeue_mission(uuid.UUID(mission_id))


@activity.defn(name=FINISH_ACTIVITY)
async def finish_exploring_activity(run_id: str) -> None:
    missions.finish_exploring(uuid.UUID(run_id))


@activity.defn(name=PLAN_TESTS_ACTIVITY)
async def plan_tests_activity(run_id: str) -> int:
    try:
        return await tests_stage.plan_tests(uuid.UUID(run_id))
    except Exception as exc:
        logger.exception("explorer test planning failed")
        _fail_run(uuid.UUID(run_id), exc)
        return 0


@activity.defn(name=PLANNED_TESTS_ACTIVITY)
async def planned_tests_activity(run_id: str) -> list[str]:
    return tests_stage.planned_tests(uuid.UUID(run_id))


@activity.defn(name=BUILD_TEST_ACTIVITY)
async def build_test_activity(run_id: str, test_id: str) -> str:
    reason = ""
    for attempt in range(2):
        try:
            async with kept_alive():
                return await tests_stage.build_and_prove(
                    uuid.UUID(run_id), uuid.UUID(test_id), activity.heartbeat
                )
        except Exception as exc:
            # One test failing never stops the others. A first failure is
            # often a network blip (model call, DNS): wait, then try again.
            logger.exception("explorer test build failed")
            reason = (str(exc).splitlines() or [type(exc).__name__])[0][:300]
            if attempt == 0:
                tests_stage.requeue_test(uuid.UUID(test_id))
                for _ in range(6):
                    activity.heartbeat()
                    await asyncio.sleep(10)
    return tests_stage.drop(
        Journal(uuid.UUID(run_id)),
        uuid.UUID(test_id),
        "test",
        f"Stopped unexpectedly: {reason}",
    )


@activity.defn(name=REQUEUE_TEST_ACTIVITY)
async def requeue_test_activity(test_id: str) -> None:
    tests_stage.requeue_test(uuid.UUID(test_id))


@activity.defn(name=FINISH_TESTING_ACTIVITY)
async def finish_testing_activity(run_id: str) -> None:
    tests_stage.finish_testing(uuid.UUID(run_id))


@activity.defn(name=HUNT_ACTIVITY)
async def hunt_activity(run_id: str) -> int:
    try:
        async with kept_alive():
            return await hunt.hunt(uuid.UUID(run_id), activity.heartbeat)
    except Exception:
        # The hunt is a bonus: if it fails, testing still goes ahead.
        logger.exception("explorer hidden-screen hunt failed")
        return 0


@activity.defn(name=BREADTH_ACTIVITY)
async def breadth_activity(run_id: str) -> None:
    try:
        async with kept_alive():
            await breadth.breadth(uuid.UUID(run_id), activity.heartbeat)
    except Exception:
        # Breadth checks are a bonus: testing still goes ahead without them.
        logger.exception("explorer breadth checks failed")


@activity.defn(name=REEL_ACTIVITY)
async def reel_activity(run_id: str) -> bool:
    try:
        return await asyncio.to_thread(reel.make_reel, uuid.UUID(run_id))
    except Exception:
        logger.exception("explorer highlight video failed")
        return False


@activity.defn(name=PROMOTE_ACTIVITY)
async def promote_activity(run_id: str) -> dict[str, int]:
    """Stage 8: Explorer's proven tests become Journeys / Scenarios / Test cases."""
    try:
        return await promote.promote(uuid.UUID(run_id))
    except Exception as exc:
        logger.exception("explorer hand-off to Vantage failed")
        Journal(uuid.UUID(run_id)).event(
            "error",
            "Couldn't send the results to Journeys",
            (str(exc).splitlines() or ["?"])[0][:300],
        )
        return {}


@activity.defn(name=EXPIRE_RUN_ACTIVITY)
async def expire_run_activity(run_id: str, days: int) -> str:
    """Nobody confirmed the App Summary in time: the run ends for good
    ("expired" — not resumable, not active, so the app is free for a new
    run). A run stopped meanwhile keeps its own status."""
    journal = Journal(uuid.UUID(run_id))
    status = journal.status()
    if status != "awaiting_confirmation":
        return status or "gone"
    journal.event(
        "phase",
        "App Summary expired",
        f"Nobody confirmed it within {days} days, so this run has ended. Start a new run: "
        "it begins from what this one learned, and your answers are kept.",
    )
    journal.update_run(status="expired", headline=f"Expired: not confirmed within {days} days")
    return "expired"


@activity.defn(name=FAIL_RUN_ACTIVITY)
async def fail_run_activity(run_id: str, reason: str) -> str:
    """A step the workflow lost (timed out, worker died) ends as a visible
    failed run, never a run that says "understanding" forever."""
    return _fail_run(uuid.UUID(run_id), RuntimeError(reason))
