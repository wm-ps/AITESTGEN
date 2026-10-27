"""add Vantage Explorer test cases (Stage 5)

Revision ID: a4c6e8f0b2d5
Revises: f3b5d7e9a1c4
Create Date: 2026-10-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "a4c6e8f0b2d5"
down_revision: str | None = "f3b5d7e9a1c4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "explorer_test_case",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", UUID(as_uuid=True), nullable=False, unique=True, index=True),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("explorer_run.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("technique", sa.String(), nullable=True),
        sa.Column("business_thing", sa.String(), nullable=True),
        sa.Column("start_screen", sa.String(), nullable=True),
        sa.Column("steps", JSONB(), nullable=False),
        sa.Column("expected", sa.String(), nullable=False),
        sa.Column("trust", sa.String(), nullable=False),
        sa.Column("observed", sa.String(), nullable=True),
        sa.Column("script", JSONB(), nullable=False),
        sa.Column("check", JSONB(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("drop_reason", sa.String(), nullable=True),
        sa.Column("proof_runs", sa.Integer(), nullable=False),
        sa.Column("proof_passes", sa.Integer(), nullable=False),
        sa.Column("catches_breakage", sa.Boolean(), nullable=True),
        sa.Column("evidence_shot_id", UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("explorer_recording", "mission_id", nullable=True)
    op.add_column(
        "explorer_recording",
        sa.Column("test_case_id", UUID(as_uuid=True), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_column("explorer_recording", "test_case_id")
    op.alter_column("explorer_recording", "mission_id", nullable=False)
    op.drop_table("explorer_test_case")
