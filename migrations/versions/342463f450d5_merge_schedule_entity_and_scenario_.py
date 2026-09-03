"""merge schedule entity and scenario source

Revision ID: 342463f450d5
Revises: 584191e291e5, a7b3f2c9e4d1
Create Date: 2026-09-03 15:13:38.097066

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '342463f450d5'
down_revision: str | None = ('584191e291e5', 'a7b3f2c9e4d1')
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
