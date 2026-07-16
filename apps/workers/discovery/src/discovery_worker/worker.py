"""Discovery worker process — Story 1.3 scaffold.

Registers and runs only the no-op `DiscoveryWorkflow` shell against a local
Temporal server. Zero Activities are registered yet — DiscoveryActivity
(Playwright exploration) lands in Epic 2.

Run with: uv run --package discovery-worker python -m discovery_worker.worker
"""

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker
from workflows import DISCOVERY_TASK_QUEUE, DiscoveryWorkflow

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")


async def main() -> None:
    client = await Client.connect(TEMPORAL_ADDRESS)
    worker = Worker(
        client,
        task_queue=DISCOVERY_TASK_QUEUE,
        workflows=[DiscoveryWorkflow],
        activities=[],
    )
    print(f"Discovery worker polling task queue '{DISCOVERY_TASK_QUEUE}' at {TEMPORAL_ADDRESS}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
