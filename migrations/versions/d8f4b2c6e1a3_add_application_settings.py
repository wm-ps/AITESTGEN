"""Per-application settings: Explorer limits and test-case generation
settings saved on the application. Empty (NULL) means the application uses
the organisation-wide values, as before.

Revision ID: d8f4b2c6e1a3
Revises: c7e3a9b1d4f2
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "d8f4b2c6e1a3"
down_revision: str | None = "c7e3a9b1d4f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("application", sa.Column("explorer_limits", JSONB(), nullable=True))
    op.add_column("application", sa.Column("generation_settings", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("application", "generation_settings")
    op.drop_column("application", "explorer_limits")
