"""add login_url to application

Revision ID: c76d24c85cdc
Revises: d2e3f4a5b6c7
Create Date: 2026-08-04 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c76d24c85cdc"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application",
        sa.Column("login_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("application", "login_url")
