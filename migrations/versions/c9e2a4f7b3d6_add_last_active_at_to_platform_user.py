"""add last_active_at to platform_user

Revision ID: c9e2a4f7b3d6
Revises: b1f4d8a2c6e9
Create Date: 2026-09-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e2a4f7b3d6"
down_revision: str | None = "b1f4d8a2c6e9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_user",
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("platform_user", "last_active_at")
