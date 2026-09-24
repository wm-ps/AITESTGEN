"""merge page_settled and recording_session heads

Revision ID: 18c295426362
Revises: a38396a6ee18, f7a1c3e5b9d2
Create Date: 2026-09-24 23:29:40.765012

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '18c295426362'
down_revision: str | None = ('a38396a6ee18', 'f7a1c3e5b9d2')
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
