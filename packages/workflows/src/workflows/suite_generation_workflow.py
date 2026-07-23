"""SuiteGenerationWorkflow — Story 4.2's Journey-scoped Test Suite dispatch.

Mirrors `GenerationWorkflow.run(journey_id)`'s exact shape (AD-2: zero I/O,
only Activity dispatch) — a distinct workflow type, not an extension of
`GenerationWorkflow`, since Temporal only permits one `@workflow.run` method
per class and the two dispatch different Activities for different purposes.

First resolves this Journey's current `TestSuite` and its current Scenario
ids in one combined `EnsureTestSuiteActivity` call (idempotent insert-or-fetch
for the `TestSuite`, run once — not once per Scenario, so concurrent
`PlaywrightGenerationActivity` calls for the same Journey never race to
create duplicate `TestSuite` rows), then fans out one
`PlaywrightGenerationActivity` call per current Scenario, concurrently.

Workflow-ID convention: `suite-{journey_id}-{attempt}`, directly mirroring
`generation-{journey_id}-{attempt}` — `journey.attempt` already exists and is
exactly the right per-suite counter, no content-derived digest needed.
"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from workflows.generation_workflow import GENERATION_TASK_QUEUE

ENSURE_TEST_SUITE_ACTIVITY_NAME = "EnsureTestSuiteActivity"
PLAYWRIGHT_GENERATION_ACTIVITY_NAME = "PlaywrightGenerationActivity"


@dataclass
class EnsureTestSuiteActivityInput:
    journey_id: str


@dataclass
class EnsureTestSuiteActivityResult:
    test_suite_id: str
    scenario_ids: list[str]


@dataclass
class PlaywrightGenerationActivityInput:
    scenario_id: str
    test_suite_id: str


@workflow.defn(name="SuiteGenerationWorkflow")
class SuiteGenerationWorkflow:
    @workflow.run
    async def run(self, journey_id: str) -> list[str]:
        prep: EnsureTestSuiteActivityResult = await workflow.execute_activity(
            ENSURE_TEST_SUITE_ACTIVITY_NAME,
            EnsureTestSuiteActivityInput(journey_id=journey_id),
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
            result_type=EnsureTestSuiteActivityResult,
        )

        # Fan-out (AD-2: still orchestration-only, only Activity dispatch).
        # `return_exceptions=True` — one Scenario's failure must not fail the
        # whole Journey's dispatch; every other Scenario's TestAsset should
        # still get written. Matches this codebase's established
        # fault-isolation convention for batch capture.
        results = await asyncio.gather(
            *[
                workflow.execute_activity(
                    PLAYWRIGHT_GENERATION_ACTIVITY_NAME,
                    PlaywrightGenerationActivityInput(
                        scenario_id=scenario_id, test_suite_id=prep.test_suite_id
                    ),
                    # Generous for LLM latency, matching InferenceActivity's/
                    # ScenarioGenerationActivity's own timeout.
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                    result_type=str,
                )
                for scenario_id in prep.scenario_ids
            ],
            return_exceptions=True,
        )

        test_asset_ids: list[str] = []
        for scenario_id, result in zip(prep.scenario_ids, results, strict=True):
            if isinstance(result, BaseException):
                workflow.logger.warning(
                    "SuiteGenerationWorkflow: PlaywrightGenerationActivity failed for "
                    "scenario_id=%s: %r",
                    scenario_id,
                    result,
                )
                continue
            test_asset_ids.append(result)
        return test_asset_ids


__all__ = [
    "ENSURE_TEST_SUITE_ACTIVITY_NAME",
    "GENERATION_TASK_QUEUE",
    "PLAYWRIGHT_GENERATION_ACTIVITY_NAME",
    "EnsureTestSuiteActivityInput",
    "EnsureTestSuiteActivityResult",
    "PlaywrightGenerationActivityInput",
    "SuiteGenerationWorkflow",
]
