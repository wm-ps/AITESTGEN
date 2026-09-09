"""merge heads (test_case_number + captured_flow)

Revision ID: 8d88839005f9
Revises: a7c3e9f1b6d4, b8d2f4a6c9e3
Create Date: 2026-09-09 17:09:51.861232

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8d88839005f9'
down_revision: str | None = ('a7c3e9f1b6d4', 'b8d2f4a6c9e3')
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
