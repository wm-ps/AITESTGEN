"""add triggered_by_name to test_run

Revision ID: 10771097a5f5
Revises: 8341132a4193
Create Date: 2026-08-12 00:00:00.000000

Application Workspace feature: who clicked "Run All Tests"/"Run Suite" —
this app has no scheduling/CI, only manual runs, so this is the whole
"trigger" concept the Runs tab needs to display. Nullable: a run started
outside the API (e.g. directly via Temporal CLI, as this feature's own
manual verification step already does) has no user to attribute.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "10771097a5f5"
down_revision: str | None = "8341132a4193"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "test_run",
        sa.Column("triggered_by_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("test_run", "triggered_by_name")
