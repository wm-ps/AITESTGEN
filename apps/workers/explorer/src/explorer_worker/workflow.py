"""ExplorerRunWorkflow — orchestration only (docs/vantage-explorer/PLAN.md).

mode="full":
  Stage 1  get to know the app, then wait for the user to confirm the App
           Summary (a signal — free while waiting, survives restarts);
  Stage 2  plan the Mission Board and keep up to MAX_PARALLEL missions
           running until none are queued (missions added meanwhile too);
  Stage 5  write test cases and build/prove them, MAX_PARALLEL at a time.
mode="missions": re-enter at Stage 2 for missions added after a finished run.
mode="tests":    re-enter at Stage 5 (write and prove test cases again).
mode="resume":   carry on a paused/stopped/failed run from the step it reached
                 (resume.resume_point); finished work is kept.
"""

import asyncio
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, CancelledError

with workflow.unsafe.imports_passed_through():
    from explorer_core import BRIEF_CONFIRMED_SIGNAL, EXPLORER_WORKFLOW_NAME

    from explorer_worker.activities import (
        BREADTH_ACTIVITY,
        BUILD_TEST_ACTIVITY,
        FAIL_RUN_ACTIVITY,
        FINISH_ACTIVITY,
        FINISH_TESTING_ACTIVITY,
        HUNT_ACTIVITY,
        PLAN_MISSIONS_ACTIVITY,
        PLAN_TESTS_ACTIVITY,
        PLANNED_TESTS_ACTIVITY,
        PROMOTE_ACTIVITY,
        QUEUED_MISSIONS_ACTIVITY,
        REEL_ACTIVITY,
        REQUEUE_MISSION_ACTIVITY,
        REQUEUE_TEST_ACTIVITY,
        RESUME_POINT_ACTIVITY,
        RUN_MISSION_ACTIVITY,
        UNDERSTAND_ACTIVITY,
    )

MAX_PARALLEL = 3
# A browser session isn't safely replayable mid-way; activities turn their own
# failures into visible failed runs/missions/tests instead of retrying.
_ONCE = RetryPolicy(maximum_attempts=1)
_QUICK = timedelta(minutes=2)
# A run's steps in order; a run can start at any of them (see `run`).
STEPS = ("understand", "confirm", "plan_missions", "missions", "hunt", "plan_tests", "build_tests")


@workflow.defn(name=EXPLORER_WORKFLOW_NAME)
class ExplorerRunWorkflow:
    def __init__(self) -> None:
        self._confirmed = False

    @workflow.signal(name=BRIEF_CONFIRMED_SIGNAL)
    def brief_confirmed(self) -> None:
        self._confirmed = True

    @workflow.run
    async def run(self, run_id: str, mode: str = "full") -> str:
        try:
            return await self._run(run_id, mode)
        except ActivityError as exc:
            if isinstance(exc.cause, CancelledError):
                raise  # Stop/Pause: the API already set the run's status
            # A step that timed out or lost its worker must not leave the run
            # showing "in progress" forever.
            await workflow.execute_activity(
                FAIL_RUN_ACTIVITY,
                args=[run_id, "A step stopped responding. Press Resume to carry on from here."],
                start_to_close_timeout=_QUICK,
            )
            return "failed"

    async def _run(self, run_id: str, mode: str) -> str:
        if mode == "send":
            # Only the hand-off: after you answer a possible bug.
            await self._bonus(PROMOTE_ACTIVITY, run_id, timedelta(minutes=10), heartbeat=False)
            return "sent"
        if mode == "resume":
            start: str = await workflow.execute_activity(
                RESUME_POINT_ACTIVITY, run_id, start_to_close_timeout=_QUICK
            )
        else:
            start = {"full": "understand", "missions": "missions", "tests": "plan_tests"}[mode]

        def doing(step: str) -> bool:
            return STEPS.index(step) >= STEPS.index(start)

        if doing("understand"):
            outcome: str = await workflow.execute_activity(
                UNDERSTAND_ACTIVITY,
                run_id,
                start_to_close_timeout=timedelta(hours=2),
                heartbeat_timeout=timedelta(minutes=5),
                retry_policy=_ONCE,
            )
            if outcome != "awaiting_confirmation":
                return outcome
        if doing("confirm"):
            try:
                await workflow.wait_condition(lambda: self._confirmed, timeout=timedelta(days=14))
            except TimeoutError:
                return "unconfirmed"
        if doing("plan_missions"):
            planned: int = await workflow.execute_activity(
                PLAN_MISSIONS_ACTIVITY,
                run_id,
                start_to_close_timeout=timedelta(minutes=15),
                retry_policy=_ONCE,
            )
            if planned == 0:
                return "no-missions"

        if doing("missions"):
            await self._pool(
                run_id, QUEUED_MISSIONS_ACTIVITY, RUN_MISSION_ACTIVITY, REQUEUE_MISSION_ACTIVITY
            )
            await workflow.execute_activity(FINISH_ACTIVITY, run_id, start_to_close_timeout=_QUICK)
        if doing("hunt"):
            # Stage 3: hunt for screens that only appear sometimes.
            await self._bonus(HUNT_ACTIVITY, run_id, timedelta(minutes=40))
            # Stage 6: who can see what, unlinked pages, code coverage.
            await self._bonus(BREADTH_ACTIVITY, run_id, timedelta(minutes=40))
            if mode == "missions":
                return "explored"

        tests = 0
        if doing("plan_tests"):
            tests = await self._bonus(
                PLAN_TESTS_ACTIVITY, run_id, timedelta(minutes=20), heartbeat=False
            )
        if tests or start == "build_tests":
            await self._pool(
                run_id, PLANNED_TESTS_ACTIVITY, BUILD_TEST_ACTIVITY, REQUEUE_TEST_ACTIVITY
            )
        await workflow.execute_activity(
            FINISH_TESTING_ACTIVITY, run_id, start_to_close_timeout=_QUICK
        )
        # Stage 8: proven tests land in Journeys / Scenarios / Test cases.
        await self._bonus(PROMOTE_ACTIVITY, run_id, timedelta(minutes=10), heartbeat=False)
        # Stage 7: the shareable highlight video.
        await self._bonus(REEL_ACTIVITY, run_id, timedelta(minutes=20), heartbeat=False)
        return "tested"

    async def _bonus(
        self, activity: str, run_id: str, timeout: timedelta, heartbeat: bool = True
    ) -> Any:
        """A step whose loss must not end the run (its worker restarted, it
        timed out): log it and carry on with the next step."""
        try:
            return await workflow.execute_activity(
                activity,
                run_id,
                start_to_close_timeout=timeout,
                heartbeat_timeout=timedelta(minutes=5) if heartbeat else None,
                retry_policy=_ONCE,
            )
        except ActivityError as exc:
            if isinstance(exc.cause, CancelledError):
                raise  # Stop/Pause cancelled the run: end here, don't carry on
            workflow.logger.warning("explorer step %s did not finish; continuing", activity)
            return None

    async def _pool(
        self, run_id: str, list_activity: str, run_activity: str, requeue_activity: str
    ) -> None:
        """Keep up to MAX_PARALLEL items running until none are waiting. An
        item whose worker died (restart/timeout) gets one more try (the
        requeue activity gives up on the second)."""
        running: dict[str, asyncio.Task[str]] = {}
        while True:
            waiting: list[str] = await workflow.execute_activity(
                list_activity, run_id, start_to_close_timeout=_QUICK
            )
            for item_id in waiting:
                if len(running) >= MAX_PARALLEL:
                    break
                if item_id not in running:
                    running[item_id] = asyncio.ensure_future(
                        workflow.execute_activity(
                            run_activity,
                            args=[run_id, item_id],
                            start_to_close_timeout=timedelta(minutes=45),
                            heartbeat_timeout=timedelta(minutes=5),
                            retry_policy=_ONCE,
                        )
                    )
            if not running:
                return
            await workflow.wait(list(running.values()), return_when=asyncio.FIRST_COMPLETED)
            for item_id in [i for i, task in running.items() if task.done()]:
                task = running.pop(item_id)
                failure = task.exception()
                if isinstance(failure, ActivityError) and isinstance(failure.cause, CancelledError):
                    raise failure  # Stop/Pause cancelled the run
                if failure is not None:  # requeued once, then given up
                    await workflow.execute_activity(
                        requeue_activity, item_id, start_to_close_timeout=_QUICK
                    )
