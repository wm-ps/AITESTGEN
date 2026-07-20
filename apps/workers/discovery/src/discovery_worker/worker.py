"""Discovery worker process — Story 1.3 scaffold; Story 2.1/2.2 add the real
`DiscoveryActivity`; Story 2.5 adds `ApplicationModelBuilderActivity`; Story
2.6 adds `InferenceActivity`.

Registers `DiscoveryWorkflow` and all three Activities against a local
Temporal server.

Run with: uv run --package discovery-worker python -m discovery_worker.worker
"""

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker
from workflows import DISCOVERY_TASK_QUEUE, DiscoveryWorkflow

from discovery_worker.activities import (
    application_model_builder_activity,
    discovery_activity,
    inference_activity,
)

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")


async def main() -> None:
    client = await Client.connect(TEMPORAL_ADDRESS)
    worker = Worker(
        client,
        task_queue=DISCOVERY_TASK_QUEUE,
        workflows=[DiscoveryWorkflow],
        activities=[discovery_activity, application_model_builder_activity, inference_activity],
    )
    print(f"Discovery worker polling task queue '{DISCOVERY_TASK_QUEUE}' at {TEMPORAL_ADDRESS}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
