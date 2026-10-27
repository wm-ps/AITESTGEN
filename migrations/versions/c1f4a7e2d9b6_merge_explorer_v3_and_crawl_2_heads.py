"""merge feature-explorerv3.0 and feature-crawl2.0 heads

Revision ID: c1f4a7e2d9b6
Revises: b9d3f5a7c2e4, e4c8b2d6f1a7
Create Date: 2026-10-27 00:00:00.000000

No schema change: joins Explorer's chain (saved screen routes, requires_login)
with crawl's (activity events, run reports, dropped application_context).
"""

from collections.abc import Sequence

revision: str = "c1f4a7e2d9b6"
down_revision: str | tuple[str, ...] | None = ("b9d3f5a7c2e4", "e4c8b2d6f1a7")
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
