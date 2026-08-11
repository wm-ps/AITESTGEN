"""add generation volume limits to discovery_settings

Revision ID: b9d1e3f5a7c2
Revises: f3b8e6a1c4d7
Create Date: 2026-08-11 00:00:00.000000

Per-run generation-volume caps for testing cost control: max journeys, max
scenarios per journey, max test cases (Playwright specs) per application.
All nullable — null means unlimited (today's behaviour).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9d1e3f5a7c2"
down_revision: str | None = "f3b8e6a1c4d7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("discovery_settings", sa.Column("max_journeys", sa.Integer(), nullable=True))
    op.add_column(
        "discovery_settings", sa.Column("max_scenarios_per_journey", sa.Integer(), nullable=True)
    )
    op.add_column(
        "discovery_settings",
        sa.Column("max_test_cases_per_application", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discovery_settings", "max_test_cases_per_application")
    op.drop_column("discovery_settings", "max_scenarios_per_journey")
    op.drop_column("discovery_settings", "max_journeys")
