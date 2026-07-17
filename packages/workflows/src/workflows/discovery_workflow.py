"""DiscoveryWorkflow — bounded execution shell for a DiscoveryRun (AD-1).

Story 1.3 absorbed the former Story 1.5's trigger: onboarding an Application
starts this workflow immediately, in the same request — no separate "start
discovery" action. Story 2.1 dispatches the first Activity call; contains
zero I/O itself (AD-2) — only calls to Activities, whose real
implementations live in `apps/workers/discovery` (the concrete adapter,
never imported here — only registered names and input/output shapes are).
Story 2.2/2.3/2.4 grow `DiscoveryActivity` into real, bounded autonomous
exploration.

`InferenceActivity` (Story 2.5) is intentionally not dispatched from here —
disconnected so Discovery (2.1-2.4) stands on its own and reaches `complete`/
`failed` without depending on Story 2.5's AI provider being configured.
`InferenceActivityInput`/`INFERENCE_ACTIVITY_NAME` stay exported: the
Activity itself still exists and is invoked directly (see
`apps/workers/discovery/tests/test_inference_activity.py`), just not chained
here. Re-wire with a second `workflow.execute_activity` call when 2.5 is
ready to be part of this workflow again.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow

DISCOVERY_TASK_QUEUE = "discovery-task-queue"
DISCOVERY_ACTIVITY_NAME = "DiscoveryActivity"
INFERENCE_ACTIVITY_NAME = "InferenceActivity"


@dataclass
class DiscoveryActivityInput:
    discovery_run_id: str
    application_id: str
    secret_ref: str


@dataclass
class DiscoveryActivityOutput:
    status: str
    evidence_count: int


@dataclass
class InferenceActivityInput:
    discovery_run_id: str


@workflow.defn(name="DiscoveryWorkflow")
class DiscoveryWorkflow:
    @workflow.run
    async def run(self, discovery_run_id: str, application_id: str, secret_ref: str) -> str:
        discovery_result = await workflow.execute_activity(
            DISCOVERY_ACTIVITY_NAME,
            DiscoveryActivityInput(
                discovery_run_id=discovery_run_id,
                application_id=application_id,
                secret_ref=secret_ref,
            ),
            # Story 2.3 removed the crawl's iteration cap by explicit product
            # decision (accepted risk — no bound on a real site's traversal
            # time), so a short start_to_close_timeout would kill and restart
            # a merely-large-but-healthy crawl from scratch, forever. A long
            # timeout plus heartbeating lets Temporal distinguish "still
            # working" from "worker actually died" correctly.
            start_to_close_timeout=timedelta(hours=6),
            heartbeat_timeout=timedelta(minutes=2),
            result_type=DiscoveryActivityOutput,
        )

        return discovery_result.status
