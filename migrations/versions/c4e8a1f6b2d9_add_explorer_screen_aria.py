"""Each screen's element structure (accessibility snapshot): what scenarios
are planned from, so they only use controls, options and rows the page has.

Revision ID: c4e8a1f6b2d9
Revises: bd3dbdb0b2e3
"""

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8a1f6b2d9"
down_revision: str | None = "bd3dbdb0b2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("explorer_screen", sa.Column("aria", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("explorer_screen", "aria")
