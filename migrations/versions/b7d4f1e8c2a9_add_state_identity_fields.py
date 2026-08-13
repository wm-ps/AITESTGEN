"""add state identity fields

Revision ID: b7d4f1e8c2a9
Revises: a2c9e5f7d3b6
Create Date: 2026-08-03 00:00:00.000000

Story 2.10: `Page.variant_of_page_id` (distinct from `merged_into_id` — a
live sibling, not a superseded duplicate) and per-Application state-identity
thresholds.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d4f1e8c2a9"
down_revision: str | None = "a2c9e5f7d3b6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("page", sa.Column("variant_of_page_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_page_variant_of_page_id"), "page", ["variant_of_page_id"])
    op.create_foreign_key(
        "fk_page_variant_of_page_id_page", "page", "page", ["variant_of_page_id"], ["id"]
    )
    op.add_column(
        "application",
        sa.Column(
            "state_identity_threshold_same", sa.Float(), nullable=False, server_default="0.75"
        ),
    )
    op.add_column(
        "application",
        sa.Column(
            "state_identity_threshold_new", sa.Float(), nullable=False, server_default="0.35"
        ),
    )


def downgrade() -> None:
    op.drop_column("application", "state_identity_threshold_new")
    op.drop_column("application", "state_identity_threshold_same")
    op.drop_constraint("fk_page_variant_of_page_id_page", "page", type_="foreignkey")
    op.drop_index(op.f("ix_page_variant_of_page_id"), table_name="page")
    op.drop_column("page", "variant_of_page_id")
