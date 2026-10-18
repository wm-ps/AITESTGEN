"""merge explorer and discovery_required heads

Revision ID: 362ae149aa7c
Revises: d4a1c7e9b3f2, d7f9b1c3e5a8
Create Date: 2026-10-18 19:05:22.444428

"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '362ae149aa7c'
down_revision: str | tuple[str, ...] | None = ('d4a1c7e9b3f2', 'd7f9b1c3e5a8')
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
