"""add run-completed email columns; merge the allure-report and
discovery-required heads

Revision ID: e5b2d8f1a4c6
Revises: c3e7a9d1f5b2, d4a1c7e9b3f2
Create Date: 2026-10-19 00:00:00.000000

Who receives a run's completion email: `test_run.triggered_by_user_id` for
a manual run, `schedule.created_by_user_id` for a scheduled one. Both
nullable and left null for existing rows — no owner is inferred from the
stored names — and `ON DELETE SET NULL` because users are hard-deleted.
`report_email_claimed_at` / `report_emailed_at` keep the email to one send.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5b2d8f1a4c6"
down_revision: tuple[str, str] = ("c3e7a9d1f5b2", "d4a1c7e9b3f2")
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "test_run",
        sa.Column(
            "triggered_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "platform_user.id",
                name="fk_test_run_triggered_by_user_id_platform_user",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "test_run",
        sa.Column("report_email_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "test_run",
        sa.Column("report_emailed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "schedule",
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "platform_user.id",
                name="fk_schedule_created_by_user_id_platform_user",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("schedule", "created_by_user_id")
    op.drop_column("test_run", "report_emailed_at")
    op.drop_column("test_run", "report_email_claimed_at")
    op.drop_column("test_run", "triggered_by_user_id")
