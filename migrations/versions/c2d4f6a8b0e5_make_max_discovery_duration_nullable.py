"""make discovery_settings.max_discovery_duration_minutes nullable

Revision ID: c2d4f6a8b0e5
Revises: b3d7e9f1a5c7
Create Date: 2026-08-25 00:00:00.000000

None = unlimited (discovery runs as long as it can), matching the
max_journeys/max_scenarios_per_journey/max_test_cases_per_application
nullable-cap convention.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d4f6a8b0e5"
down_revision: str | None = "b3d7e9f1a5c7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("discovery_settings", "max_discovery_duration_minutes", nullable=True)


def downgrade() -> None:
    op.execute("UPDATE discovery_settings SET max_discovery_duration_minutes = 30 WHERE max_discovery_duration_minutes IS NULL")
    op.alter_column("discovery_settings", "max_discovery_duration_minutes", nullable=False)
