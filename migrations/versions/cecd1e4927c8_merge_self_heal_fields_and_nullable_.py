"""merge self-heal fields and nullable discovery duration branches

Revision ID: cecd1e4927c8
Revises: c4d6e8f0a2b4, c2d4f6a8b0e5
Create Date: 2026-08-26 17:16:07.722213

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'cecd1e4927c8'
down_revision: str | None = ('c4d6e8f0a2b4', 'c2d4f6a8b0e5')
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
