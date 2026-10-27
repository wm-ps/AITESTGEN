"""add explorer_run.started_by_id — who to email when a run needs them

Revision ID: d7f9b1c3e5a8
Revises: c6e8a0b2d4f7
Create Date: 2026-10-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d7f9b1c3e5a8"
down_revision: str | None = "c6e8a0b2d4f7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "explorer_run",
        sa.Column(
            "started_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("platform_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("explorer_run", "started_by_id")
