"""AutofillScenarioTestDataWorkflow — Scenarios tab "Auto-generate" button.

Fills any still-blank test_data fields on one Scenario with the same
deterministic, non-AI defaults PlaywrightGenerationActivity already applies
at suite-generation time (`_resolve_scenario_defaults_sync`,
apps/workers/generation/src/generation_worker/activities.py) — this just
lets a reviewer trigger that same fill early, before generation, instead of
only ever seeing it happen implicitly. No AI call, no typecheck retry loop —
a single fast Activity, same start+poll shape as RegenerateTestAssetWorkflow
for frontend consistency even though this one resolves in well under a
second.

Workflow id convention: `autofill-{scenario_id}` (mirrors
`regenerate-{scenario_id}`) — a duplicate click while one is already RUNNING
is a no-op start, same as regenerate's.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from workflows.generation_workflow import GENERATION_TASK_QUEUE

AUTOFILL_SCENARIO_TEST_DATA_ACTIVITY_NAME = "AutofillScenarioTestDataActivity"


@dataclass
class AutofillScenarioTestDataActivityInput:
    scenario_id: str


@dataclass
class AutofillScenarioTestDataResult:
    status: str  # complete | failed
    test_data: list[dict] = field(default_factory=list)
    # Plain-language only — same convention RegenerateTestAssetResult's
    # error_message uses.
    error_message: str | None = None


@workflow.defn(name="AutofillScenarioTestDataWorkflow")
class AutofillScenarioTestDataWorkflow:
    @workflow.run
    async def run(
        self, input: AutofillScenarioTestDataActivityInput
    ) -> AutofillScenarioTestDataResult:
        try:
            test_data: list[dict] = await workflow.execute_activity(
                AUTOFILL_SCENARIO_TEST_DATA_ACTIVITY_NAME,
                input,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except Exception as exc:  # noqa: BLE001 — surfaced in the result, not re-raised
            workflow.logger.warning(
                "AutofillScenarioTestDataWorkflow: scenario_id=%s failed: %s",
                input.scenario_id,
                exc,
            )
            return AutofillScenarioTestDataResult(
                status="failed",
                error_message="Could not auto-fill test data — try again.",
            )
        return AutofillScenarioTestDataResult(status="complete", test_data=test_data)


__all__ = [
    "AUTOFILL_SCENARIO_TEST_DATA_ACTIVITY_NAME",
    "GENERATION_TASK_QUEUE",
    "AutofillScenarioTestDataActivityInput",
    "AutofillScenarioTestDataResult",
    "AutofillScenarioTestDataWorkflow",
]
