"""add approved_domain (domain whitelist for application onboarding)

Revision ID: e4b8d2f6a1c3
Revises: e5b8c2f1a9d3
Create Date: 2026-10-29 00:00:00.000000

Admin-managed list of hosts an Application may be onboarded on. Backfilled
from each org's existing (non-deleted) Applications so nothing already
onboarded is blocked on deploy.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from urllib.parse import urlsplit

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4b8d2f6a1c3"
down_revision: str | None = "e5b8c2f1a9d3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approved_domain",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("host", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_by_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "host", name="uq_approved_domain_org_host"),
    )
    op.create_index(op.f("ix_approved_domain_external_id"), "approved_domain", ["external_id"], unique=True)
    op.create_index(op.f("ix_approved_domain_organization_id"), "approved_domain", ["organization_id"], unique=False)

    bind = op.get_bind()
    seen: set[tuple[uuid.UUID, str]] = set()
    for organization_id, url in bind.execute(
        sa.text("SELECT organization_id, url FROM application WHERE deleted_at IS NULL")
    ):
        host = (urlsplit(url.strip()).hostname or "").lower().rstrip(".")
        if host:
            seen.add((organization_id, host))
    if seen:
        bind.execute(
            sa.text(
                "INSERT INTO approved_domain (external_id, organization_id, host, created_by_name, created_at) "
                "VALUES (:external_id, :organization_id, :host, 'System', :created_at)"
            ),
            [
                {
                    "external_id": uuid.uuid4(),
                    "organization_id": organization_id,
                    "host": host,
                    "created_at": datetime.now(UTC),
                }
                for organization_id, host in seen
            ],
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_approved_domain_organization_id"), table_name="approved_domain")
    op.drop_index(op.f("ix_approved_domain_external_id"), table_name="approved_domain")
    op.drop_table("approved_domain")
