"""add run_number to test_run and next_test_run_number to application

Revision ID: d6e2a4c8b1f3
Revises: cecd1e4927c8
Create Date: 2026-09-01 00:00:00.000000

Run All Tests feature's Runs tab gains a human-facing "RUN" column
(`#1`, `#2`, ...) — deliberately not the existing `TestRun.id` (uuid7,
internal) or `external_id` (uuid4, opaque) since neither is meant to be
read aloud or typed by a user. Numbering is scoped per Application (each
application's Runs tab restarts at #1), so the counter
(`Application.next_test_run_number`) lives on `Application`, not as a
global sequence. `_prepare_test_run_sync` claims a number via an atomic
`UPDATE ... RETURNING` against that counter in the same transaction that
creates the `TestRun` row — Postgres's row lock on that UPDATE is what
makes concurrent "Run All Tests" clicks for one Application race-safe, not
a select-then-increment convention. Existing rows are backfilled here in
creation order per application, same "assign nullable, backfill, then
constrain" shape as `journey.application_id` in b2f4a8c1d9e6.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6e2a4c8b1f3"
down_revision: str | None = "cecd1e4927c8"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # --- Application.next_test_run_number (the claim-and-increment counter) ---
    op.add_column(
        "application",
        sa.Column("next_test_run_number", sa.Integer(), nullable=False, server_default="1"),
    )

    # --- TestRun.run_number (nullable first, backfilled below) ---
    op.add_column("test_run", sa.Column("run_number", sa.Integer(), nullable=True))

    # Assign each existing Application's TestRuns 1..N in creation order.
    # `id` (uuid7) is the tiebreaker for rows created in the same instant,
    # same reasoning `list_test_runs` already uses `TestRun.id` rather than
    # `created_at` as its keyset pagination column.
    op.execute(
        """
        UPDATE test_run
        SET run_number = numbered.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY application_id ORDER BY created_at, id
            ) AS rn
            FROM test_run
        ) AS numbered
        WHERE test_run.id = numbered.id
        """
    )
    op.alter_column("test_run", "run_number", nullable=False)

    op.create_unique_constraint(
        "uq_test_run_application_id_run_number", "test_run", ["application_id", "run_number"]
    )

    # Seed Application.next_test_run_number = (max existing run_number) + 1
    # for applications that already have runs; applications with none keep
    # the column's default of 1.
    op.execute(
        """
        UPDATE application
        SET next_test_run_number = counts.max_rn + 1
        FROM (
            SELECT application_id, MAX(run_number) AS max_rn
            FROM test_run
            GROUP BY application_id
        ) AS counts
        WHERE application.id = counts.application_id
        """
    )


def downgrade() -> None:
    op.drop_constraint("uq_test_run_application_id_run_number", "test_run", type_="unique")
    op.drop_column("test_run", "run_number")
    op.drop_column("application", "next_test_run_number")
