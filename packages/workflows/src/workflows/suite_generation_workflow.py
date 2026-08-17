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
FINALIZE_SUITE_GENERATION_ACTIVITY_NAME = "FinalizeSuiteGenerationActivity"
# ponytail: fixed wave count/cooldown, not configurable — revisit if timeouts
# still exhaust 3 waves at higher real concurrency than observed live.
MAX_SCENARIO_WAVES = 3
WAVE_COOLDOWN_SECONDS = 30
# `generation_worker.playwright_generation_activity` raises
# `ValueError(f"GROUNDING_VIOLATION: {feedback}")` when a Scenario's generated
# locators still aren't grounded in real captured DOM data after its own
# in-process retries — this sentinel is how the wave loop tells that failure
# apart from an ordinary timeout/typecheck failure (which retries blind,
# unchanged) so it can carry the specific feedback into the next wave.
_GROUNDING_VIOLATION_SENTINEL = "GROUNDING_VIOLATION:"


def _extract_grounding_feedback(error: BaseException) -> str | None:
    """`workflow.execute_activity` raises a `temporalio.exceptions.
    ActivityError` whose own `str()` is a generic "Activity task failed" —
    never the Activity's actual raised message. The real message lives on
    `.__cause__` (a `temporalio.exceptions.ApplicationError`, itself rendered
    as `f"{exception_type}: {message}"`, e.g. `"ValueError: GROUNDING_
    VIOLATION: ..."`) — confirmed empirically against the installed
    temporalio SDK rather than assumed. Walk the whole `__cause__` chain
    (not just one level) so this stays correct regardless of exact wrapping
    depth across SDK versions."""
    current: BaseException | None = error
    while current is not None:
        message = str(current)
        if _GROUNDING_VIOLATION_SENTINEL in message:
            return message.split(_GROUNDING_VIOLATION_SENTINEL, 1)[1].strip()
        current = current.__cause__
    return None


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
    # Locator-grounding hardening: when a prior wave's attempt for this
    # Scenario raised a `GROUNDING_VIOLATION:`-prefixed error (a locator the
    # LLM wrote that isn't backed by any real captured DOM data —
    # `generation_worker.locator_grounding`), the extracted feedback text is
    # threaded into the next wave's input so that retry actually corrects the
    # named mistake instead of blindly repeating it. `None` (the default) for
    # every wave-1 input and every non-grounding failure.
    grounding_feedback: str | None = None


@dataclass
class FinalizeSuiteGenerationActivityInput:
    test_suite_id: str
    status: str


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
        #
        # Each Scenario's own Activity already retries 3x
        # (`retry_policy` below) — but under real fan-out concurrency
        # (a dozen+ Journeys x dozens of Scenarios hitting one AI proxy at
        # once) a Scenario can exhaust all 3 attempts on transient timeouts
        # alone. A single pass then permanently drops it: the Journey's
        # TestSuite already exists, so nothing ever revisits that Scenario
        # again without a human re-triggering Generate Suite (observed live
        # — that's exactly what got stuck at 107/159). Re-waving the
        # still-missing subset here, with a cooldown between waves so the
        # same transient load has a chance to clear, makes the Workflow
        # itself keep trying instead of a human having to notice and retry.
        pending = list(prep.scenario_ids)
        test_asset_ids: list[str] = []
        # Locator-grounding hardening: a `GROUNDING_VIOLATION:`-raising
        # Scenario's extracted feedback, carried forward into that same
        # Scenario's next-wave input — see `PlaywrightGenerationActivityInput`.
        feedback_by_scenario: dict[str, str] = {}
        for wave in range(MAX_SCENARIO_WAVES):
            if not pending:
                break
            results = await asyncio.gather(
                *[
                    workflow.execute_activity(
                        PLAYWRIGHT_GENERATION_ACTIVITY_NAME,
                        PlaywrightGenerationActivityInput(
                            scenario_id=scenario_id,
                            test_suite_id=prep.test_suite_id,
                            grounding_feedback=feedback_by_scenario.get(scenario_id),
                        ),
                        # Generous for LLM latency, matching InferenceActivity's/
                        # ScenarioGenerationActivity's own timeout.
                        start_to_close_timeout=timedelta(minutes=5),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                        result_type=str,
                    )
                    for scenario_id in pending
                ],
                return_exceptions=True,
            )

            still_pending = []
            for scenario_id, result in zip(pending, results, strict=True):
                if isinstance(result, BaseException):
                    still_pending.append(scenario_id)
                    feedback = _extract_grounding_feedback(result)
                    if feedback:
                        feedback_by_scenario[scenario_id] = feedback
                    continue
                # Empty string is PlaywrightGenerationActivity's sentinel for
                # "skipped, max_test_cases_per_application reached" — not a
                # failure to retry, not a real TestAsset id either.
                if result:
                    test_asset_ids.append(result)
                    feedback_by_scenario.pop(scenario_id, None)
            pending = still_pending

            if pending and wave < MAX_SCENARIO_WAVES - 1:
                await asyncio.sleep(WAVE_COOLDOWN_SECONDS)

        if pending:
            workflow.logger.warning(
                "SuiteGenerationWorkflow: %d scenario(s) never got a TestAsset "
                "after %d wave(s): %r",
                len(pending),
                MAX_SCENARIO_WAVES,
                pending,
            )

        # Records the outcome the log line above didn't: `list_test_suites`'s
        # own comment on this exact gap ("a TestSuite can exist with some
        # Scenarios never getting a TestAsset... permanent, no way to
        # resume") is what this status now surfaces to the user instead of
        # silently looking identical to a fully-generated suite.
        await workflow.execute_activity(
            FINALIZE_SUITE_GENERATION_ACTIVITY_NAME,
            FinalizeSuiteGenerationActivityInput(
                test_suite_id=prep.test_suite_id,
                status="incomplete" if pending else "complete",
            ),
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        return test_asset_ids


__all__ = [
    "ENSURE_TEST_SUITE_ACTIVITY_NAME",
    "FINALIZE_SUITE_GENERATION_ACTIVITY_NAME",
    "GENERATION_TASK_QUEUE",
    "PLAYWRIGHT_GENERATION_ACTIVITY_NAME",
    "EnsureTestSuiteActivityInput",
    "EnsureTestSuiteActivityResult",
    "FinalizeSuiteGenerationActivityInput",
    "PlaywrightGenerationActivityInput",
    "SuiteGenerationWorkflow",
]
