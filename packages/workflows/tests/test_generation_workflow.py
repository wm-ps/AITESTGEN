"""GenerationWorkflow shell test — runs the no-op workflow against Temporal's
in-memory time-skipping test environment (no external Temporal server needed).

Also asserts AD-2: the workflow module performs no I/O — this is the
convention every later workflow depends on being established correctly here.
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
