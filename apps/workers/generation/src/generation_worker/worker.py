"""Generation worker process — Story 1.1 scaffold, graduated by Story 4.1,
extended by Story 4.2.

Registers `GenerationWorkflow`/`ScenarioGenerationActivity` (Story 4.1) and
`SuiteGenerationWorkflow`/`EnsureTestSuiteActivity`/`PlaywrightGenerationActivity`
(Story 4.2) against a local Temporal server, on the same task queue (one
worker process, two independent workflow types).

Run with: uv run --package generation-worker python -m generation_worker.worker
"""

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker
from workflows import (
    GENERATION_TASK_QUEUE,
    LIVE_EXPLORATION_TASK_QUEUE,
    GenerationWorkflow,
    LiveExplorationTestWorkflow,
    RegenerateTestAssetWorkflow,
    SuiteGenerationWorkflow,
)

from generation_worker.activities import (
    ensure_test_suite_activity,
    finalize_suite_generation_activity,
    playwright_generation_activity,
    regenerate_test_asset_activity,
    scenario_generation_activity,
)
from generation_worker.add_test_case_activities import analyze_prompt_activity
from generation_worker.live_exploration_activities import live_explore_activity, live_heal_activity

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
MAX_CONCURRENT_ACTIVITIES = int(os.environ.get("GENERATION_WORKER_MAX_CONCURRENT_ACTIVITIES", "5"))
# LiveExploreActivity/LiveHealActivity each spawn a Node/Playwright-MCP
# subprocess plus a multi-turn LLM loop — a much heavier, longer-running
# activity than this worker's normal AI-only ones. A separate queue (and its
# own, smaller concurrency ceiling) keeps a live exploration in flight from
# starving normal scenario/code generation on the shared queue above.
LIVE_EXPLORATION_MAX_CONCURRENT_ACTIVITIES = int(
    os.environ.get("LIVE_EXPLORATION_WORKER_MAX_CONCURRENT_ACTIVITIES", "2")
)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    client = await Client.connect(TEMPORAL_ADDRESS)
    worker = Worker(
        client,
        task_queue=GENERATION_TASK_QUEUE,
        workflows=[
            GenerationWorkflow,
            SuiteGenerationWorkflow,
            LiveExplorationTestWorkflow,
            RegenerateTestAssetWorkflow,
        ],
        activities=[
            scenario_generation_activity,
            ensure_test_suite_activity,
            playwright_generation_activity,
            finalize_suite_generation_activity,
            regenerate_test_asset_activity,
            # Live-exploration NLM feature — prompt classification is a
            # cheap AI-only call. LiveExploreActivity/LiveHealActivity (the
            # actual Playwright-MCP browser agent, which also creates the
            # Journey row itself) run on their own queue below.
            analyze_prompt_activity,
        ],
        max_concurrent_activities=MAX_CONCURRENT_ACTIVITIES,
    )
    live_exploration_worker = Worker(
        client,
        task_queue=LIVE_EXPLORATION_TASK_QUEUE,
        activities=[live_explore_activity, live_heal_activity],
        max_concurrent_activities=LIVE_EXPLORATION_MAX_CONCURRENT_ACTIVITIES,
    )
    print(f"Generation worker polling task queue '{GENERATION_TASK_QUEUE}' at {TEMPORAL_ADDRESS}")
    print(
        f"Live-exploration worker polling task queue '{LIVE_EXPLORATION_TASK_QUEUE}' "
        f"at {TEMPORAL_ADDRESS}"
    )
    await asyncio.gather(worker.run(), live_exploration_worker.run())


if __name__ == "__main__":
    asyncio.run(main())
