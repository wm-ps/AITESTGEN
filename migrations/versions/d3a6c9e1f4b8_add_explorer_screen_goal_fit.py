"""add each Explorer screen's place against the run's Goal

Revision ID: d3a6c9e1f4b8
Revises: c1f4a7e2d9b6
Create Date: 2026-10-27 00:00:00.000000

inside | on_the_way | past_stop | outside, or NULL when the run has no goal.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3a6c9e1f4b8"
down_revision: str | None = "c1f4a7e2d9b6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("explorer_screen", sa.Column("goal_fit", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("explorer_screen", "goal_fit")
