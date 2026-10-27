"""add the recorded route to each Explorer screen

Revision ID: a8c2e4f6b1d3
Revises: 362ae149aa7c
Create Date: 2026-10-26 00:00:00.000000

Scenarios fast-forward to their screen by replaying this route instead of
having the model walk in from the start (it was kept in worker memory, keyed
by a name that rarely matched, and lost on every restart).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a8c2e4f6b1d3"
down_revision: str | None = "362ae149aa7c"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("explorer_screen", sa.Column("route", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("explorer_screen", "route")
