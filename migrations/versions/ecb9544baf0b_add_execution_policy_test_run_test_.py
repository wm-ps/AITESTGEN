"""add execution_policy, test_run, test_result, test_result_artifact entities

Revision ID: ecb9544baf0b
Revises: f3b8e6a1c4d7
Create Date: 2026-08-11 00:00:00.000000

Run All Tests feature: `ExecutionPolicy` (per-Application execution
allowlist/toggle), `TestRun`/`TestResult` (one "Run All Tests" execution
attempt and its per-`TestAsset` outcomes), `TestResultArtifact`
(object-storage pointers for failure screenshots/traces), and
`Scenario.safety_classification`/`safety_classification_reason` (persisted
destructive-action gate, computed once at generation time).

Every pre-existing `Scenario` row gets `safety_classification='UNKNOWN'`
via the column's `server_default` — by design, `UNKNOWN` is blocked from
execution unless an `ExecutionPolicy` explicitly permits it, so a backfill
pass (out of scope for this migration) is needed before existing
applications can usefully "Run All Tests".
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "ecb9544baf0b"
down_revision: str | None = "f3b8e6a1c4d7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_policy",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("execution_enabled", sa.Boolean(), nullable=False),
        sa.Column("allowed_base_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("destructive_actions_permitted", sa.Boolean(), nullable=False),
        sa.Column("video_capture_enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_execution_policy_external_id"), "execution_policy", ["external_id"], unique=True
    )
    op.create_index(
        op.f("ix_execution_policy_application_id"),
        "execution_policy",
        ["application_id"],
        unique=True,
    )

    op.create_table(
        "test_run",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("execution_policy_id", sa.UUID(), nullable=False),
        sa.Column("execution_policy_version", sa.Integer(), nullable=False),
        sa.Column("environment_snapshot", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("target_base_url_snapshot", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("blocked_reason", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("passed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("timed_out_count", sa.Integer(), nullable=False),
        sa.Column("errored_count", sa.Integer(), nullable=False),
        sa.Column("blocked_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"]),
        sa.ForeignKeyConstraint(["execution_policy_id"], ["execution_policy.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_test_run_external_id"), "test_run", ["external_id"], unique=True)
    op.create_index(
        op.f("ix_test_run_application_id"), "test_run", ["application_id"], unique=False
    )

    op.create_table(
        "test_result",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("test_run_id", sa.UUID(), nullable=False),
        sa.Column("test_asset_id", sa.UUID(), nullable=False),
        sa.Column("scenario_id", sa.UUID(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("stack_trace", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("console_output", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("blocked_reason", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_run.id"]),
        sa.ForeignKeyConstraint(["test_asset_id"], ["test_asset.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_test_result_external_id"), "test_result", ["external_id"], unique=True
    )
    op.create_index(
        op.f("ix_test_result_test_run_id"), "test_result", ["test_run_id"], unique=False
    )
    op.create_index(
        op.f("ix_test_result_test_asset_id"), "test_result", ["test_asset_id"], unique=False
    )
    op.create_index(
        op.f("ix_test_result_scenario_id"), "test_result", ["scenario_id"], unique=False
    )

    op.create_table(
        "test_result_artifact",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("test_result_id", sa.UUID(), nullable=False),
        sa.Column("artifact_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("object_store_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("content_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["test_result_id"], ["test_result.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_test_result_artifact_external_id"),
        "test_result_artifact",
        ["external_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_test_result_artifact_test_result_id"),
        "test_result_artifact",
        ["test_result_id"],
        unique=False,
    )

    op.add_column(
        "scenario",
        sa.Column(
            "safety_classification",
            sqlmodel.sql.sqltypes.AutoString(),
            server_default="UNKNOWN",
            nullable=False,
        ),
    )
    op.add_column(
        "scenario",
        sa.Column(
            "safety_classification_reason", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("scenario", "safety_classification_reason")
    op.drop_column("scenario", "safety_classification")

    op.drop_index(op.f("ix_test_result_artifact_test_result_id"), table_name="test_result_artifact")
    op.drop_index(op.f("ix_test_result_artifact_external_id"), table_name="test_result_artifact")
    op.drop_table("test_result_artifact")

    op.drop_index(op.f("ix_test_result_scenario_id"), table_name="test_result")
    op.drop_index(op.f("ix_test_result_test_asset_id"), table_name="test_result")
    op.drop_index(op.f("ix_test_result_test_run_id"), table_name="test_result")
    op.drop_index(op.f("ix_test_result_external_id"), table_name="test_result")
    op.drop_table("test_result")

    op.drop_index(op.f("ix_test_run_application_id"), table_name="test_run")
    op.drop_index(op.f("ix_test_run_external_id"), table_name="test_run")
    op.drop_table("test_run")

    op.drop_index(op.f("ix_execution_policy_application_id"), table_name="execution_policy")
    op.drop_index(op.f("ix_execution_policy_external_id"), table_name="execution_policy")
    op.drop_table("execution_policy")
