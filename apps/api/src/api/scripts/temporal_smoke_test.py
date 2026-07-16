"""Dev-only smoke test (Story 1.1, AC4/Task 4).

Starts the no-op GenerationWorkflow via the apps/api-side Temporal client and
confirms it completes. Requires a local Temporal server
(`temporal server start-dev`) and the generation worker
(`uv run --package generation-worker python -m generation_worker.worker`)
both running.

Run with: uv run --package api python -m api.scripts.temporal_smoke_test
"""

import asyncio
import uuid

from workflows import GenerationWorkflow

from api.temporal_client import GENERATION_TASK_QUEUE, get_temporal_client


async def main() -> None:
    client = await get_temporal_client()
    workflow_id = f"generation-smoke-test-{uuid.uuid4()}"
    result = await client.execute_workflow(
        GenerationWorkflow.run,
        id=workflow_id,
        task_queue=GENERATION_TASK_QUEUE,
    )
    assert result == "ok", f"expected 'ok', got {result!r}"
    print(f"Temporal smoke test OK — workflow {workflow_id} completed with result={result!r}")


if __name__ == "__main__":
    asyncio.run(main())
