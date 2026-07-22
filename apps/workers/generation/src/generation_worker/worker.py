"""Generation worker process — Story 1.1 scaffold, graduated by Story 4.1.

Registers `GenerationWorkflow` and `ScenarioGenerationActivity` against a
local Temporal server. `PlaywrightGenerationActivity` lands in Story 4.2.

Run with: uv run --package generation-worker python -m generation_worker.worker
"""

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker
from workflows import GENERATION_TASK_QUEUE, GenerationWorkflow

from generation_worker.activities import scenario_generation_activity

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    client = await Client.connect(TEMPORAL_ADDRESS)
    worker = Worker(
        client,
        task_queue=GENERATION_TASK_QUEUE,
        workflows=[GenerationWorkflow],
        activities=[scenario_generation_activity],
    )
    print(f"Generation worker polling task queue '{GENERATION_TASK_QUEUE}' at {TEMPORAL_ADDRESS}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
