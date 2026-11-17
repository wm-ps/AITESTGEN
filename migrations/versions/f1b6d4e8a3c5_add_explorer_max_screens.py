"""Settings → Explorer limits → "Screens to explore": the whole run's screen
total. NULL = no limit (as before).

Revision ID: f1b6d4e8a3c5
Revises: e9a5c3d7f2b4
"""

import sqlalchemy as sa
from alembic import op

revision: str = "f1b6d4e8a3c5"
down_revision: str | None = "e9a5c3d7f2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("explorer_settings", sa.Column("max_screens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("explorer_settings", "max_screens")
