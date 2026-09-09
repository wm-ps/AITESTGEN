"""add source to discovery_run

Revision ID: a1c3e5f7b9d1
Revises: 342463f450d5
Create Date: 2026-09-04 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c3e5f7b9d1"
down_revision: str | None = "342463f450d5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "discovery_run",
        sa.Column("source", sa.String(), nullable=False, server_default="crawler"),
    )


def downgrade() -> None:
    op.drop_column("discovery_run", "source")
