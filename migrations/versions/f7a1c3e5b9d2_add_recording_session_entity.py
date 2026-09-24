"""add recording session entity

Revision ID: f7a1c3e5b9d2
Revises: c9e2a4f7b3d6
Create Date: 2026-09-18 00:00:00.000000

Record and Play feature: `RecordingSession` gates a worker-hosted, human-
driven `playwright codegen` session — mirrors `invite`/`password_reset`'s
token design (`token_hash` is the sole secret, sha256 of a raw token never
itself persisted) but adds a `status` column, since a recording session has
real async lifecycle beyond one-shot token validity that neither of those
two mirror models needed.

`Scenario.source` needs no migration to widen its Literal to add
`"recorded"` — it's already an untyped `String` column (same reasoning
already documented in `584191e291e5_add_scenario_source.py` for why adding
`"nl"` needed none).
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a1c3e5b9d2"
down_revision: str | None = "c9e2a4f7b3d6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recording_session",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("auth_mode", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sqlmodel.sql.sqltypes.AutoString(), server_default="pending", nullable=False
        ),
        sa.Column("error_message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("journey_external_id", sa.UUID(), nullable=True),
        sa.Column("scenario_external_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["platform_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recording_session_external_id"),
        "recording_session",
        ["external_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_recording_session_application_id"),
        "recording_session",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recording_session_token_hash"), "recording_session", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_recording_session_token_hash"), table_name="recording_session")
    op.drop_index(op.f("ix_recording_session_application_id"), table_name="recording_session")
    op.drop_index(op.f("ix_recording_session_external_id"), table_name="recording_session")
    op.drop_table("recording_session")
