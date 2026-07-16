"""DiscoveryWorkflow — bounded execution shell for a DiscoveryRun (AD-1).

Story 1.3 absorbs the former Story 1.5's trigger: onboarding an Application
starts this workflow immediately, in the same request — no separate "start
discovery" action. Contains zero I/O (AD-2): only Workflow-safe primitives.
Story 2.1+ grows this into the real autonomous-exploration orchestration
(DiscoveryActivity, stop conditions); this shell only needs to exist and be
startable/observable via Temporal CLI/Web UI for this story.
"""

from temporalio import workflow

DISCOVERY_TASK_QUEUE = "discovery-task-queue"


@workflow.defn(name="DiscoveryWorkflow")
class DiscoveryWorkflow:
    @workflow.run
    async def run(self, application_id: str) -> str:
        return "started"
