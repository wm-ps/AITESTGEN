"""Cancelling a TestRun — the one database rule shared by the API's cancel
endpoint and the execution worker (its cleanup activity and every write
guard), so the two sides can never disagree about what "cancelled" means.

Every path that writes a run's status or any of its results takes
`lock_test_run` first (`SELECT … FOR UPDATE` on the TestRun row) and then
checks `status`. Postgres serializes those transactions, so a test that
finishes at the same moment as a cancel is either committed first (and
preserved — the cancel only touches results still "pending") or blocks until
the cancel commits, sees "cancelled", and writes nothing. Lock order is
always the TestRun row before any of its TestResult rows.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import update
from sqlmodel import Session, select

from domain.test_result import TestResult
from domain.test_run import TestRun

CANCELLABLE_TEST_RUN_STATUSES = ("pending", "running")
RUN_CANCELLED_MESSAGE = "Run cancelled"


def lock_test_run(session: Session, test_run_pk: uuid.UUID) -> TestRun | None:
    # populate_existing: a TestRun this session already loaded would
    # otherwise come back with its stale in-memory status, not the locked row's.
    return session.exec(
        select(TestRun)
        .where(TestRun.id == test_run_pk)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()


def tally_result_counts(results: list[TestResult]) -> dict[str, int]:
    counts = {status: 0 for status in ("passed", "failed", "timed_out", "errored", "blocked")}
    for result in results:
        if result.status in counts:
            counts[result.status] += 1
    return counts


def apply_test_run_cancel(session: Session, test_run: TestRun) -> None:
    """Marks a TestRun already locked by `lock_test_run` cancelled, in the
    caller's transaction (the caller commits). Every result still "pending"
    — queued or executing right now — becomes "cancelled"; every finished
    result keeps its real outcome. Idempotent.

    ponytail: `completed_at` doubles as the cancel time and there's no
    `cancelled_by`/`cancelled_count` — a cancelled run's summary shows the
    existing tallies, its cancelled tests appear as pills in the result list.
    Add those columns if cancels ever need an audit trail or their own tile."""
    now = datetime.now(UTC)
    test_run.status = "cancelled"
    test_run.completed_at = test_run.completed_at or now
    session.execute(
        update(TestResult)
        .where(
            TestResult.test_run_id == test_run.id,  # type: ignore[arg-type]
            TestResult.status == "pending",  # type: ignore[arg-type]
        )
        .values(status="cancelled", error_message=RUN_CANCELLED_MESSAGE, completed_at=now)
    )
    # No heal claim outlives the run: a heal in flight stops on its own
    # (execution worker's `cancel_watch`) and must not leave the result
    # looking "being healed".
    session.execute(
        update(TestResult)
        .where(TestResult.test_run_id == test_run.id)  # type: ignore[arg-type]
        .values(heal_started_at=None)
    )
    results = session.exec(select(TestResult).where(TestResult.test_run_id == test_run.id)).all()
    counts = tally_result_counts(list(results))
    test_run.passed_count = counts["passed"]
    test_run.failed_count = counts["failed"]
    test_run.timed_out_count = counts["timed_out"]
    test_run.errored_count = counts["errored"]
    test_run.blocked_count = counts["blocked"]
    session.add(test_run)
