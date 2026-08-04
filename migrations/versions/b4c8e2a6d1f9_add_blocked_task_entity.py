"""add blocked task entity

Revision ID: b4c8e2a6d1f9
Revises: a3f7c9e1b2d4
Create Date: 2026-08-04 00:00:00.000000

Story 2.15 Task 1: BlockedTask, an aggregated open ask for a Planner DEFER
(Story 2.11) — from the Safety Engine (Story 2.12, required_type=approval)
or the Data Resolver (Story 2.13, required_type=data).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b4c8e2a6d1f9"
down_revision: str | None = "a3f7c9e1b2d4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blocked_task",
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
        sa.Column(
            "discovery_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("discovery_run.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("aggregation_key", sa.String(), nullable=False),
        sa.Column("required_description", sa.String(), nullable=False),
        sa.Column("required_type", sa.String(), nullable=False),
        sa.Column("waiting_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_blocked_task_application_id", "blocked_task", ["application_id"])
    op.create_index("ix_blocked_task_external_id", "blocked_task", ["external_id"])
    op.create_index("ix_blocked_task_aggregation_key", "blocked_task", ["aggregation_key"])
    op.create_index(
        "ix_blocked_task_app_key_status",
        "blocked_task",
        ["application_id", "aggregation_key", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_blocked_task_app_key_status", table_name="blocked_task")
    op.drop_index("ix_blocked_task_aggregation_key", table_name="blocked_task")
    op.drop_index("ix_blocked_task_external_id", table_name="blocked_task")
    op.drop_index("ix_blocked_task_application_id", table_name="blocked_task")
    op.drop_table("blocked_task")
