"""add test_case_number to scenario and next_test_case_number to application

Revision ID: a7c3e9f1b6d4
Revises: b2e6a1c9f4d3
Create Date: 2026-09-08 00:00:00.000000

Test Case Number feature: a persistent, sequential, per-Application display
id for each Scenario (TC-001, TC-002, ...), assigned once at creation and
never reassigned — same "claim via atomic UPDATE...RETURNING against a
per-Application counter" shape as `run_number`/`next_test_run_number`
(d6e2a4c8b1f3). Existing rows are backfilled here in creation order per
application, same "assign, backfill, then constrain" shape as that
migration.

No unique constraint here (unlike `run_number`'s
uq_test_run_application_id_run_number) — Scenario has no `application_id`
column to constrain against (only `journey_id`), and denormalizing one on
just to back a uniqueness check isn't worth it: the atomic counter claim
already makes collisions impossible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e9f1b6d4"
down_revision: str | None = "b2e6a1c9f4d3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application",
        sa.Column("next_test_case_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "scenario",
        sa.Column("test_case_number", sa.Integer(), nullable=False, server_default="0"),
    )

    # Assign each existing Application's Scenarios 1..N in creation order.
    op.execute(
        """
        UPDATE scenario
        SET test_case_number = numbered.rn
        FROM (
            SELECT scenario.id, ROW_NUMBER() OVER (
                PARTITION BY journey.application_id ORDER BY scenario.created_at, scenario.id
            ) AS rn
            FROM scenario
            JOIN journey ON journey.id = scenario.journey_id
        ) AS numbered
        WHERE scenario.id = numbered.id
        """
    )

    # Seed Application.next_test_case_number = (max existing test_case_number) + 1
    # for applications that already have scenarios; applications with none
    # keep the column's default of 1.
    op.execute(
        """
        UPDATE application
        SET next_test_case_number = counts.max_num + 1
        FROM (
            SELECT journey.application_id, MAX(scenario.test_case_number) AS max_num
            FROM scenario
            JOIN journey ON journey.id = scenario.journey_id
            GROUP BY journey.application_id
        ) AS counts
        WHERE application.id = counts.application_id
        """
    )


def downgrade() -> None:
    op.drop_column("scenario", "test_case_number")
    op.drop_column("application", "next_test_case_number")
