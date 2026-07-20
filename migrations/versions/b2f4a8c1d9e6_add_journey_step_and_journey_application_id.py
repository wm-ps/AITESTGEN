"""add journey_step entity, journey.application_id, and race-safety unique constraints

Revision ID: b2f4a8c1d9e6
Revises: e40def73f77e
Create Date: 2026-07-20 00:00:00.000000

Story 2.6 rework: `Journey` gains a denormalized `application_id` (previously
only reachable transitively via `discovery_run_id -> DiscoveryRun.application_id`,
which Postgres cannot express a unique constraint across) so
`UNIQUE(application_id, identity_key)` is a real, single-table constraint —
this is what makes `InferenceActivity`'s find-or-create race-safe under
concurrent/overlapping runs, not just a select-then-create convention.
`Capability` gains the equivalent `UNIQUE(application_id, name)`. The bare
`journey_id` FK previously planned directly on `Page`/`Form`/`ApiEndpoint`/
`Component` is replaced before ever being built by the `journey_step` join
table (ordered, stage-labeled, and able to attribute one canonical row to
more than one Journey).
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2f4a8c1d9e6"
down_revision: str | None = "e40def73f77e"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # --- Drop the superseded bare journey_id FK on canonical rows ---
    # `JourneyStep` (below) replaces this: a bare FK had nowhere to record
    # step order/stage label and made it impossible for one canonical row
    # to support more than one Journey. `component`'s FK was created without
    # an explicit name in the original migration, hence the auto-generated
    # `_fkey` suffix here instead of this codebase's usual `fk_*` convention.
    op.drop_constraint("fk_page_journey_id_journey", "page", type_="foreignkey")
    op.drop_index(op.f("ix_page_journey_id"), table_name="page")
    op.drop_column("page", "journey_id")

    op.drop_constraint("fk_form_journey_id_journey", "form", type_="foreignkey")
    op.drop_index(op.f("ix_form_journey_id"), table_name="form")
    op.drop_column("form", "journey_id")

    op.drop_constraint("fk_api_endpoint_journey_id_journey", "api_endpoint", type_="foreignkey")
    op.drop_index(op.f("ix_api_endpoint_journey_id"), table_name="api_endpoint")
    op.drop_column("api_endpoint", "journey_id")

    op.drop_constraint("component_journey_id_fkey", "component", type_="foreignkey")
    op.drop_index(op.f("ix_component_journey_id"), table_name="component")
    op.drop_column("component", "journey_id")

    # --- Journey.application_id (denormalized) ---
    op.add_column("journey", sa.Column("application_id", sa.UUID(), nullable=True))
    op.execute(
        "UPDATE journey SET application_id = discovery_run.application_id "
        "FROM discovery_run WHERE journey.discovery_run_id = discovery_run.id"
    )
    op.alter_column("journey", "application_id", nullable=False)
    op.create_foreign_key(
        "fk_journey_application_id_application",
        "journey",
        "application",
        ["application_id"],
        ["id"],
    )

    # --- Race-safe uniqueness (replaces the old single-column identity_key index) ---
    op.drop_index(op.f("ix_journey_identity_key"), table_name="journey")
    op.create_unique_constraint(
        "uq_journey_application_id_identity_key", "journey", ["application_id", "identity_key"]
    )
    op.create_unique_constraint(
        "uq_capability_application_id_name", "capability", ["application_id", "name"]
    )

    # --- JourneyStep ---
    op.create_table(
        "journey_step",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("journey_id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=True),
        sa.Column("form_id", sa.UUID(), nullable=True),
        sa.Column("api_endpoint_id", sa.UUID(), nullable=True),
        sa.Column("component_id", sa.UUID(), nullable=True),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("stage_label", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journey_id"], ["journey.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["page.id"]),
        sa.ForeignKeyConstraint(["form_id"], ["form.id"]),
        sa.ForeignKeyConstraint(["api_endpoint_id"], ["api_endpoint.id"]),
        sa.ForeignKeyConstraint(["component_id"], ["component.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "journey_id", "step_order", name="uq_journey_step_journey_id_step_order"
        ),
        sa.CheckConstraint(
            "(CASE WHEN page_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN form_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN api_endpoint_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN component_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_journey_step_exactly_one_target",
        ),
    )
    op.create_index(
        op.f("ix_journey_step_journey_id"), "journey_step", ["journey_id"], unique=False
    )
    op.create_index(op.f("ix_journey_step_page_id"), "journey_step", ["page_id"], unique=False)
    op.create_index(op.f("ix_journey_step_form_id"), "journey_step", ["form_id"], unique=False)
    op.create_index(
        op.f("ix_journey_step_api_endpoint_id"), "journey_step", ["api_endpoint_id"], unique=False
    )
    op.create_index(
        op.f("ix_journey_step_component_id"), "journey_step", ["component_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_journey_step_component_id"), table_name="journey_step")
    op.drop_index(op.f("ix_journey_step_api_endpoint_id"), table_name="journey_step")
    op.drop_index(op.f("ix_journey_step_form_id"), table_name="journey_step")
    op.drop_index(op.f("ix_journey_step_page_id"), table_name="journey_step")
    op.drop_index(op.f("ix_journey_step_journey_id"), table_name="journey_step")
    op.drop_table("journey_step")

    op.drop_constraint("uq_capability_application_id_name", "capability", type_="unique")
    op.drop_constraint("uq_journey_application_id_identity_key", "journey", type_="unique")
    op.create_index(op.f("ix_journey_identity_key"), "journey", ["identity_key"], unique=False)

    op.drop_constraint("fk_journey_application_id_application", "journey", type_="foreignkey")
    op.drop_column("journey", "application_id")

    # --- Restore the bare journey_id FK on canonical rows ---
    op.add_column("component", sa.Column("journey_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_component_journey_id"), "component", ["journey_id"], unique=False)
    op.create_foreign_key(
        "component_journey_id_fkey", "component", "journey", ["journey_id"], ["id"]
    )

    op.add_column("api_endpoint", sa.Column("journey_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_api_endpoint_journey_id"), "api_endpoint", ["journey_id"], unique=False
    )
    op.create_foreign_key(
        "fk_api_endpoint_journey_id_journey", "api_endpoint", "journey", ["journey_id"], ["id"]
    )

    op.add_column("form", sa.Column("journey_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_form_journey_id"), "form", ["journey_id"], unique=False)
    op.create_foreign_key(
        "fk_form_journey_id_journey", "form", "journey", ["journey_id"], ["id"]
    )

    op.add_column("page", sa.Column("journey_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_page_journey_id"), "page", ["journey_id"], unique=False)
    op.create_foreign_key(
        "fk_page_journey_id_journey", "page", "journey", ["journey_id"], ["id"]
    )
