"""ReconcileStaleTestRunsWorkflow — closes the gap `FinalizeTestRunActivity`/
`ForceCompleteTestRunActivity`'s own docstrings flag: "no reconciliation job
exists to catch this later." Runs periodically (every 15 min, via a Temporal
Schedule created by
`apps/api/src/api/scripts/create_stale_test_run_reconciliation_schedule.py`),
on `EXECUTION_TASK_QUEUE` — same convention as `CleanupWorkflow`, mirrored
exactly (single Activity, no dedicated worker/deployment).

Covers what `ForceCompleteTestRunActivity` itself cannot: the whole Temporal
cluster/task queue being unreachable, or a worker dying before either
Finalize or ForceComplete ever got to run at all. This reads `TestRun` rows
directly from Postgres rather than Temporal workflow history, since it must
still work when Temporal itself was the thing that broke.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow

RECONCILE_STALE_TEST_RUNS_ACTIVITY_NAME = "ReconcileStaleTestRunsActivity"

# ponytail: one fixed cutoff, not scaled by test count/concurrency. Worst-case
# per test is ExecuteTestActivity (10min x2 attempts) + HealTestActivity
# (28min x2 attempts) ~= 76min, run in batches of `max_concurrency` (default
# 5) — so a suite with dozens of tests all genuinely hitting worst-case
# retries could in theory still be running past this. 6 hours is a generous
# margin over every suite size seen in practice; revisit with a per-run
# cutoff derived from TestRun.total_count if a real suite ever false-positives.
TEST_RUN_STALE_AFTER = timedelta(hours=6)


@dataclass
class ReconcileStaleTestRunsResult:
    reconciled_test_run_ids: list[str]


@workflow.defn(name="ReconcileStaleTestRunsWorkflow")
class ReconcileStaleTestRunsWorkflow:
    @workflow.run
    async def run(self) -> ReconcileStaleTestRunsResult:
        reconciled_ids = await workflow.execute_activity(
            RECONCILE_STALE_TEST_RUNS_ACTIVITY_NAME,
            start_to_close_timeout=timedelta(minutes=5),
            result_type=list[str],
        )
        return ReconcileStaleTestRunsResult(reconciled_test_run_ids=reconciled_ids)
