"""AuthoringRunWorkflow — Explorer's run, following the user's request.

Same workflow id and confirm signal as an Explorer run, so the Explorer
screen, Confirm, Pause/Stop/Resume and the questions work on it unchanged.
A fresh walk of the user's request: no first look around the app, no
hidden-screen hunt or breadth (that is Explorer exploring by itself). The
request's questions, if any, are answered first; then Explorer walks the
request's steps (its own mission activity), writes the scenarios asked for,
proves them (its own build/prove activities), adds them as test cases and
generates their code.

mode: full | resume (from the step reached) | missions (ones the user added)
      | tests (scenarios again) | send (add the test cases again, after "Not a bug").
"""

import asyncio
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, CancelledError

with workflow.unsafe.imports_passed_through():
    from explorer_core import AUTHORING_WORKFLOW_NAME, BRIEF_CONFIRMED_SIGNAL
    from workflows import GENERATION_TASK_QUEUE

    from explorer_worker.activities import (
        BUILD_TEST_ACTIVITY,
        EXPIRE_RUN_ACTIVITY,
        FAIL_RUN_ACTIVITY,
        FINISH_TESTING_ACTIVITY,
        REEL_ACTIVITY,
        REQUEUE_MISSION_ACTIVITY,
        REQUEUE_TEST_ACTIVITY,
        RESUME_POINT_ACTIVITY,
        RUN_MISSION_ACTIVITY,
    )
    from explorer_worker.authoring.activities import (
        DONE_ACTIVITY,
        FINISH_EXPLORING_ACTIVITY,
        PLAN_MISSIONS_ACTIVITY,
        PLAN_TESTS_ACTIVITY,
        PLANNED_TESTS_ACTIVITY,
        PROMOTE_ACTIVITY,
        QUEUED_MISSIONS_ACTIVITY,
        READ_REQUEST_ACTIVITY,
        RETRY_BLANK_ACTIVITY,
        START_ACTIVITY,
    )

MAX_PARALLEL = 3
_ONCE = RetryPolicy(maximum_attempts=1)
_QUICK = timedelta(minutes=2)
STEPS = ("understand", "confirm", "plan_missions", "missions", "plan_tests", "build_tests")
CONFIRM_WAIT_DAYS = 14
SUITE_GENERATION_WORKFLOW = "SuiteGenerationWorkflow"


@workflow.defn(name=AUTHORING_WORKFLOW_NAME)
class AuthoringRunWorkflow:
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
                raise
            await workflow.execute_activity(
                FAIL_RUN_ACTIVITY,
                args=[run_id, "A step stopped responding. Press Resume to carry on from here."],
                start_to_close_timeout=_QUICK,
            )
            return "failed"

    async def _run(self, run_id: str, mode: str) -> str:
        if mode == "send":
            await self._add_test_cases(run_id)
            return "sent"
        if mode == "resume":
            start: str = await workflow.execute_activity(
                RESUME_POINT_ACTIVITY, run_id, start_to_close_timeout=_QUICK
            )
            start = "plan_tests" if start == "hunt" else start  # no hunt when authoring
        else:
            start = {"full": "understand", "missions": "missions", "tests": "plan_tests"}[mode]

        def doing(step: str) -> bool:
            return STEPS.index(step) >= STEPS.index(start)

        if doing("understand"):
            await self._bonus(READ_REQUEST_ACTIVITY, run_id, timedelta(minutes=5), heartbeat=False)
            outcome: str = await workflow.execute_activity(
                START_ACTIVITY, run_id, start_to_close_timeout=_QUICK
            )
            if outcome == "confirmed":  # nothing to ask: walk the request now
                self._confirmed = True
            elif outcome != "awaiting_confirmation":
                return outcome
        if doing("confirm") and not self._confirmed:
            try:
                await workflow.wait_condition(
                    lambda: self._confirmed, timeout=timedelta(days=CONFIRM_WAIT_DAYS)
                )
            except TimeoutError:
                return await workflow.execute_activity(
                    EXPIRE_RUN_ACTIVITY,
                    args=[run_id, CONFIRM_WAIT_DAYS],
                    start_to_close_timeout=_QUICK,
                )
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
            # A blank app (still loading, or failing to) gets another go.
            while await workflow.execute_activity(
                RETRY_BLANK_ACTIVITY, run_id, start_to_close_timeout=_QUICK
            ):
                await workflow.sleep(timedelta(seconds=30))
                await self._pool(
                    run_id,
                    QUEUED_MISSIONS_ACTIVITY,
                    RUN_MISSION_ACTIVITY,
                    REQUEUE_MISSION_ACTIVITY,
                )
            await workflow.execute_activity(
                FINISH_EXPLORING_ACTIVITY, run_id, start_to_close_timeout=_QUICK
            )

        tests = 0
        if doing("plan_tests"):
            tests = await self._bonus(
                PLAN_TESTS_ACTIVITY, run_id, timedelta(minutes=20), heartbeat=False
            )
        if tests or start == "build_tests":
            await self._pool(
                run_id, PLANNED_TESTS_ACTIVITY, BUILD_TEST_ACTIVITY, REQUEUE_TEST_ACTIVITY
            )
        else:  # nothing to try (planning said why): no test cases to write
            await workflow.execute_activity(
                FINISH_TESTING_ACTIVITY, run_id, start_to_close_timeout=_QUICK
            )
            return "no-tests"
        # Test cases first, then "tested": the run shows as working until its
        # test cases exist, and the app then opens Test cases on them.
        await self._add_test_cases(run_id)
        await workflow.execute_activity(
            FINISH_TESTING_ACTIVITY, run_id, start_to_close_timeout=_QUICK
        )
        await workflow.execute_activity(DONE_ACTIVITY, run_id, start_to_close_timeout=_QUICK)
        await self._bonus(REEL_ACTIVITY, run_id, timedelta(minutes=20), heartbeat=False)
        return "tested"

    async def _add_test_cases(self, run_id: str) -> None:
        """Add the proven scenarios, then write their test cases the way
        "Generate tests" does (one SuiteGenerationWorkflow per journey), and
        wait for them."""
        journeys = await self._bonus(
            PROMOTE_ACTIVITY, run_id, timedelta(minutes=10), heartbeat=False
        )
        for journey_id in journeys or []:
            try:
                await workflow.execute_child_workflow(
                    SUITE_GENERATION_WORKFLOW,
                    journey_id,
                    id=f"authoring-suite-{journey_id}-{workflow.uuid4()}",
                    task_queue=GENERATION_TASK_QUEUE,
                    # Pause/Stop end this run, never test-case writing under way.
                    parent_close_policy=workflow.ParentClosePolicy.ABANDON,
                )
            except Exception:  # noqa: BLE001 — "Generate tests" can still do it
                workflow.logger.warning("authoring: test-case generation did not finish")

    async def _bonus(
        self, activity: str, run_id: str, timeout: timedelta, heartbeat: bool = True
    ) -> Any:
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
                raise
            workflow.logger.warning("authoring step %s did not finish; continuing", activity)
            return None

    async def _pool(
        self, run_id: str, list_activity: str, run_activity: str, requeue_activity: str
    ) -> None:
        """Up to MAX_PARALLEL items at a time until none are waiting (as
        ExplorerRunWorkflow._pool)."""
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
                    raise failure
                if failure is not None:
                    await workflow.execute_activity(
                        requeue_activity, item_id, start_to_close_timeout=_QUICK
                    )
