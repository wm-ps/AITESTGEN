"""Explorer limits: the settings table (one row) and, per run, the limits it
uses and its AI spend

Revision ID: f3c8a1d5e2b7
Revises: e4b8d2f6a1c3
Create Date: 2026-10-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3c8a1d5e2b7"
down_revision: str | None = "e4b8d2f6a1c3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "explorer_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_wait_minutes", sa.Integer(), nullable=True),
        sa.Column("mission_time_limit_minutes", sa.Integer(), nullable=True),
        sa.Column("run_time_limit_minutes", sa.Integer(), nullable=True),
        sa.Column("first_look_time_limit_minutes", sa.Integer(), nullable=False),
        sa.Column("hidden_screen_search_minutes", sa.Integer(), nullable=False),
        sa.Column("ai_budget_usd", sa.Float(), nullable=True),
        sa.Column("first_look_max_screens", sa.Integer(), nullable=False),
        sa.Column("max_missions", sa.Integer(), nullable=False),
        sa.Column("steps_per_mission", sa.Integer(), nullable=False),
        sa.Column("max_scenarios", sa.Integer(), nullable=False),
        sa.Column("proof_replays", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="explorer_settings_singleton"),
    )
    op.execute(
        "INSERT INTO explorer_settings (id, question_wait_minutes, mission_time_limit_minutes, "
        "run_time_limit_minutes, first_look_time_limit_minutes, hidden_screen_search_minutes, "
        "ai_budget_usd, first_look_max_screens, max_missions, steps_per_mission, max_scenarios, "
        "proof_replays) VALUES (1, 30, 75, NULL, 120, 25, NULL, 150, 15, 20, 150, 1)"
    )
    op.add_column(
        "explorer_run",
        sa.Column("limits", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "explorer_run",
        sa.Column("ai_spent_usd", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("explorer_run", "ai_spent_usd")
    op.drop_column("explorer_run", "limits")
    op.drop_table("explorer_settings")
