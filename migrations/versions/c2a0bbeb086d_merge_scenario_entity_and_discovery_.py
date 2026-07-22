"""merge scenario entity and discovery stage branches

Revision ID: c2a0bbeb086d
Revises: 31f9485f28e9, c3d4e5f6a7b8
Create Date: 2026-07-22 12:11:25.387159

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c2a0bbeb086d'
down_revision: str | None = ('31f9485f28e9', 'c3d4e5f6a7b8')
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
