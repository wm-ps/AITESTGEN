"""GenerationWorkflow shell test — runs the no-op workflow against Temporal's
in-memory time-skipping test environment (no external Temporal server needed).

AD-2 (workflow performs no I/O) is enforced by Temporal's workflow sandbox at
runtime, not asserted here; this test only verifies the shell starts and
completes. Keep the workflow I/O-free as later workflows are built on it.
"""

import uuid

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from workflows import GENERATION_TASK_QUEUE, GenerationWorkflow


@pytest.mark.asyncio
async def test_generation_workflow_completes() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=GENERATION_TASK_QUEUE,
            workflows=[GenerationWorkflow],
        ):
            result = await env.client.execute_workflow(
                GenerationWorkflow.run,
                id=f"generation-test-{uuid.uuid4()}",
                task_queue=GENERATION_TASK_QUEUE,
            )
            assert result == "ok"
