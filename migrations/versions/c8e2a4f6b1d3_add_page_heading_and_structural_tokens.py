"""add page heading and structural_tokens

Revision ID: c8e2a4f6b1d3
Revises: b7d4f1e8c2a9
Create Date: 2026-08-03 00:00:00.000000

Story 2.10 Task 5: persisted so a prior Discovery Run's canonical Page rows
can be re-fingerprinted when seeding a new run's in-process state-identity
cache.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c8e2a4f6b1d3"
down_revision: str | None = "b7d4f1e8c2a9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("page", sa.Column("heading", sa.String(), nullable=True))
    op.add_column(
        "page",
        sa.Column("structural_tokens", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("page", "structural_tokens")
    op.drop_column("page", "heading")
