"""add diagnostic_record entity

Revision ID: d4b8f2c6e9a1
Revises: e7c2a4b9d105
Create Date: 2026-08-03 00:00:00.000000

Story 2.22 Task 1: the record_diagnostic() sink contract. One typed table,
`kind` indexed for per-section queries, `payload` JSONB so producer stories
(2.10-2.14, 2.19, 2.21) can add fields without a migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4b8f2c6e9a1"
down_revision: str | None = "e7c2a4b9d105"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_record",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("discovery_run_id", sa.UUID(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["discovery_run_id"], ["discovery_run.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_diagnostic_record_discovery_run_id"),
        "diagnostic_record",
        ["discovery_run_id"],
        unique=False,
    )
    op.create_index(op.f("ix_diagnostic_record_kind"), "diagnostic_record", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_diagnostic_record_kind"), table_name="diagnostic_record")
    op.drop_index(op.f("ix_diagnostic_record_discovery_run_id"), table_name="diagnostic_record")
    op.drop_table("diagnostic_record")
