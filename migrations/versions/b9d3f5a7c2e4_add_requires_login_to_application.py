"""add requires_login to application

Revision ID: b9d3f5a7c2e4
Revises: a8c2e4f6b1d3
Create Date: 2026-10-26 00:00:00.000000

The Add application form's "This application requires sign-in" switch: off
means the app has no login, so no credentials are asked for and Explorer
opens it directly. Existing applications keep requiring sign-in.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b9d3f5a7c2e4"
down_revision: str | None = "a8c2e4f6b1d3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application",
        sa.Column("requires_login", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("application", "requires_login")
