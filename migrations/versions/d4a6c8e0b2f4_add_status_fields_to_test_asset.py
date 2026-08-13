"""add requires_auth/status/warnings/primary_page_id to test_asset

Revision ID: d4a6c8e0b2f4
Revises: ac886e3061d8
Create Date: 2026-08-13 00:00:00.000000

Generation-pipeline hardening: `requires_auth` tags whether a TestAsset's
target page needed an authenticated session (drives the exported project's
auth/public Playwright project split); `status`/`warnings` hold the
post-generation linter's verdict (locator provenance, required-field
coverage, shared-auth-helper usage, sibling-spec consistency) — flag-only,
never blocking; `primary_page_id` is the Scenario's primary Page, needed to
group sibling TestAssets for the consistency check without re-deriving it
via Journey/JourneyStep on every read. All backfilled for existing rows via
server_default (`requires_auth=false`, `status='ready'`, `warnings='[]'`,
`primary_page_id` left null — no existing TestAsset has a computed one).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "d4a6c8e0b2f4"
down_revision: str | None = "ac886e3061d8"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "test_asset",
        sa.Column(
            "requires_auth", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "test_asset",
        sa.Column("status", sa.String(), nullable=False, server_default="ready"),
    )
    op.add_column(
        "test_asset",
        sa.Column("warnings", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "test_asset",
        sa.Column("primary_page_id", PGUUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_test_asset_primary_page_id_page",
        "test_asset",
        "page",
        ["primary_page_id"],
        ["id"],
    )
    op.create_index(
        "ix_test_asset_primary_page_id", "test_asset", ["primary_page_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_test_asset_primary_page_id", table_name="test_asset")
    op.drop_constraint("fk_test_asset_primary_page_id_page", "test_asset", type_="foreignkey")
    op.drop_column("test_asset", "primary_page_id")
    op.drop_column("test_asset", "warnings")
    op.drop_column("test_asset", "status")
    op.drop_column("test_asset", "requires_auth")
