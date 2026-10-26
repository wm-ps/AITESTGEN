"""drop application_context from application

Revision ID: e4c8b2d6f1a7
Revises: b7e3f1a9c2d4
Create Date: 2026-10-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e4c8b2d6f1a7"
down_revision: str | None = "b7e3f1a9c2d4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("application", "application_context")


def downgrade() -> None:
    op.add_column(
        "application",
        sa.Column(
            "application_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
