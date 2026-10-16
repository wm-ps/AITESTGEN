"""add discovery_required to application

Revision ID: d4a1c7e9b3f2
Revises: b8d4f6a0c2e3
Create Date: 2026-10-16 00:00:00.000000

Add Application's "Autonomous discovery" checkbox: when false the crawler is
never started for the Application. Existing rows backfill to true (today's
behavior) via the server default.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4a1c7e9b3f2"
down_revision: str | None = "b8d4f6a0c2e3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application",
        sa.Column(
            "discovery_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("application", "discovery_required")
