"""add schedule.test_collection_id

Revision ID: d8b4f1a2c6e3
Revises: c7a3e9d1b5f2
Create Date: 2026-11-06 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d8b4f1a2c6e3"
down_revision: str | None = "c7a3e9d1b5f2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Nullable: NULL = every current test case, so existing schedules (and the
    # seeded defaults) keep their application-wide behavior.
    op.add_column(
        "schedule",
        sa.Column(
            "test_collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_collection.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_schedule_test_collection_id", "schedule", ["test_collection_id"])


def downgrade() -> None:
    op.drop_index("ix_schedule_test_collection_id", table_name="schedule")
    op.drop_column("schedule", "test_collection_id")
