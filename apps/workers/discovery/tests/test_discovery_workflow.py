"""DiscoveryWorkflow orchestration test (Story 2.1 AC 1, extended by Story 2.2).

Runs against Temporal's in-memory time-skipping test environment (no external
Temporal server needed) — same pattern as
`packages/workflows/tests/test_generation_workflow.py`. Proves the workflow
dispatches to the registered `"DiscoveryActivity"` activity with the right
input shape and returns its status, using a **fake** activity implementation
— fast, no real Playwright/DB/Vault I/O. `InferenceActivity` (Story 2.5) is
intentionally not chained here (see `discovery_workflow.py`'s module
docstring) and is covered standalone by `test_inference_activity.py`.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from workflows import (
    DISCOVERY_TASK_QUEUE,
    DiscoveryActivityInput,
    DiscoveryActivityOutput,
    DiscoveryWorkflow,
)


def _make_fake_discovery_activity(status: str):
    @activity.defn(name="DiscoveryActivity")
    async def fake_discovery_activity(input: DiscoveryActivityInput) -> DiscoveryActivityOutput:
        return DiscoveryActivityOutput(status=status, evidence_count=3)

    return fake_discovery_activity


async def _run_workflow(discovery_status: str) -> str:
    discovery_run_id = str(uuid.uuid4())
    application_id = str(uuid.uuid4())

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=DISCOVERY_TASK_QUEUE,
            workflows=[DiscoveryWorkflow],
            activities=[_make_fake_discovery_activity(discovery_status)],
        ):
            return await env.client.execute_workflow(
                DiscoveryWorkflow.run,
                args=[discovery_run_id, application_id, "applications/org-1/secret-abc"],
                id=f"discovery-test-{uuid.uuid4()}",
                task_queue=DISCOVERY_TASK_QUEUE,
            )


@pytest.mark.asyncio
async def test_discovery_workflow_returns_complete_status() -> None:
    assert await _run_workflow("complete") == "complete"


@pytest.mark.asyncio
async def test_discovery_workflow_returns_failed_status() -> None:
    assert await _run_workflow("failed") == "failed"
