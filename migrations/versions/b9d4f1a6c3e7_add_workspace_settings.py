"""add workspace_settings

Revision ID: b9d4f1a6c3e7
Revises: a8c2e5f7b1d3
Create Date: 2026-11-23 03:00:00.000000

Per-team and per-person values for the settings that were organisation-wide.
The existing singleton settings rows stay as the organisation default and each
workspace stores only what it changed, so nothing changes until someone edits a
team's or their own settings.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b9d4f1a6c3e7"
down_revision: str | None = "a8c2e5f7b1d3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_settings",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=True),
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "discovery", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "explorer", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.CheckConstraint(
            "(team_id IS NOT NULL AND owner_user_id IS NULL) OR (team_id IS NULL AND owner_user_id IS NOT NULL)",
            name="workspace_settings_one_owner",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["team.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["platform_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id"),
        sa.UniqueConstraint("owner_user_id"),
    )
    op.create_index(op.f("ix_workspace_settings_organization_id"), "workspace_settings", ["organization_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_workspace_settings_organization_id"), table_name="workspace_settings")
    op.drop_table("workspace_settings")
