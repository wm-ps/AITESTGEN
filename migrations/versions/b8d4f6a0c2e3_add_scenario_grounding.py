"""add scenario.grounding

Revision ID: b8d4f6a0c2e3
Revises: a7c3e5f9b1d2
Create Date: 2026-10-12 00:00:00.000000

An authored test case added to an existing Journey keeps the flow/pages it
was actually explored with, since that Journey's own describe another flow.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "b8d4f6a0c2e3"
down_revision: str | None = "a7c3e5f9b1d2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scenario", sa.Column("grounding", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("scenario", "grounding")
