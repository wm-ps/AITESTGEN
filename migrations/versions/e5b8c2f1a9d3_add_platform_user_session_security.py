"""add session_version, failed_logins, locked_until to platform_user

Revision ID: e5b8c2f1a9d3
Revises: e7b2d4f1a9c3
Create Date: 2026-10-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5b8c2f1a9d3"
down_revision: str | None = "e7b2d4f1a9c3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_user",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "platform_user",
        sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "platform_user",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("platform_user", "locked_until")
    op.drop_column("platform_user", "failed_logins")
    op.drop_column("platform_user", "session_version")
