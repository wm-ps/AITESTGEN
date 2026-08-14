"""make test_run execution_policy columns nullable

Revision ID: 8341132a4193
Revises: ecb9544baf0b
Create Date: 2026-08-11 00:00:00.000000

Run All Tests feature: execution-policy/allowlist/destructive-action gating
was removed from the run path per explicit request (see
`execution_worker.activities._prepare_test_run_sync`'s ponytail note) so
"Run All Tests" works with no setup. `TestRun.execution_policy_id`/
`execution_policy_version` are no longer always populated — made nullable
rather than dropped, in case policy-gated execution is reintroduced later.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8341132a4193"
down_revision: str | None = "ecb9544baf0b"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("test_run", "execution_policy_id", existing_type=sa.UUID(), nullable=True)
    op.alter_column(
        "test_run", "execution_policy_version", existing_type=sa.Integer(), nullable=True
    )


def downgrade() -> None:
    op.alter_column(
        "test_run", "execution_policy_version", existing_type=sa.Integer(), nullable=False
    )
    op.alter_column("test_run", "execution_policy_id", existing_type=sa.UUID(), nullable=False)
