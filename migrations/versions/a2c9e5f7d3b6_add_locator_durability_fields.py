"""add locator durability fields

Revision ID: a2c9e5f7d3b6
Revises: f6a3c8d2b1e4
Create Date: 2026-08-03 00:00:00.000000

Story 2.21: ranked candidate locators on Action/FormField (capture-time),
plus fragile/durability_score on ComponentLocator (derivation-time).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a2c9e5f7d3b6"
down_revision: str | None = "f6a3c8d2b1e4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "action",
        sa.Column("locator_candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "form_field",
        sa.Column("locator_candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "component_locator",
        sa.Column("fragile", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "component_locator",
        sa.Column("durability_score", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("component_locator", "durability_score")
    op.drop_column("component_locator", "fragile")
    op.drop_column("form_field", "locator_candidates")
    op.drop_column("action", "locator_candidates")
