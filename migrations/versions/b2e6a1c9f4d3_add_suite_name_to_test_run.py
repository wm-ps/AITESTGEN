"""add suite_name to test_run

Revision ID: b2e6a1c9f4d3
Revises: f18a92c6d3b7
Create Date: 2026-09-08 00:00:00.000000

Run Suite Flow: a "Run Journey(s)" run carries a custom suite name; a Full
Suite run leaves this null (label derived as "Full Suite Run" at read time).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2e6a1c9f4d3"
down_revision: str | None = "f18a92c6d3b7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("test_run", sa.Column("suite_name", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("test_run", "suite_name")
