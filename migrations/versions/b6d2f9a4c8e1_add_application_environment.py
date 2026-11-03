"""add application_environment, test_run.environment_id, schedule.environment_id

Revision ID: b6d2f9a4c8e1
Revises: f3c8a1d5e2b7
Create Date: 2026-11-03 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b6d2f9a4c8e1"
down_revision: str | None = "f3c8a1d5e2b7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_environment",
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
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("login_url", sa.String(), nullable=True),
        sa.Column("auth_method", sa.String(), nullable=False),
        sa.Column("requires_login", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("secret_ref", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_application_environment_external_id",
        "application_environment",
        ["external_id"],
        unique=True,
    )
    op.create_index(
        "ix_application_environment_application_id", "application_environment", ["application_id"]
    )
    # Name is unique per application, case-insensitively.
    op.create_index(
        "uq_application_environment_application_id_name",
        "application_environment",
        ["application_id", sa.text("lower(name)")],
        unique=True,
    )

    # Nullable, no backfill: NULL = the Application's own (default) environment.
    for table in ("test_run", "schedule"):
        op.add_column(
            table,
            sa.Column(
                "environment_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("application_environment.id", ondelete="RESTRICT"),
                nullable=True,
            ),
        )
        op.create_index(f"ix_{table}_environment_id", table, ["environment_id"])


def downgrade() -> None:
    for table in ("schedule", "test_run"):
        op.drop_index(f"ix_{table}_environment_id", table_name=table)
        op.drop_column(table, "environment_id")
    op.drop_index(
        "uq_application_environment_application_id_name", table_name="application_environment"
    )
    op.drop_index(
        "ix_application_environment_application_id", table_name="application_environment"
    )
    op.drop_index("ix_application_environment_external_id", table_name="application_environment")
    op.drop_table("application_environment")
