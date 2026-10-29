"""add the authoring request an Explorer run follows

Revision ID: e7b2d4f1a9c3
Revises: d3a6c9e1f4b8
Create Date: 2026-10-29 00:00:00.000000

NULL for a normal Explorer run; the user's prompt for an authoring run.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7b2d4f1a9c3"
down_revision: str | None = "d3a6c9e1f4b8"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("explorer_run", sa.Column("prompt", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("explorer_run", "prompt")
