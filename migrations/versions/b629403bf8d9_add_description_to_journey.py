"""add description to journey

Revision ID: b629403bf8d9
Revises: c2a0bbeb086d
Create Date: 2026-07-22 16:04:32.294927

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b629403bf8d9'
down_revision: str | None = 'c2a0bbeb086d'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('journey', sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column('journey', 'description')
