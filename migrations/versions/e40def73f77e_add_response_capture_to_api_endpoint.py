"""add response capture to api_endpoint

Revision ID: e40def73f77e
Revises: d1e9a4b6f2c3
Create Date: 2026-07-18 00:00:01.000000

Discovery-crawl improvement pass: `ApiEndpoint` previously captured only
method/path — no way to tell a successful call from a failing one, so a
negative/error-path Scenario (Story 4.1) had nothing to draw from. Both
columns are nullable since a pre-existing row has no response to backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e40def73f77e"
down_revision: str | None = "d1e9a4b6f2c3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("api_endpoint", sa.Column("status_code", sa.Integer(), nullable=True))
    op.add_column(
        "api_endpoint",
        sa.Column("response_summary", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_endpoint", "response_summary")
    op.drop_column("api_endpoint", "status_code")
