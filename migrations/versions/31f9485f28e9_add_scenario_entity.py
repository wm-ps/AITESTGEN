"""add scenario entity

Revision ID: 31f9485f28e9
Revises: b2f4a8c1d9e6
Create Date: 2026-07-21 00:00:00.000000

Story 4.1: an AI-generated integration test Scenario for a Journey. `steps`
and `test_data` are JSONB — `test_data` starts with every entry's `value`
null, filled in later by a reviewer via the API, never by the AI.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "31f9485f28e9"
down_revision: str | None = "b2f4a8c1d9e6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scenario",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("journey_id", sa.UUID(), nullable=False),
        sa.Column("type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expected_result", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("test_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generation_run_id", sa.Integer(), nullable=False),
        sa.Column("current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journey_id"], ["journey.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scenario_external_id"), "scenario", ["external_id"], unique=True)
    op.create_index(op.f("ix_scenario_journey_id"), "scenario", ["journey_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_scenario_journey_id"), table_name="scenario")
    op.drop_index(op.f("ix_scenario_external_id"), table_name="scenario")
    op.drop_table("scenario")
