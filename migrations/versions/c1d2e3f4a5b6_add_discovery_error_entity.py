"""add discovery error entity

Revision ID: c1d2e3f4a5b6
Revises: b4c8e2a6d1f9
Create Date: 2026-08-04 00:00:00.000000

Story 2.18 Task 1: DiscoveryError, a starter error taxonomy (DISC-001..006)
for engine crashes and target-application failures.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b4c8e2a6d1f9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discovery_error",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            primary_key=True,
        ),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("application.id"),
            nullable=False,
        ),
        sa.Column(
            "discovery_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("discovery_run.id"),
            nullable=False,
        ),
        sa.Column(
            "page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("page.id"), nullable=True
        ),
        sa.Column("error_code", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_discovery_error_application_id", "discovery_error", ["application_id"])
    op.create_index(
        "ix_discovery_error_discovery_run_id", "discovery_error", ["discovery_run_id"]
    )
    op.create_index(
        "ix_discovery_error_run_code", "discovery_error", ["discovery_run_id", "error_code"]
    )


def downgrade() -> None:
    op.drop_index("ix_discovery_error_run_code", table_name="discovery_error")
    op.drop_index("ix_discovery_error_discovery_run_id", table_name="discovery_error")
    op.drop_index("ix_discovery_error_application_id", table_name="discovery_error")
    op.drop_table("discovery_error")
