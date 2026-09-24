"""GenerationWorkflow — graduated from Story 1.1's no-op shell by Story 4.1.

Contains zero I/O itself (AD-2): only calls to Activities. `[CORRECTED
2026-07-21]` Started by the "Continue to Scenarios" trigger endpoint (Story
4.1, Task 5), one execution per candidate Journey — not automatically by
`InferenceActivity` at Journey-creation time, which is what this shell's
original Story 1.1/2.5 docstring described. Playwright generation (Story
4.2) is a separate, independently-triggered workflow dispatch, not part of
this run — see Story 4.1/4.2's 2026-07-21 Change Log entries.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

GENERATION_TASK_QUEUE = "generation-task-queue"
SCENARIO_GENERATION_ACTIVITY_NAME = "ScenarioGenerationActivity"


@dataclass
class ScenarioGenerationActivityInput:
    journey_id: str
    # `Scenario.source` — 'discovery' (default, the normal crawler pipeline)
    # or 'nl' (a live-exploration-created Journey, see
    # `LiveExplorationTestWorkflow`), so the frontend's "NL Test Case" badge
    # applies to those too.
    source: str = "discovery"
    # Only non-empty for a live-exploration Journey whose originating prompt
    # stated an explicit total/per-category scenario count (see
    # `PromptAnalysisResult.requested_scenario_counts`) — overrides
    # `generate_scenarios`'s normal free-running per-type count.
    requested_scenario_counts: dict[str, int] = field(default_factory=dict)
    # Only non-empty for a live-exploration Journey whose originating prompt
    # stated a concrete literal value (see
    # `PromptAnalysisResult.provided_test_data`) — applied to the happy-path
    # Scenario's matching test_data field(s) only; a negative/edge Scenario
    # keeps its own intent-based default fill, since its whole point is a
    # deliberately different or missing value.
    provided_test_data: dict[str, str] = field(default_factory=dict)


@workflow.defn(name="GenerationWorkflow")
class GenerationWorkflow:
    @workflow.run
    async def run(self, journey_id: str) -> list[str]:
        # `[FIXED]` ScenarioGenerationActivity failing used to fail this
        # whole Workflow — Temporal's own `RetryPolicy` below already gives
        # it 3 genuine attempts first (each one logs and records the
        # failure on the Journey before re-raising, see the Activity's own
        # comment), so by the time `ActivityError` reaches here every
        # reasonable retry has already happened; this is the "truly out of
        # options" case, not the first failure. A Journey whose generation
        # never Recovers used to leave this Workflow permanently "Failed"
        # in Temporal and the Journey stuck at 0 Scenarios with the Review
        # Scenarios screen's `journeysCovered >= journeys.length` check
        # unable to ever pass — the progress bar spun forever. Completing
        # cleanly instead lets every other candidate Journey's own
        # Workflow keep going (they were always independent — one per
        # Journey), and lets the frontend see this one as concluded
        # (Journey.generation_error already recorded by the Activity) and
        # move on rather than waiting on it forever.
        try:
            return await workflow.execute_activity(
                SCENARIO_GENERATION_ACTIVITY_NAME,
                ScenarioGenerationActivityInput(journey_id=journey_id),
                # Generous for LLM latency, matching InferenceActivity's own
                # generous timeout in DiscoveryWorkflow.
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
                result_type=list[str],
            )
        except ActivityError:
            workflow.logger.error(
                "GenerationWorkflow: journey_id=%s exhausted every retry — see "
                "Journey.generation_error for what ScenarioGenerationActivity hit",
                journey_id,
            )
            return []
