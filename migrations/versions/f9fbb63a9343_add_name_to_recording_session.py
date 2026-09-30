"""add name to recording_session

Revision ID: f9fbb63a9343
Revises: f7a1c3e5b9d2
Create Date: 2026-09-24 00:00:00.000000

Record and Play: the human now names a recording on the idle screen before
starting it (instead of every recording defaulting to a hardcoded
"Recorded flow" Journey/Scenario name, dedup-suffixed only by a counter).
`server_default` backfills any pre-existing row, then is dropped so every
future insert must supply its own name explicitly, same as every other
required column this table already has.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9fbb63a9343"
down_revision: str | None = "f7a1c3e5b9d2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recording_session",
        sa.Column(
            "name",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="Recorded flow",
        ),
    )
    op.alter_column("recording_session", "name", server_default=None)


def downgrade() -> None:
    op.drop_column("recording_session", "name")
