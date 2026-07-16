"""Generation worker process — Story 1.1 scaffold.

Registers and runs only the no-op `GenerationWorkflow` shell against a local
Temporal server (`temporal server start-dev` or a docker-compose service —
dev ergonomics only, not the deferred SaaS/on-prem Temporal-hosting decision).
Zero Activities are registered yet — ScenarioGenerationActivity and
PlaywrightGenerationActivity land in Epic 4.

Run with: uv run --package generation-worker python -m generation_worker.worker
"""

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker
from workflows import GENERATION_TASK_QUEUE, GenerationWorkflow

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")


async def main() -> None:
    client = await Client.connect(TEMPORAL_ADDRESS)
    worker = Worker(
        client,
        task_queue=GENERATION_TASK_QUEUE,
        workflows=[GenerationWorkflow],
        activities=[],
    )
    print(f"Generation worker polling task queue '{GENERATION_TASK_QUEUE}' at {TEMPORAL_ADDRESS}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
