"""DiscoveryWorkflow orchestration test (Story 2.1 AC 1, extended by 2.2/2.5).

Runs against Temporal's in-memory time-skipping test environment (no external
Temporal server needed) — same pattern as
`packages/workflows/tests/test_generation_workflow.py`. Proves the workflow
dispatches `DiscoveryActivity` -> `ApplicationModelBuilderActivity`, only
continuing past `DiscoveryActivity` when it returns `status=complete`, using
**fake** activity implementations — fast, no real Playwright/DB/Vault I/O.

`InferenceActivity` (Story 2.6) is intentionally not exercised here — the
workflow no longer invokes it (see `discovery_workflow.py`).
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from workflows import (
    DISCOVERY_TASK_QUEUE,
    ApplicationModelBuilderActivityInput,
    ApplicationModelBuilderActivityOutput,
    DiscoveryActivityInput,
    DiscoveryActivityOutput,
    DiscoveryWorkflow,
)


def _make_fake_discovery_activity(status: str):
    @activity.defn(name="DiscoveryActivity")
    async def fake_discovery_activity(input: DiscoveryActivityInput) -> DiscoveryActivityOutput:
        return DiscoveryActivityOutput(status=status, page_count=3)

    return fake_discovery_activity


def _make_fake_model_builder_activity(calls: list[str]):
    @activity.defn(name="ApplicationModelBuilderActivity")
    async def fake_model_builder_activity(
        input: ApplicationModelBuilderActivityInput,
    ) -> ApplicationModelBuilderActivityOutput:
        calls.append("model_builder")
        return ApplicationModelBuilderActivityOutput(component_count=1)

    return fake_model_builder_activity


async def _run_workflow(discovery_status: str, calls: list[str]) -> str:
    discovery_run_id = str(uuid.uuid4())
    application_id = str(uuid.uuid4())

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=DISCOVERY_TASK_QUEUE,
            workflows=[DiscoveryWorkflow],
            activities=[
                _make_fake_discovery_activity(discovery_status),
                _make_fake_model_builder_activity(calls),
            ],
        ):
            return await env.client.execute_workflow(
                DiscoveryWorkflow.run,
                args=[discovery_run_id, application_id, "applications/org-1/secret-abc"],
                id=f"discovery-test-{uuid.uuid4()}",
                task_queue=DISCOVERY_TASK_QUEUE,
            )


@pytest.mark.asyncio
async def test_discovery_workflow_chains_model_builder_when_complete() -> None:
    calls: list[str] = []
    assert await _run_workflow("complete", calls) == "complete"
    assert calls == ["model_builder"]


@pytest.mark.asyncio
async def test_discovery_workflow_skips_model_builder_when_failed() -> None:
    calls: list[str] = []
    assert await _run_workflow("failed", calls) == "failed"
    assert calls == []
