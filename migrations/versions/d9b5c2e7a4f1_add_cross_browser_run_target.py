"""add the browsers + window size a run executes against

Revision ID: d9b5c2e7a4f1
Revises: d8f4b2c6e1a3
Create Date: 2026-11-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d9b5c2e7a4f1"
down_revision: str | None = "d8f4b2c6e1a3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Server defaults are what execution always did (Chromium at 1280x720), so
    # every existing row reads correctly with no backfill.
    op.add_column(
        "test_result",
        sa.Column("browser", sa.String(), nullable=False, server_default=sa.text("'chromium'")),
    )
    op.add_column(
        "test_run",
        sa.Column(
            "browsers",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("""'["chromium"]'::jsonb"""),
        ),
    )
    op.add_column(
        "test_run",
        sa.Column("viewport_width", sa.Integer(), nullable=False, server_default=sa.text("1280")),
    )
    op.add_column(
        "test_run",
        sa.Column("viewport_height", sa.Integer(), nullable=False, server_default=sa.text("720")),
    )
    # NULL = Chromium at 1280x720, so every existing schedule keeps today's behavior.
    op.add_column("schedule", sa.Column("browsers", postgresql.JSONB(), nullable=True))
    op.add_column("schedule", sa.Column("viewport_width", sa.Integer(), nullable=True))
    op.add_column("schedule", sa.Column("viewport_height", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("schedule", "viewport_height")
    op.drop_column("schedule", "viewport_width")
    op.drop_column("schedule", "browsers")
    op.drop_column("test_run", "viewport_height")
    op.drop_column("test_run", "viewport_width")
    op.drop_column("test_run", "browsers")
    op.drop_column("test_result", "browser")
