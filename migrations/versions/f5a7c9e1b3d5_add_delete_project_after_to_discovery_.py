"""add delete_project_after to discovery_settings

Revision ID: f5a7c9e1b3d5
Revises: e2f4a6c8b0d2
Create Date: 2026-08-18 00:00:00.000000

How long a soft-deleted Application survives before the daily cleanup job
purges it and all its dependent rows for good ("1_day" / "1_week" /
"1_month"). Same singleton row (id=1) as every other discovery_settings
field.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5a7c9e1b3d5"
down_revision: str | None = "e2f4a6c8b0d2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "discovery_settings",
        sa.Column("delete_project_after", sa.String(), nullable=False, server_default="1_month"),
    )


def downgrade() -> None:
    op.drop_column("discovery_settings", "delete_project_after")
