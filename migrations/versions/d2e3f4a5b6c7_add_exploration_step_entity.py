"""add exploration step entity

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-04 00:00:00.000000

Story 2.16 Task 1: ExplorationStep, a human-readable diagnostic record of
how the crawler reached a BlockedTask — never a replay script.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exploration_step",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            primary_key=True,
        ),
        sa.Column(
            "blocked_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("blocked_task.id"),
            nullable=False,
        ),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column(
            "page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("page.id"), nullable=False
        ),
        sa.Column("action_description", sa.String(), nullable=False),
        sa.Column("input_values", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("blocked_task_id", "step_order"),
    )
    op.create_index(
        "ix_exploration_step_blocked_task_id", "exploration_step", ["blocked_task_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_exploration_step_blocked_task_id", table_name="exploration_step")
    op.drop_table("exploration_step")
