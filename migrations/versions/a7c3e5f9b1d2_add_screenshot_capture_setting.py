"""add screenshot_capture to discovery_settings

Revision ID: a7c3e5f9b1d2
Revises: 4b9005e9b5f6
Create Date: 2026-10-10 00:00:00.000000

Which finished TestResults keep a final-screen screenshot: "failed"
(default, today's behaviour), "passed" or "all".
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e5f9b1d2"
down_revision: str | None = "4b9005e9b5f6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Singleton row already exists — server_default backfills it.
    op.add_column(
        "discovery_settings",
        sa.Column("screenshot_capture", sa.String(), nullable=False, server_default="failed"),
    )


def downgrade() -> None:
    op.drop_column("discovery_settings", "screenshot_capture")
