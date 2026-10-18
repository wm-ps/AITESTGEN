"""add Vantage Explorer roles, access, insights and recording kind (Stages 6-7)

Revision ID: c6e8a0b2d4f7
Revises: b5d7f9a1c3e6
Create Date: 2026-10-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "c6e8a0b2d4f7"
down_revision: str | None = "b5d7f9a1c3e6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "explorer_role",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", UUID(as_uuid=True), nullable=False, unique=True, index=True),
        sa.Column(
            "application_id",
            UUID(as_uuid=True),
            sa.ForeignKey("application.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("secret_ref", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "explorer_access",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("explorer_run.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("screen_id", UUID(as_uuid=True), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "explorer_run", sa.Column("insights", JSONB(), nullable=False, server_default="{}")
    )
    op.add_column(
        "explorer_recording",
        sa.Column("kind", sa.String(), nullable=False, server_default="mission"),
    )


def downgrade() -> None:
    op.drop_column("explorer_recording", "kind")
    op.drop_column("explorer_run", "insights")
    op.drop_table("explorer_access")
    op.drop_table("explorer_role")
