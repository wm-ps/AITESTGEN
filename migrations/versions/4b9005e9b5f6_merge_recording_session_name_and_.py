"""merge recording-session-name and content-score-on-page heads

Revision ID: 4b9005e9b5f6
Revises: 81a74eae15ef, f4a9d3e7c1b8
Create Date: 2026-10-01 12:41:47.404954

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '4b9005e9b5f6'
down_revision: str | None = ('81a74eae15ef', 'f4a9d3e7c1b8')
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
