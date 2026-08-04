"""add page_load_timeout_seconds to application and discovery_run

Revision ID: f6a3c8d2b1e4
Revises: d4b8f2c6e9a1
Create Date: 2026-08-03 00:00:00.000000

Story 2.9 Task 1: nullable per-Application default and per-DiscoveryRun
override for the crawler's readiness ceiling (`wait_for_page_ready`).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a3c8d2b1e4"
down_revision: str | None = "d4b8f2c6e9a1"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application", sa.Column("page_load_timeout_seconds", sa.Float(), nullable=True)
    )
    op.add_column(
        "discovery_run", sa.Column("page_load_timeout_seconds", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("discovery_run", "page_load_timeout_seconds")
    op.drop_column("application", "page_load_timeout_seconds")
