"""add organization_limits

Revision ID: a8c2e5f7b1d3
Revises: f6a3d9b2c4e8
Create Date: 2026-11-23 02:00:00.000000

The ceilings a super admin sets on resource settings (Explorer limits,
discovery and generation limits) and the floor on retention. No row, or an
empty one, means no limits, so this changes nothing until someone sets one.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a8c2e5f7b1d3"
down_revision: str | None = "f6a3d9b2c4e8"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_limits",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("maximums", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("min_delete_project_after", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id"),
    )


def downgrade() -> None:
    op.drop_table("organization_limits")
