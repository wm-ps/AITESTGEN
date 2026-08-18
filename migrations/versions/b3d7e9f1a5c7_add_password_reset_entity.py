"""add password_reset entity

Revision ID: b3d7e9f1a5c7
Revises: f5a7c9e1b3d5
Create Date: 2026-08-18 00:00:00.000000

Forgot-password flow — mirrors `invite`'s token design (sole secret is
`token_hash`, sha256 of a one-time raw token) but points at an existing
`platform_user.id` instead of creating one.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3d7e9f1a5c7"
down_revision: str | None = "f5a7c9e1b3d5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["platform_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_password_reset_user_id"), "password_reset", ["user_id"], unique=False)
    op.create_index(op.f("ix_password_reset_token_hash"), "password_reset", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_password_reset_token_hash"), table_name="password_reset")
    op.drop_index(op.f("ix_password_reset_user_id"), table_name="password_reset")
    op.drop_table("password_reset")
