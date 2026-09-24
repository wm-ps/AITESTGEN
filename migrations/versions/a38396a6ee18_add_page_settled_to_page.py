"""add page_settled to page

Revision ID: a38396a6ee18
Revises: 24772b41d896
Create Date: 2026-09-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a38396a6ee18"
down_revision: str | None = "24772b41d896"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "page",
        sa.Column("page_settled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("page", "page_settled")
