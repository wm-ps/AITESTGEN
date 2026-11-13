"""count a multi-browser run's outcomes per test, not per browser result

A run on several browsers has one result per test per browser. Its counters
used to tally those results (3 tests on 2 browsers read 6); they now count one
outcome per test — worst browser wins, still running beats everything — the
same rule as `domain.test_run_cancel.tally_result_counts`. This recounts the
runs that already finished that way. One-browser runs are already right.

Revision ID: e2c6d4a8f1b7
Revises: d9b5c2e7a4f1
"""

from alembic import op

revision: str = "e2c6d4a8f1b7"
down_revision: str | None = "d9b5c2e7a4f1"
branch_labels = None
depends_on = None

# One row per (run, test) with its outcome across browsers, then per-run totals.
_PER_TEST = """
    SELECT test_run_id, scenario_id,
        CASE
            WHEN bool_or(status = 'pending') THEN 'pending'
            WHEN bool_or(status = 'failed') THEN 'failed'
            WHEN bool_or(status = 'timed_out') THEN 'timed_out'
            WHEN bool_or(status = 'errored') THEN 'errored'
            WHEN bool_or(status = 'blocked') THEN 'blocked'
            WHEN bool_or(status = 'cancelled') THEN 'cancelled'
            ELSE 'passed'
        END AS outcome
    FROM test_result
    GROUP BY test_run_id, scenario_id
"""
_PER_RESULT = "SELECT test_run_id, status AS outcome FROM test_result"


def _recount(per_row_sql: str) -> None:
    op.execute(
        f"""
        WITH rows AS ({per_row_sql}),
        totals AS (
            SELECT test_run_id,
                count(*) AS total,
                count(*) FILTER (WHERE outcome = 'passed') AS passed,
                count(*) FILTER (WHERE outcome = 'failed') AS failed,
                count(*) FILTER (WHERE outcome = 'timed_out') AS timed_out,
                count(*) FILTER (WHERE outcome = 'errored') AS errored,
                count(*) FILTER (WHERE outcome = 'blocked') AS blocked
            FROM rows GROUP BY test_run_id
        )
        UPDATE test_run SET
            total_count = totals.total,
            passed_count = totals.passed,
            failed_count = totals.failed,
            timed_out_count = totals.timed_out,
            errored_count = totals.errored,
            blocked_count = totals.blocked
        FROM totals
        WHERE totals.test_run_id = test_run.id
          AND jsonb_array_length(test_run.browsers) > 1
        """
    )


def upgrade() -> None:
    _recount(_PER_TEST)


def downgrade() -> None:
    _recount(_PER_RESULT)
