"""drop favicon_url from application

Story 1.6's browser tab branding turned out not to need a per-Application
favicon (it's static platform branding, not the target site's own icon) —
this reverts Task 7 of Story 1.3, which added the column solely to feed the
original (corrected) design of Story 1.6.

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-07-21 00:00:02.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("application", "favicon_url")


def downgrade() -> None:
    op.add_column(
        "application",
        sa.Column("favicon_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
