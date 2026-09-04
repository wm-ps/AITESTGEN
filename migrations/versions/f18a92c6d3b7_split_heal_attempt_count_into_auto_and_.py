"""split heal attempt count into auto and manual budgets

Revision ID: f18a92c6d3b7
Revises: 342463f450d5
Create Date: 2026-09-03 00:00:00.000000

Self-healing gains two independent attempt budgets instead of one shared
counter: automatic healing (run right after ExecuteTestActivity, capped at
the fixed AUTO_HEAL_ATTEMPT_CAP) and manual "Retry with self-healing"
(capped at the admin-configurable DiscoverySettings.max_heal_attempts).
Renaming the existing column (rather than dropping it) preserves prior
attempts as auto-origin history and gives any already-"spent" row under the
old shared semantics a clean, correct manual budget under the new one.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f18a92c6d3b7"
down_revision: str | None = "342463f450d5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("test_result", "heal_attempt_count", new_column_name="auto_heal_attempt_count")
    op.add_column(
        "test_result",
        sa.Column("manual_heal_attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("test_result", "manual_heal_attempt_count")
    op.alter_column("test_result", "auto_heal_attempt_count", new_column_name="heal_attempt_count")
