"""add test_run.workflow_id

Revision ID: a9c4e2b7d1f3
Revises: e5b2d8f1a4c6
Create Date: 2026-10-22 00:00:00.000000

The ApplicationTestExecutionWorkflow id running a TestRun, so a run can be
cancelled. Nullable: runs from before this column have none.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9c4e2b7d1f3"
down_revision: str | None = "e5b2d8f1a4c6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("test_run", sa.Column("workflow_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("test_run", "workflow_id")
