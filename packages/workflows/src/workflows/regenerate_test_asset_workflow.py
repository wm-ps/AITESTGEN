"""RegenerateTestAssetWorkflow — Edit Test Data (Test Suite page).

Regenerates exactly one Scenario's current TestAsset after its test_data
changed, as a targeted AI edit against the existing code (never a blind
rewrite) — see `regenerate_test_asset_activity`'s own docstring
(apps/workers/generation/src/generation_worker/activities.py) for the
generation contract, and `supersede_test_asset` for how the new TestAsset
replaces the old one. A single Activity call; a `@workflow.query` lets
apps/api's polling endpoint report progress the same way
`AddTestCaseWorkflow.get_status` already does, since this can take as long
as a real AI + typecheck round trip.

Workflow id convention: `regenerate-{scenario_id}` (deterministic, not
content-derived, mirrors `heal-{test_result_id}`'s own convention) — a
duplicate click while one is already RUNNING is rejected outright
(`WorkflowIDReusePolicy`'s default only rejects a still-open execution; a
later request after this one has CLOSED is a perfectly ordinary new
regenerate and is allowed to proceed). apps/api reads a rejection as
`WorkflowAlreadyStartedError` and reports "already regenerating" rather than
an error.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from workflows.generation_workflow import GENERATION_TASK_QUEUE

REGENERATE_TEST_ASSET_ACTIVITY_NAME = "RegenerateTestAssetActivity"


@dataclass
class RegenerateTestAssetActivityInput:
    scenario_id: str


@dataclass
class RegenerateTestAssetStatus:
    status: str  # running | complete | failed


@dataclass
class RegenerateTestAssetResult:
    status: str  # complete | failed
    test_asset_id: str | None = None
    # Plain-language only, never raw AI/typecheck output — same convention
    # AddTestCaseWorkflow's own TestCaseGenerationResult.error_message uses.
    error_message: str | None = None


@workflow.defn(name="RegenerateTestAssetWorkflow")
class RegenerateTestAssetWorkflow:
    def __init__(self) -> None:
        self._status = "running"

    @workflow.query
    def get_status(self) -> RegenerateTestAssetStatus:
        return RegenerateTestAssetStatus(status=self._status)

    @workflow.run
    async def run(self, input: RegenerateTestAssetActivityInput) -> RegenerateTestAssetResult:
        try:
            test_asset_id: str = await workflow.execute_activity(
                REGENERATE_TEST_ASSET_ACTIVITY_NAME,
                input,
                # Generous for LLM latency, matching PlaywrightGenerationActivity's
                # own call in SuiteGenerationWorkflow.
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
                result_type=str,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced in the result, not re-raised
            # `[FIXED-pattern]` never return the raw activity exception text —
            # same reasoning as AddTestCaseWorkflow's own
            # _activity_failure_message/_simple_test_result_reason split: it
            # may carry raw AI output, typecheck diagnostics, or a DB error.
            workflow.logger.warning(
                "RegenerateTestAssetWorkflow: scenario_id=%s failed: %s",
                input.scenario_id,
                exc,
            )
            self._status = "failed"
            return RegenerateTestAssetResult(
                status="failed",
                error_message=(
                    "Could not update this test's code — the previous version is still in use."
                ),
            )
        self._status = "complete"
        return RegenerateTestAssetResult(status="complete", test_asset_id=test_asset_id)


__all__ = [
    "GENERATION_TASK_QUEUE",
    "REGENERATE_TEST_ASSET_ACTIVITY_NAME",
    "RegenerateTestAssetActivityInput",
    "RegenerateTestAssetResult",
    "RegenerateTestAssetStatus",
    "RegenerateTestAssetWorkflow",
]
