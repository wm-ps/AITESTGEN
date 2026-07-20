"""DiscoveryWorkflow — bounded execution shell for a DiscoveryRun (AD-1).

Story 1.3 absorbed the former Story 1.5's trigger: onboarding an Application
starts this workflow immediately, in the same request — no separate "start
discovery" action. Story 2.1 dispatches the first Activity call; contains
zero I/O itself (AD-2) — only calls to Activities, whose real
implementations live in `apps/workers/discovery` (the concrete adapter,
never imported here — only registered names and input/output shapes are).
Story 2.2/2.3/2.4 grow `DiscoveryActivity` into real, bounded autonomous
exploration.

Sprint Change Proposal (2026-07-18): the pipeline is now three activities,
dispatched in order, each only when the prior one leaves the run in a state
worth continuing from:
`DiscoveryActivity` -> `ApplicationModelBuilderActivity` (Story 2.5) ->
`InferenceActivity` (Story 2.6) — only when `DiscoveryActivity` returns
`status=complete` (never `failed`, e.g. `session_expired`).

`InferenceActivity` gets an explicit `start_to_close_timeout` (LLM calls are
slow) and a bounded `RetryPolicy` (the first use of one in this codebase) —
an unbounded default retry against a slow/flaky AI provider would otherwise
risk silent repeated paid calls and a workflow that never resolves.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

DISCOVERY_TASK_QUEUE = "discovery-task-queue"
DISCOVERY_ACTIVITY_NAME = "DiscoveryActivity"
APPLICATION_MODEL_BUILDER_ACTIVITY_NAME = "ApplicationModelBuilderActivity"
INFERENCE_ACTIVITY_NAME = "InferenceActivity"


@dataclass
class DiscoveryActivityInput:
    discovery_run_id: str
    application_id: str
    secret_ref: str


@dataclass
class DiscoveryActivityOutput:
    status: str
    page_count: int


@dataclass
class ApplicationModelBuilderActivityInput:
    discovery_run_id: str


@dataclass
class ApplicationModelBuilderActivityOutput:
    component_count: int


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

        if discovery_result.status != "complete":
            return discovery_result.status

        await workflow.execute_activity(
            APPLICATION_MODEL_BUILDER_ACTIVITY_NAME,
            ApplicationModelBuilderActivityInput(discovery_run_id=discovery_run_id),
            start_to_close_timeout=timedelta(minutes=10),
            result_type=ApplicationModelBuilderActivityOutput,
        )

        await workflow.execute_activity(
            INFERENCE_ACTIVITY_NAME,
            InferenceActivityInput(discovery_run_id=discovery_run_id),
            # Generous for LLM latency — InferenceActivity may make several
            # sequential per-batch calls for a large Application (Story 2.6's
            # navigation-graph clustering).
            # ponytail: batches run sequentially within one Activity attempt,
            # not concurrently — the simplest thing that satisfies this
            # story's tasks. If a very-many-batch Application makes this
            # timeout too tight, dispatching batches concurrently (they're
            # independent) is the upgrade path, not a longer timeout alone.
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=list[str],
        )

        return discovery_result.status
