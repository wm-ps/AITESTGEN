"""add self-heal fields to test_result and discovery_settings

Revision ID: c4d6e8f0a2b4
Revises: b3d7e9f1a5c7
Create Date: 2026-08-25 00:00:00.000000

Self-healing for failed generated Playwright test cases: TestResult tracks
its own heal-attempt state, DiscoverySettings gains the admin-configurable
shared attempt budget (max_heal_attempts, default 3).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "c4d6e8f0a2b4"
down_revision: str | None = "b3d7e9f1a5c7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "test_result",
        sa.Column("heal_attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "test_result",
        sa.Column("healed_test_asset_id", PGUUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_test_result_healed_test_asset_id_test_asset",
        "test_result",
        "test_asset",
        ["healed_test_asset_id"],
        ["id"],
    )
    op.add_column(
        "test_result",
        sa.Column("heal_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    # discovery_settings is a singleton (id=1, seeded by an earlier
    # migration) and this column is non-nullable — server_default backfills
    # that one existing row.
    op.add_column(
        "discovery_settings",
        sa.Column("max_heal_attempts", sa.Integer(), nullable=False, server_default="3"),
    )


def downgrade() -> None:
    op.drop_column("discovery_settings", "max_heal_attempts")
    op.drop_constraint(
        "fk_test_result_healed_test_asset_id_test_asset", "test_result", type_="foreignkey"
    )
    op.drop_column("test_result", "heal_started_at")
    op.drop_column("test_result", "healed_test_asset_id")
    op.drop_column("test_result", "heal_attempt_count")
