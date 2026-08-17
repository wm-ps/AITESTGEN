"""add status to test_suite

Revision ID: e2f4a6c8b0d2
Revises: d4a6c8e0b2f4
Create Date: 2026-08-14 00:00:00.000000

SuiteGenerationWorkflow can finish with some Scenarios never getting a
TestAsset (each Scenario's own PlaywrightGenerationActivity retries/waves
independently, per-Journey fault isolation) — until now nothing recorded
that fact, so an incomplete TestSuite looked identical to a complete one.
`status` tracks the outcome: 'generating' while the workflow is still
running, 'complete'/'incomplete' once it finishes depending on whether every
Scenario got covered, 'terminated' once a user explicitly stops retrying an
'incomplete' suite. Existing rows predate this feature and already finished
under the old code path, so they're backfilled as 'complete'.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f4a6c8b0d2"
down_revision: str | None = "d4a6c8e0b2f4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "test_suite",
        sa.Column("status", sa.String(), nullable=False, server_default="complete"),
    )


def downgrade() -> None:
    op.drop_column("test_suite", "status")
