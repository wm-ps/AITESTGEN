"""merge recording-session-name and application-context heads

Revision ID: 81a74eae15ef
Revises: f9fbb63a9343, 24772b41d896
Create Date: 2026-09-25 06:21:01.358521

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '81a74eae15ef'
down_revision: str | None = ('f9fbb63a9343', '24772b41d896')
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
