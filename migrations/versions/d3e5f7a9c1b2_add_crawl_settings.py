"""add crawl_settings singleton table

Revision ID: d3e5f7a9c1b2
Revises: a9f3d81c5e2b
Create Date: 2026-08-06 00:00:00.000000

Global crawl config (Max Pages, Max Crawl Duration, Navigation Timeout,
Interaction Level) — single row, fixed id=1, enforced by a check constraint.
Seeds the one row so every consumer can assume it exists.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e5f7a9c1b2"
down_revision: str | None = "a9f3d81c5e2b"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crawl_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("max_pages", sa.Integer(), nullable=False),
        sa.Column("max_crawl_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("navigation_timeout_seconds", sa.Float(), nullable=False),
        sa.Column("interaction_level", sa.String(), nullable=False),
        sa.CheckConstraint("id = 1", name="crawl_settings_singleton"),
    )
    op.execute(
        "INSERT INTO crawl_settings "
        "(id, max_pages, max_crawl_duration_minutes, navigation_timeout_seconds, interaction_level) "
        "VALUES (1, 500, 30, 15.0, 'normal')"
    )


def downgrade() -> None:
    op.drop_table("crawl_settings")
