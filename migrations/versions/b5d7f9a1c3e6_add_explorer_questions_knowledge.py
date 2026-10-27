"""add Vantage Explorer questions and knowledge (Stage 4)

Revision ID: b5d7f9a1c3e6
Revises: a4c6e8f0b2d5
Create Date: 2026-10-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "b5d7f9a1c3e6"
down_revision: str | None = "a4c6e8f0b2d5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "explorer_question",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", UUID(as_uuid=True), nullable=False, unique=True, index=True),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("explorer_run.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("mission_id", UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("question", sa.String(), nullable=False),
        sa.Column("why", sa.String(), nullable=True),
        sa.Column("options", JSONB(), nullable=False),
        sa.Column("shot_id", UUID(as_uuid=True), nullable=True),
        sa.Column("issue_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("answer", sa.String(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "explorer_knowledge",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", UUID(as_uuid=True), nullable=False, unique=True, index=True),
        sa.Column(
            "application_id",
            UUID(as_uuid=True),
            sa.ForeignKey("application.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("explorer_knowledge")
    op.drop_table("explorer_question")
