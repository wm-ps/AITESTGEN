"""Explorer limits are organisation-wide only (Settings → Explorer limits):
an application's run starts as soon as it is added, so per-application
limits were never in time to matter.

Revision ID: e9a5c3d7f2b4
Revises: d8f4b2c6e1a3
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "e9a5c3d7f2b4"
down_revision: str | None = "d8f4b2c6e1a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("application", "explorer_limits")


def downgrade() -> None:
    op.add_column("application", sa.Column("explorer_limits", JSONB(), nullable=True))
