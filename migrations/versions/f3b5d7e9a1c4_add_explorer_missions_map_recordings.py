"""add Vantage Explorer missions, app map transitions and recordings

Revision ID: f3b5d7e9a1c4
Revises: e7a1c3b5d9f2
Create Date: 2026-10-15 00:00:00.000000

Stage 2 of docs/vantage-explorer/PLAN.md.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "f3b5d7e9a1c4"
down_revision: str | None = "e7a1c3b5d9f2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _run_fk() -> sa.Column:
    return sa.Column(
        "run_id",
        UUID(as_uuid=True),
        sa.ForeignKey("explorer_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def upgrade() -> None:
    op.add_column(
        "explorer_run",
        sa.Column("branch_points", JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column("explorer_screen", sa.Column("condition", sa.String(), nullable=True))
    op.add_column(
        "explorer_event", sa.Column("mission_id", UUID(as_uuid=True), nullable=True, index=True)
    )
    op.create_table(
        "explorer_mission",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", UUID(as_uuid=True), nullable=False, unique=True, index=True),
        _run_fk(),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("goal", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("why", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.String(), nullable=True),
        sa.Column("condition", sa.String(), nullable=True),
        sa.Column("expected", sa.String(), nullable=True),
        sa.Column("start_screen", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("matches_expected", sa.Boolean(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=False),
        sa.Column("new_screens", sa.Integer(), nullable=False),
        sa.Column("added_by", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "explorer_transition",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _run_fk(),
        sa.Column("from_screen_id", UUID(as_uuid=True), nullable=False),
        sa.Column("to_screen_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("mission_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "explorer_recording",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _run_fk(),
        sa.Column("mission_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("explorer_recording")
    op.drop_table("explorer_transition")
    op.drop_table("explorer_mission")
    op.drop_column("explorer_event", "mission_id")
    op.drop_column("explorer_screen", "condition")
    op.drop_column("explorer_run", "branch_points")
