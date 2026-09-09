"""Temporal client wiring — Story 1.1 scaffold.

Confirms `apps/api` can start and confirm completion of a Temporal workflow.
No real trigger endpoint exists yet (not required until Epic 2/3) — see
`scripts/temporal_smoke_test.py` for the dev-only proof-of-life check.
"""

import os

from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest
from temporalio.client import Client
from workflows import GENERATION_TASK_QUEUE

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")

__all__ = ["GENERATION_TASK_QUEUE", "TEMPORAL_ADDRESS", "get_temporal_client", "has_pollers"]


async def get_temporal_client() -> Client:
    return await Client.connect(TEMPORAL_ADDRESS)


async def has_pollers(
    client: Client, task_queue: str, task_queue_type: int = TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW
) -> bool:
    """Whether any worker is currently polling `task_queue` right now — the
    same signal `temporal task-queue describe` uses, queried directly
    instead of guessing from a client-side timeout. Starting a workflow
    always succeeds regardless of whether a worker exists to run it, so this
    is the only way to tell "API up, worker pod down" apart from "worker is
    just busy" before the caller commits to it. A poller that crashed rather
    than shutting down cleanly drops out of this within Temporal's own
    staleness window (a few minutes), not instantly.

    `[FIXED]` `task_queue_type` defaults to WORKFLOW (every other caller's
    queue has a workflow-type worker on it) but must be passed explicitly as
    ACTIVITY for `LIVE_EXPLORATION_TASK_QUEUE` — its worker
    (`generation_worker/worker.py`) is registered activity-only
    (`LiveExploreActivity`/`LiveHealActivity`, no `workflows=[...]`), so it
    never has a WORKFLOW-type poller at all; checking for one there always
    returned zero regardless of whether the worker was actually healthy.
    """
    response = await client.workflow_service.describe_task_queue(
        DescribeTaskQueueRequest(
            namespace=client.namespace,
            task_queue=TaskQueue(name=task_queue),
            task_queue_type=task_queue_type,
        )
    )
    return len(response.pollers) > 0
