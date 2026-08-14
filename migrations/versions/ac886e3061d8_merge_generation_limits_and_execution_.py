"""merge generation limits and execution policy branches

Revision ID: ac886e3061d8
Revises: 10771097a5f5, b9d1e3f5a7c2
Create Date: 2026-08-13 12:04:22.665224

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ac886e3061d8'
down_revision: str | None = ('10771097a5f5', 'b9d1e3f5a7c2')
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
