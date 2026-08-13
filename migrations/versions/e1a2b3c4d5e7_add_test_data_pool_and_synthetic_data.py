"""add test data pool and synthetic data entry

Revision ID: e1a2b3c4d5e7
Revises: c8e2a4f6b1d3
Create Date: 2026-08-04 00:00:00.000000

Story 2.20 Task 1: TestDataEntry, the user-seeded Test Data Pool.
Story 2.13 Task 4: SyntheticDataEntry, every value the Data Resolver used.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e1a2b3c4d5e7"
down_revision: str | None = "c8e2a4f6b1d3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "test_data_entry",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            primary_key=True,
        ),
        sa.Column("external_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("application.id"),
            nullable=False,
        ),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("normalized_key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=True),
        sa.Column("secret_ref", sa.String(), nullable=True),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("application_id", "normalized_key"),
    )
    op.create_index(
        "ix_test_data_entry_application_id", "test_data_entry", ["application_id"]
    )
    op.create_index(
        "ix_test_data_entry_normalized_key", "test_data_entry", ["normalized_key"]
    )
    op.create_index(
        "ix_test_data_entry_external_id", "test_data_entry", ["external_id"]
    )

    op.create_table(
        "synthetic_data_entry",
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
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("normalized_key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("is_placeholder_file", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_synthetic_data_entry_application_id", "synthetic_data_entry", ["application_id"]
    )
    op.create_index(
        "ix_synthetic_data_entry_discovery_run_id", "synthetic_data_entry", ["discovery_run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_synthetic_data_entry_discovery_run_id", table_name="synthetic_data_entry")
    op.drop_index("ix_synthetic_data_entry_application_id", table_name="synthetic_data_entry")
    op.drop_table("synthetic_data_entry")
    op.drop_index("ix_test_data_entry_external_id", table_name="test_data_entry")
    op.drop_index("ix_test_data_entry_normalized_key", table_name="test_data_entry")
    op.drop_index("ix_test_data_entry_application_id", table_name="test_data_entry")
    op.drop_table("test_data_entry")
