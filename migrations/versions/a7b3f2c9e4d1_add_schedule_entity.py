"""add schedule entity and test_run.schedule_id

Revision ID: a7b3f2c9e4d1
Revises: d6e2a4c8b1f3
Create Date: 2026-09-02 00:00:00.000000

Schedules feature: user-created recurring triggers for "Run All Tests".
`schedule` is created first, then `test_run.schedule_id` referencing it —
one file, not two, since the FK requires the table to exist first.

The (application_id, name) uniqueness is a *partial* unique index rather
than a UniqueConstraint because `schedule` is soft-deleted (`deleted_at`,
same convention as `application`) — a plain constraint would permanently
burn a name the moment a schedule was deleted.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7b3f2c9e4d1"
down_revision: str | None = "d6e2a4c8b1f3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedule",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            primary_key=True,
        ),
        sa.Column("external_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("application.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("cadence_type", sa.String(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=True),
        sa.Column("minute", sa.Integer(), nullable=True),
        sa.Column(
            "days_of_week",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("cron_expression", sa.String(), nullable=True),
        sa.Column("time_zone", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("temporal_schedule_id", sa.String(), nullable=False, unique=True),
        sa.Column("created_by_name", sa.String(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_schedule_external_id", "schedule", ["external_id"])
    op.create_index("ix_schedule_application_id", "schedule", ["application_id"])
    op.create_index("ix_schedule_temporal_schedule_id", "schedule", ["temporal_schedule_id"])
    op.create_index(
        "uq_schedule_application_id_name",
        "schedule",
        ["application_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.add_column(
        "test_run",
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("schedule.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_test_run_schedule_id", "test_run", ["schedule_id"])
    # Every pre-existing TestRun was a manual run — NULL is already correct,
    # no backfill needed (unlike d6e2a4c8b1f3's run_number).


def downgrade() -> None:
    op.drop_index("ix_test_run_schedule_id", table_name="test_run")
    op.drop_column("test_run", "schedule_id")
    op.drop_index("uq_schedule_application_id_name", table_name="schedule")
    op.drop_index("ix_schedule_temporal_schedule_id", table_name="schedule")
    op.drop_index("ix_schedule_application_id", table_name="schedule")
    op.drop_index("ix_schedule_external_id", table_name="schedule")
    op.drop_table("schedule")
