"""GenerationWorkflow — Story 1.1 proof-of-life shell.

Contains zero I/O (AD-2): only Workflow-safe primitives, no Activity calls
yet. Story 2.5's InferenceActivity graduates this shell into the real
GenerationWorkflow (Scenario generation -> Playwright generation) —
`[UPDATED 2026-07-15]` originally Story 3.2's job; that story was removed
when the approval gate was cut. Name and structure it so it can grow into
that role rather than being throwaway code.
"""

from temporalio import workflow

GENERATION_TASK_QUEUE = "generation-task-queue"


@workflow.defn(name="GenerationWorkflow")
class GenerationWorkflow:
    @workflow.run
    async def run(self) -> str:
        return "ok"
