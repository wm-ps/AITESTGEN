"""add role to platform_user and invite entity

Revision ID: a9f3d81c5e2b
Revises: c76d24c85cdc
Create Date: 2026-08-06 00:00:00.000000

Every existing PlatformUser predates Invites and was created directly via
the seed script/migration — each one is the sole/first user of their
Organization, so backfills to "admin" rather than the new-row default of
"member" (only an Invite's own `role` picks "member" going forward).
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9f3d81c5e2b"
down_revision: str | None = "c76d24c85cdc"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_user",
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="member"),
    )
    op.execute("UPDATE platform_user SET role = 'admin'")

    op.create_table(
        "invite",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("invited_by_id", sa.UUID(), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("token_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invited_by_id"], ["platform_user.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_invite_email"), "invite", ["email"], unique=False)
    op.create_index(op.f("ix_invite_external_id"), "invite", ["external_id"], unique=True)
    op.create_index(op.f("ix_invite_organization_id"), "invite", ["organization_id"], unique=False)
    op.create_index(op.f("ix_invite_token_hash"), "invite", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_invite_token_hash"), table_name="invite")
    op.drop_index(op.f("ix_invite_organization_id"), table_name="invite")
    op.drop_index(op.f("ix_invite_external_id"), table_name="invite")
    op.drop_index(op.f("ix_invite_email"), table_name="invite")
    op.drop_table("invite")
    op.drop_column("platform_user", "role")
