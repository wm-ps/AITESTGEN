"""add test_collection, test_collection_member, test_run.test_collection_id

Revision ID: c7a3e9d1b5f2
Revises: b6d2f9a4c8e1
Create Date: 2026-11-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c7a3e9d1b5f2"
down_revision: str | None = "b6d2f9a4c8e1"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "test_collection",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("external_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("application.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_test_collection_external_id", "test_collection", ["external_id"], unique=True
    )
    op.create_index("ix_test_collection_application_id", "test_collection", ["application_id"])
    # Name is unique per application, case-insensitively.
    op.create_index(
        "uq_test_collection_application_id_name",
        "test_collection",
        ["application_id", sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "test_collection_member",
        sa.Column(
            "collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_collection.id"),
            primary_key=True,
        ),
        sa.Column(
            "scenario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scenario.id"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_test_collection_member_scenario_id", "test_collection_member", ["scenario_id"]
    )

    # Nullable, no backfill: NULL = Complete, Selective or scheduled run.
    op.add_column(
        "test_run",
        sa.Column(
            "test_collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_collection.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_test_run_test_collection_id", "test_run", ["test_collection_id"])


def downgrade() -> None:
    op.drop_index("ix_test_run_test_collection_id", table_name="test_run")
    op.drop_column("test_run", "test_collection_id")
    op.drop_index("ix_test_collection_member_scenario_id", table_name="test_collection_member")
    op.drop_table("test_collection_member")
    op.drop_index("uq_test_collection_application_id_name", table_name="test_collection")
    op.drop_index("ix_test_collection_application_id", table_name="test_collection")
    op.drop_index("ix_test_collection_external_id", table_name="test_collection")
    op.drop_table("test_collection")
