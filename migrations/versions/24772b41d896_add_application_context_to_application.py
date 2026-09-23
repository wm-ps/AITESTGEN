"""add application_context to application

Revision ID: 24772b41d896
Revises: c9e2a4f7b3d6
Create Date: 2026-09-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "24772b41d896"
down_revision: str | None = "c9e2a4f7b3d6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application",
        sa.Column(
            "application_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("application", "application_context")
