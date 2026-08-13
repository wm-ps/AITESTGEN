"""rename crawl_settings to discovery_settings

Revision ID: e4f6a8b0d2c3
Revises: d3e5f7a9c1b2
Create Date: 2026-08-06 00:00:01.000000

Terminology fix: this codebase's established word for this concept is
"discovery" (DiscoveryRun, discovery_worker), not "crawl" — renaming the
table/column/constraint the previous migration just added, rather than
editing an already-applied migration.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f6a8b0d2c3"
down_revision: str | None = "d3e5f7a9c1b2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("crawl_settings", "discovery_settings")
    op.alter_column(
        "discovery_settings", "max_crawl_duration_minutes", new_column_name="max_discovery_duration_minutes"
    )
    op.drop_constraint("crawl_settings_singleton", "discovery_settings", type_="check")
    op.create_check_constraint("discovery_settings_singleton", "discovery_settings", "id = 1")


def downgrade() -> None:
    op.drop_constraint("discovery_settings_singleton", "discovery_settings", type_="check")
    op.create_check_constraint("crawl_settings_singleton", "discovery_settings", "id = 1")
    op.alter_column(
        "discovery_settings", "max_discovery_duration_minutes", new_column_name="max_crawl_duration_minutes"
    )
    op.rename_table("discovery_settings", "crawl_settings")
