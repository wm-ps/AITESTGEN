"""Generation worker process — Story 1.1 scaffold, graduated by Story 4.1,
extended by Story 4.2.

Registers `GenerationWorkflow`/`ScenarioGenerationActivity` (Story 4.1) and
`SuiteGenerationWorkflow`/`EnsureTestSuiteActivity`/`PlaywrightGenerationActivity`
(Story 4.2) against a local Temporal server, on the same task queue (one
worker process, two independent workflow types).

Run with: uv run --package generation-worker python -m generation_worker.worker
"""

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker
from workflows import GENERATION_TASK_QUEUE, GenerationWorkflow, SuiteGenerationWorkflow

from generation_worker.activities import (
    ensure_test_suite_activity,
    finalize_suite_generation_activity,
    playwright_generation_activity,
    scenario_generation_activity,
)

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
MAX_CONCURRENT_ACTIVITIES = int(os.environ.get("GENERATION_WORKER_MAX_CONCURRENT_ACTIVITIES", "5"))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    client = await Client.connect(TEMPORAL_ADDRESS)
    worker = Worker(
        client,
        task_queue=GENERATION_TASK_QUEUE,
        workflows=[GenerationWorkflow, SuiteGenerationWorkflow],
        activities=[
            scenario_generation_activity,
            ensure_test_suite_activity,
            playwright_generation_activity,
            finalize_suite_generation_activity,
        ],
        max_concurrent_activities=MAX_CONCURRENT_ACTIVITIES,
    )
    print(f"Generation worker polling task queue '{GENERATION_TASK_QUEUE}' at {TEMPORAL_ADDRESS}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
