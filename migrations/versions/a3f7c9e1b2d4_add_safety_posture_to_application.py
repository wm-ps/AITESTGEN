"""add safety_posture to application

Revision ID: a3f7c9e1b2d4
Revises: e1a2b3c4d5e7
Create Date: 2026-08-04 00:00:00.000000

Story 2.12 Task 1: per-Application safety posture (`non_production` default
/ `production`) governing how Ambiguous actions are resolved.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f7c9e1b2d4"
down_revision: str | None = "e1a2b3c4d5e7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application",
        sa.Column(
            "safety_posture", sa.String(), nullable=False, server_default="non_production"
        ),
    )


def downgrade() -> None:
    op.drop_column("application", "safety_posture")
