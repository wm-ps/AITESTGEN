"""remove evidence, add application model entities

Revision ID: d1e9a4b6f2c3
Revises: fc7fe4561f07
Create Date: 2026-07-18 00:00:00.000000

Sprint Change Proposal 2026-07-18: the generic `Evidence` table is removed in
full — Story 2.2 (rework) writes typed rows directly (`Page`/`Form`/
`FormField`/`ValidationRule`/`Action`/`ApiEndpoint`/`PageTransition`), and
Story 2.5 adds the derived-only entities (`Component`/`ComponentLocator`/
`Assertion`). `FormField.component_id` is created here as a plain column
(no FK) since `component` doesn't exist until later in this same migration —
the FK is added via a follow-up `create_foreign_key` once `component` exists.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e9a4b6f2c3"
down_revision: str | None = "fc7fe4561f07"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # --- drop the removed Evidence table ---
    op.drop_constraint("fk_evidence_journey_id_journey", "evidence", type_="foreignkey")
    op.drop_index(op.f("ix_evidence_journey_id"), table_name="evidence")
    op.drop_index(op.f("ix_evidence_external_id"), table_name="evidence")
    op.drop_index(op.f("ix_evidence_discovery_run_id"), table_name="evidence")
    op.drop_table("evidence")

    # --- Story 2.2: typed capture entities ---
    op.create_table(
        "page",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("discovery_run_id", sa.UUID(), nullable=False),
        sa.Column("merged_into_id", sa.UUID(), nullable=True),
        sa.Column("journey_id", sa.UUID(), nullable=True),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("object_storage_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"]),
        sa.ForeignKeyConstraint(["discovery_run_id"], ["discovery_run.id"]),
        sa.ForeignKeyConstraint(["merged_into_id"], ["page.id"], name="fk_page_merged_into_id_page"),
        sa.ForeignKeyConstraint(["journey_id"], ["journey.id"], name="fk_page_journey_id_journey"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_page_application_id"), "page", ["application_id"], unique=False)
    op.create_index(op.f("ix_page_discovery_run_id"), "page", ["discovery_run_id"], unique=False)
    op.create_index(op.f("ix_page_merged_into_id"), "page", ["merged_into_id"], unique=False)
    op.create_index(op.f("ix_page_journey_id"), "page", ["journey_id"], unique=False)

    op.create_table(
        "form",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("discovery_run_id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("merged_into_id", sa.UUID(), nullable=True),
        sa.Column("journey_id", sa.UUID(), nullable=True),
        sa.Column("action_url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("method", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"]),
        sa.ForeignKeyConstraint(["discovery_run_id"], ["discovery_run.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["page.id"]),
        sa.ForeignKeyConstraint(["merged_into_id"], ["form.id"], name="fk_form_merged_into_id_form"),
        sa.ForeignKeyConstraint(["journey_id"], ["journey.id"], name="fk_form_journey_id_journey"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_form_application_id"), "form", ["application_id"], unique=False)
    op.create_index(op.f("ix_form_discovery_run_id"), "form", ["discovery_run_id"], unique=False)
    op.create_index(op.f("ix_form_page_id"), "form", ["page_id"], unique=False)
    op.create_index(op.f("ix_form_merged_into_id"), "form", ["merged_into_id"], unique=False)
    op.create_index(op.f("ix_form_journey_id"), "form", ["journey_id"], unique=False)

    op.create_table(
        "form_field",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("form_id", sa.UUID(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("input_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("default_value", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("captured_selector", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("component_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["form_id"], ["form.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_form_field_form_id"), "form_field", ["form_id"], unique=False)
    op.create_index(
        op.f("ix_form_field_component_id"), "form_field", ["component_id"], unique=False
    )

    op.create_table(
        "validation_rule",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("form_field_id", sa.UUID(), nullable=False),
        sa.Column("rule_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["form_field_id"], ["form_field.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_validation_rule_form_field_id"), "validation_rule", ["form_field_id"], unique=False
    )

    op.create_table(
        "action",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("discovery_run_id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("captured_selector", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("representative", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"]),
        sa.ForeignKeyConstraint(["discovery_run_id"], ["discovery_run.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["page.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_action_application_id"), "action", ["application_id"], unique=False)
    op.create_index(op.f("ix_action_discovery_run_id"), "action", ["discovery_run_id"], unique=False)
    op.create_index(op.f("ix_action_page_id"), "action", ["page_id"], unique=False)

    op.create_table(
        "api_endpoint",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("discovery_run_id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("merged_into_id", sa.UUID(), nullable=True),
        sa.Column("journey_id", sa.UUID(), nullable=True),
        sa.Column("method", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("path", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"]),
        sa.ForeignKeyConstraint(["discovery_run_id"], ["discovery_run.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["page.id"]),
        sa.ForeignKeyConstraint(
            ["merged_into_id"], ["api_endpoint.id"], name="fk_api_endpoint_merged_into_id_api_endpoint"
        ),
        sa.ForeignKeyConstraint(
            ["journey_id"], ["journey.id"], name="fk_api_endpoint_journey_id_journey"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_api_endpoint_application_id"), "api_endpoint", ["application_id"], unique=False
    )
    op.create_index(
        op.f("ix_api_endpoint_discovery_run_id"), "api_endpoint", ["discovery_run_id"], unique=False
    )
    op.create_index(op.f("ix_api_endpoint_page_id"), "api_endpoint", ["page_id"], unique=False)
    op.create_index(
        op.f("ix_api_endpoint_merged_into_id"), "api_endpoint", ["merged_into_id"], unique=False
    )
    op.create_index(op.f("ix_api_endpoint_journey_id"), "api_endpoint", ["journey_id"], unique=False)

    op.create_table(
        "page_transition",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("discovery_run_id", sa.UUID(), nullable=False),
        sa.Column("from_page_id", sa.UUID(), nullable=False),
        sa.Column("to_page_id", sa.UUID(), nullable=False),
        sa.Column("triggered_by_action_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"]),
        sa.ForeignKeyConstraint(["discovery_run_id"], ["discovery_run.id"]),
        sa.ForeignKeyConstraint(
            ["from_page_id"], ["page.id"], name="fk_page_transition_from_page_id_page"
        ),
        sa.ForeignKeyConstraint(
            ["to_page_id"], ["page.id"], name="fk_page_transition_to_page_id_page"
        ),
        sa.ForeignKeyConstraint(["triggered_by_action_id"], ["action.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_page_transition_application_id"), "page_transition", ["application_id"], unique=False
    )
    op.create_index(
        op.f("ix_page_transition_discovery_run_id"),
        "page_transition",
        ["discovery_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_page_transition_from_page_id"), "page_transition", ["from_page_id"], unique=False
    )
    op.create_index(
        op.f("ix_page_transition_to_page_id"), "page_transition", ["to_page_id"], unique=False
    )
    op.create_index(
        op.f("ix_page_transition_triggered_by_action_id"),
        "page_transition",
        ["triggered_by_action_id"],
        unique=False,
    )

    # --- Story 2.5: derived-only entities ---
    op.create_table(
        "component",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("form_id", sa.UUID(), nullable=True),
        sa.Column("journey_id", sa.UUID(), nullable=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("action", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("target_page_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["page.id"], name="fk_component_page_id_page"),
        sa.ForeignKeyConstraint(["form_id"], ["form.id"]),
        sa.ForeignKeyConstraint(["journey_id"], ["journey.id"]),
        sa.ForeignKeyConstraint(
            ["target_page_id"], ["page.id"], name="fk_component_target_page_id_page"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_component_external_id"), "component", ["external_id"], unique=True)
    op.create_index(
        op.f("ix_component_application_id"), "component", ["application_id"], unique=False
    )
    op.create_index(op.f("ix_component_page_id"), "component", ["page_id"], unique=False)
    op.create_index(op.f("ix_component_form_id"), "component", ["form_id"], unique=False)
    op.create_index(op.f("ix_component_journey_id"), "component", ["journey_id"], unique=False)
    op.create_index(
        op.f("ix_component_target_page_id"), "component", ["target_page_id"], unique=False
    )

    op.create_table(
        "component_locator",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("component_id", sa.UUID(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("strategy", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["component.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_component_locator_external_id"), "component_locator", ["external_id"], unique=True
    )
    op.create_index(
        op.f("ix_component_locator_component_id"), "component_locator", ["component_id"], unique=False
    )

    op.create_table(
        "assertion",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("component_id", sa.UUID(), nullable=True),
        sa.Column("journey_id", sa.UUID(), nullable=True),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "expected_value", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["page.id"]),
        sa.ForeignKeyConstraint(["component_id"], ["component.id"]),
        sa.ForeignKeyConstraint(["journey_id"], ["journey.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assertion_external_id"), "assertion", ["external_id"], unique=True)
    op.create_index(
        op.f("ix_assertion_application_id"), "assertion", ["application_id"], unique=False
    )
    op.create_index(op.f("ix_assertion_page_id"), "assertion", ["page_id"], unique=False)
    op.create_index(op.f("ix_assertion_component_id"), "assertion", ["component_id"], unique=False)
    op.create_index(op.f("ix_assertion_journey_id"), "assertion", ["journey_id"], unique=False)

    # form_field.component_id -> component.id, added now that `component` exists.
    op.create_foreign_key(
        "fk_form_field_component_id_component", "form_field", "component", ["component_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_form_field_component_id_component", "form_field", type_="foreignkey")

    op.drop_index(op.f("ix_assertion_journey_id"), table_name="assertion")
    op.drop_index(op.f("ix_assertion_component_id"), table_name="assertion")
    op.drop_index(op.f("ix_assertion_page_id"), table_name="assertion")
    op.drop_index(op.f("ix_assertion_application_id"), table_name="assertion")
    op.drop_index(op.f("ix_assertion_external_id"), table_name="assertion")
    op.drop_table("assertion")

    op.drop_index(op.f("ix_component_locator_component_id"), table_name="component_locator")
    op.drop_index(op.f("ix_component_locator_external_id"), table_name="component_locator")
    op.drop_table("component_locator")

    op.drop_index(op.f("ix_component_target_page_id"), table_name="component")
    op.drop_index(op.f("ix_component_journey_id"), table_name="component")
    op.drop_index(op.f("ix_component_form_id"), table_name="component")
    op.drop_index(op.f("ix_component_page_id"), table_name="component")
    op.drop_index(op.f("ix_component_application_id"), table_name="component")
    op.drop_index(op.f("ix_component_external_id"), table_name="component")
    op.drop_table("component")

    op.drop_index(op.f("ix_page_transition_triggered_by_action_id"), table_name="page_transition")
    op.drop_index(op.f("ix_page_transition_to_page_id"), table_name="page_transition")
    op.drop_index(op.f("ix_page_transition_from_page_id"), table_name="page_transition")
    op.drop_index(op.f("ix_page_transition_discovery_run_id"), table_name="page_transition")
    op.drop_index(op.f("ix_page_transition_application_id"), table_name="page_transition")
    op.drop_table("page_transition")

    op.drop_index(op.f("ix_api_endpoint_journey_id"), table_name="api_endpoint")
    op.drop_index(op.f("ix_api_endpoint_merged_into_id"), table_name="api_endpoint")
    op.drop_index(op.f("ix_api_endpoint_page_id"), table_name="api_endpoint")
    op.drop_index(op.f("ix_api_endpoint_discovery_run_id"), table_name="api_endpoint")
    op.drop_index(op.f("ix_api_endpoint_application_id"), table_name="api_endpoint")
    op.drop_table("api_endpoint")

    op.drop_index(op.f("ix_action_page_id"), table_name="action")
    op.drop_index(op.f("ix_action_discovery_run_id"), table_name="action")
    op.drop_index(op.f("ix_action_application_id"), table_name="action")
    op.drop_table("action")

    op.drop_index(op.f("ix_validation_rule_form_field_id"), table_name="validation_rule")
    op.drop_table("validation_rule")

    op.drop_index(op.f("ix_form_field_component_id"), table_name="form_field")
    op.drop_index(op.f("ix_form_field_form_id"), table_name="form_field")
    op.drop_table("form_field")

    op.drop_index(op.f("ix_form_journey_id"), table_name="form")
    op.drop_index(op.f("ix_form_merged_into_id"), table_name="form")
    op.drop_index(op.f("ix_form_page_id"), table_name="form")
    op.drop_index(op.f("ix_form_discovery_run_id"), table_name="form")
    op.drop_index(op.f("ix_form_application_id"), table_name="form")
    op.drop_table("form")

    op.drop_index(op.f("ix_page_journey_id"), table_name="page")
    op.drop_index(op.f("ix_page_merged_into_id"), table_name="page")
    op.drop_index(op.f("ix_page_discovery_run_id"), table_name="page")
    op.drop_index(op.f("ix_page_application_id"), table_name="page")
    op.drop_table("page")

    # --- restore evidence (best-effort — this data is gone; shape only) ---
    op.create_table(
        "evidence",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("discovery_run_id", sa.UUID(), nullable=False),
        sa.Column("journey_id", sa.UUID(), nullable=True),
        sa.Column("type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("details", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("object_storage_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["discovery_run_id"], ["discovery_run.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evidence_discovery_run_id"), "evidence", ["discovery_run_id"], unique=False
    )
    op.create_index(op.f("ix_evidence_external_id"), "evidence", ["external_id"], unique=True)
    op.create_index(op.f("ix_evidence_journey_id"), "evidence", ["journey_id"], unique=False)
    op.create_foreign_key(
        "fk_evidence_journey_id_journey", "evidence", "journey", ["journey_id"], ["id"]
    )
