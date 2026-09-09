"""add captured_flow to journey

Revision ID: b8d2f4a6c9e3
Revises: a1c3e5f7b9d1
Create Date: 2026-09-08 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b8d2f4a6c9e3"
down_revision: str | None = "a1c3e5f7b9d1"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "journey",
        sa.Column("captured_flow", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("journey", "captured_flow")
