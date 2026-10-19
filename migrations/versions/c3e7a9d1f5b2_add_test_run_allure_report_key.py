"""add test_run.allure_report_key

Revision ID: c3e7a9d1f5b2
Revises: b8d4f6a0c2e3
Create Date: 2026-10-15 00:00:00.000000

Object-store key of the run's single-file Allure HTML report, written by
GenerateAllureReportActivity. Nullable: older runs and runs that produced no
report simply have none.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e7a9d1f5b2"
down_revision: str | None = "b8d4f6a0c2e3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("test_run", sa.Column("allure_report_key", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("test_run", "allure_report_key")
