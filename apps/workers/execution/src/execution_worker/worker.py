"""Execution worker process — Run All Tests feature, plus CleanupWorkflow.

Registers `ApplicationTestExecutionWorkflow` and its three Activities
against a local Temporal server, on its own task queue
(`execution-task-queue`) — a dedicated worker, separate from
discovery/generation, so this feature's resource use (real browser
processes per test, a Node toolchain) scales and fails independently of
scenario/Playwright-code generation.

Also registers `CleanupWorkflow` and its two Activities (deleted-project
purge, AD-2) on the same task queue — that job is light (DB deletes plus a
handful of Vault/S3 calls) and needs every dependency this worker already
has (`secrets-client`, `object-store`, `sqlmodel`/`psycopg`), so it doesn't
warrant its own deployment.

`max_workers` on the activity executor doubles as this worker's
cross-TestRun concurrency ceiling (decision: bounded independently of the
per-run `asyncio.Semaphore` in `ApplicationTestExecutionWorkflow`, which
only bounds concurrency *within* one run) — configurable via
`EXECUTION_WORKER_MAX_CONCURRENT_ACTIVITIES` since the right number depends
on the host's real CPU/memory budget for concurrent browser processes, not
something to hardcode.

Run with: uv run --package execution-worker python -m execution_worker.worker
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker
from workflows import EXECUTION_TASK_QUEUE, ApplicationTestExecutionWorkflow, CleanupWorkflow

from execution_worker.activities import (
    execute_test_activity,
    finalize_test_run_activity,
    prepare_test_run_activity,
)
from execution_worker.cleanup_activities import (
    find_purge_candidates_activity,
    purge_application_activity,
)
from execution_worker.project_cache import sweep_stale_project_dirs

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
MAX_CONCURRENT_ACTIVITIES = int(os.environ.get("EXECUTION_WORKER_MAX_CONCURRENT_ACTIVITIES", "20"))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    # A directory left behind by a run that crashed before its own
    # FinalizeTestRunActivity could clean up after itself — swept once at
    # startup rather than left to accumulate indefinitely.
    sweep_stale_project_dirs()
    client = await Client.connect(TEMPORAL_ADDRESS)
    worker = Worker(
        client,
        task_queue=EXECUTION_TASK_QUEUE,
        workflows=[ApplicationTestExecutionWorkflow, CleanupWorkflow],
        activities=[
            prepare_test_run_activity,
            execute_test_activity,
            finalize_test_run_activity,
            find_purge_candidates_activity,
            purge_application_activity,
        ],
        # find_purge_candidates_activity/purge_application_activity are sync
        # (plain `def`, not `async def`) — Temporal requires an explicit
        # activity_executor to run any non-async activity in a thread.
        activity_executor=ThreadPoolExecutor(max_workers=MAX_CONCURRENT_ACTIVITIES),
        max_concurrent_activities=MAX_CONCURRENT_ACTIVITIES,
    )
    print(
        f"Execution worker polling task queue '{EXECUTION_TASK_QUEUE}' at {TEMPORAL_ADDRESS} "
        f"(max_concurrent_activities={MAX_CONCURRENT_ACTIVITIES})"
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
