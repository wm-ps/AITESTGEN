"""add test_suite and test_asset entities

Revision ID: a4e1f9c2b7d3
Revises: b629403bf8d9
Create Date: 2026-07-23 00:00:00.000000

Story 4.2: `TestSuite` (one per Journey per attempt, auto-named from the
Journey) and `TestAsset` (one per Scenario, compiled Playwright code,
belonging to its Journey's `TestSuite`). `TestAsset` deliberately has no
`generation_run_id` column of its own — it's always derived via
`test_suite_id` -> `TestSuite.generation_run_id`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4e1f9c2b7d3"
down_revision: str | None = "b629403bf8d9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "test_suite",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("journey_id", sa.UUID(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("generation_run_id", sa.Integer(), nullable=False),
        sa.Column("current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journey_id"], ["journey.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "journey_id", "generation_run_id", name="uq_test_suite_journey_id_generation_run_id"
        ),
    )
    op.create_index(op.f("ix_test_suite_external_id"), "test_suite", ["external_id"], unique=True)
    op.create_index(op.f("ix_test_suite_journey_id"), "test_suite", ["journey_id"], unique=False)

    op.create_table(
        "test_asset",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("scenario_id", sa.UUID(), nullable=False),
        sa.Column("test_suite_id", sa.UUID(), nullable=False),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario.id"]),
        sa.ForeignKeyConstraint(["test_suite_id"], ["test_suite.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_test_asset_external_id"), "test_asset", ["external_id"], unique=True)
    op.create_index(op.f("ix_test_asset_scenario_id"), "test_asset", ["scenario_id"], unique=False)
    op.create_index(
        op.f("ix_test_asset_test_suite_id"), "test_asset", ["test_suite_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_test_asset_test_suite_id"), table_name="test_asset")
    op.drop_index(op.f("ix_test_asset_scenario_id"), table_name="test_asset")
    op.drop_index(op.f("ix_test_asset_external_id"), table_name="test_asset")
    op.drop_table("test_asset")
    op.drop_index(op.f("ix_test_suite_journey_id"), table_name="test_suite")
    op.drop_index(op.f("ix_test_suite_external_id"), table_name="test_suite")
    op.drop_table("test_suite")
