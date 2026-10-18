"""ExplorerRunWorkflow's mission pool with fake activities: every queued
mission runs once, never more than MAX_PARALLEL at a time, then it finishes."""

import asyncio
import uuid

from explorer_worker.activities import (
    BREADTH_ACTIVITY,
    FINISH_ACTIVITY,
    HUNT_ACTIVITY,
    QUEUED_MISSIONS_ACTIVITY,
    RUN_MISSION_ACTIVITY,
)
from explorer_worker.workflow import MAX_PARALLEL, ExplorerRunWorkflow
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker


async def test_mission_pool_runs_everything_with_bounded_parallelism():
    queued = [f"m{i}" for i in range(7)]
    ran: list[str] = []
    live = 0
    peak = 0
    finished: list[str] = []

    @activity.defn(name=QUEUED_MISSIONS_ACTIVITY)
    async def fake_queued(run_id: str) -> list[str]:
        return [m for m in queued if m not in ran]

    @activity.defn(name=RUN_MISSION_ACTIVITY)
    async def fake_run(run_id: str, mission_id: str) -> str:
        nonlocal live, peak
        ran.append(mission_id)
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.05)
        live -= 1
        return "done"

    @activity.defn(name=HUNT_ACTIVITY)
    async def fake_hunt(run_id: str) -> int:
        return 0

    @activity.defn(name=BREADTH_ACTIVITY)
    async def fake_breadth(run_id: str) -> None:
        return None

    @activity.defn(name=FINISH_ACTIVITY)
    async def fake_finish(run_id: str) -> None:
        finished.append(run_id)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-explorer",
            workflows=[ExplorerRunWorkflow],
            activities=[fake_queued, fake_run, fake_finish, fake_hunt, fake_breadth],
        ):
            result = await env.client.execute_workflow(
                ExplorerRunWorkflow.run,
                args=["run-1", "missions"],
                id=f"wf-{uuid.uuid4()}",
                task_queue="test-explorer",
            )
    assert result == "explored"
    assert sorted(ran) == sorted(queued)
    assert peak <= MAX_PARALLEL
    assert finished == ["run-1"]


async def test_cancelling_the_run_stops_it_instead_of_skipping_ahead():
    """Pause/Stop cancel the workflow: a cancelled step must end the run,
    not be treated as a failed bonus step and carry on to the next one."""
    from explorer_worker.activities import PLAN_TESTS_ACTIVITY

    started = asyncio.Event()
    later: list[str] = []

    @activity.defn(name=QUEUED_MISSIONS_ACTIVITY)
    async def fake_queued(run_id: str) -> list[str]:
        return []

    @activity.defn(name=FINISH_ACTIVITY)
    async def fake_finish(run_id: str) -> None:
        return None

    @activity.defn(name=HUNT_ACTIVITY)
    async def slow_hunt(run_id: str) -> int:
        started.set()
        while True:  # until cancelled, heartbeating like the real one
            activity.heartbeat()
            await asyncio.sleep(0.1)

    @activity.defn(name=BREADTH_ACTIVITY)
    async def fake_breadth(run_id: str) -> None:
        later.append("breadth")

    @activity.defn(name=PLAN_TESTS_ACTIVITY)
    async def fake_plan(run_id: str) -> int:
        later.append("plan_tests")
        return 0

    async with await WorkflowEnvironment.start_local() as env:
        async with Worker(
            env.client,
            task_queue="test-explorer",
            workflows=[ExplorerRunWorkflow],
            activities=[fake_queued, fake_finish, slow_hunt, fake_breadth, fake_plan],
        ):
            handle = await env.client.start_workflow(
                ExplorerRunWorkflow.run,
                args=["run-1", "missions"],
                id=f"wf-{uuid.uuid4()}",
                task_queue="test-explorer",
            )
            await asyncio.wait_for(started.wait(), 30)
            await handle.cancel()
            try:
                await handle.result()
            except Exception:  # the cancellation itself
                pass
    assert later == []
