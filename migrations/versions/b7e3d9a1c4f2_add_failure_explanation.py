"""add failure_explanation

Revision ID: b7e3d9a1c4f2
Revises: a9c4e2b7d1f3
Create Date: 2026-10-26 00:00:00.000000

Cached LLM explanations of test failures no rule recognises, keyed by a hash
of the redacted error text (one LLM call per distinct error, ever). Separate
from test_result — self-healing never reads it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e3d9a1c4f2"
down_revision: str | None = "a9c4e2b7d1f3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "failure_explanation",
        sa.Column("error_fingerprint", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("detail", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("error_fingerprint"),
    )


def downgrade() -> None:
    op.drop_table("failure_explanation")
