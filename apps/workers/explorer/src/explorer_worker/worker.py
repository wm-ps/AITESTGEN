"""Explorer worker process.

Run with: uv run --env-file .env --package explorer-worker python -m explorer_worker.worker
"""

import asyncio
import logging
import os

from explorer_core import EXPLORER_TASK_QUEUE
from temporalio.client import Client
from temporalio.worker import Worker
from workflows import VerifyCredentialsWorkflow

from explorer_worker.activities import (
    breadth_activity,
    build_test_activity,
    expire_run_activity,
    fail_run_activity,
    finish_exploring_activity,
    finish_testing_activity,
    hunt_activity,
    plan_missions_activity,
    plan_tests_activity,
    planned_tests_activity,
    promote_activity,
    queued_missions_activity,
    reel_activity,
    requeue_mission_activity,
    requeue_test_activity,
    resume_point_activity,
    run_mission_activity,
    understand_app_activity,
    verify_credentials_activity,
)
from explorer_worker.authoring.activities import ACTIVITIES as AUTHORING_ACTIVITIES
from explorer_worker.authoring.workflow import AuthoringRunWorkflow
from explorer_worker.workflow import ExplorerRunWorkflow

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
# Each run drives a real browser plus many model calls — keep it modest.
MAX_CONCURRENT_ACTIVITIES = int(os.environ.get("EXPLORER_WORKER_MAX_CONCURRENT_ACTIVITIES", "8"))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    client = await Client.connect(TEMPORAL_ADDRESS)
    worker = Worker(
        client,
        task_queue=EXPLORER_TASK_QUEUE,
        # Also the "Start discovery" login pre-flight: Explorer does discovery.
        # Authoring (a user's request) runs on Explorer too, on its own path.
        workflows=[ExplorerRunWorkflow, AuthoringRunWorkflow, VerifyCredentialsWorkflow],
        activities=[
            promote_activity,
            fail_run_activity,
            expire_run_activity,
            understand_app_activity,
            hunt_activity,
            breadth_activity,
            reel_activity,
            plan_missions_activity,
            queued_missions_activity,
            requeue_mission_activity,
            run_mission_activity,
            finish_exploring_activity,
            plan_tests_activity,
            planned_tests_activity,
            build_test_activity,
            requeue_test_activity,
            finish_testing_activity,
            resume_point_activity,
            verify_credentials_activity,
            *AUTHORING_ACTIVITIES,
        ],
        max_concurrent_activities=MAX_CONCURRENT_ACTIVITIES,
    )
    print(f"Explorer worker polling task queue '{EXPLORER_TASK_QUEUE}' at {TEMPORAL_ADDRESS}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
