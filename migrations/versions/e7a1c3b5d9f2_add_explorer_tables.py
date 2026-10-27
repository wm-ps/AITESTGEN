"""add Vantage Explorer tables (explorer_*)

Revision ID: e7a1c3b5d9f2
Revises: b8d4f6a0c2e3
Create Date: 2026-10-15 00:00:00.000000

Stage 1 of docs/vantage-explorer/PLAN.md: runs, live event feed, screenshots,
understood screens and health issues. Standalone from the classic discovery
tables — only `application` is referenced.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "e7a1c3b5d9f2"
down_revision: str | None = "b8d4f6a0c2e3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _run_fk() -> sa.Column:
    return sa.Column(
        "run_id",
        UUID(as_uuid=True),
        sa.ForeignKey("explorer_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "explorer_run",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", UUID(as_uuid=True), nullable=False, unique=True, index=True),
        sa.Column(
            "application_id",
            UUID(as_uuid=True),
            sa.ForeignKey("application.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("headline", sa.String(), nullable=False),
        sa.Column("health_score", sa.Integer(), nullable=True),
        sa.Column("requirements_first", sa.Boolean(), nullable=False),
        sa.Column("brief", JSONB(), nullable=True),
        sa.Column("brief_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "explorer_event",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        _run_fk(),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("shot_id", UUID(as_uuid=True), nullable=True),
        _created_at(),
    )
    op.create_table(
        "explorer_shot",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _run_fk(),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        _created_at(),
    )
    op.create_table(
        "explorer_screen",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _run_fk(),
        sa.Column("signature", sa.String(), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("entity", sa.String(), nullable=True),
        sa.Column("view_kind", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=True),
        sa.Column("purpose", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("url_pattern", sa.String(), nullable=False),
        sa.Column("visits", sa.Integer(), nullable=False),
        sa.Column("fields", JSONB(), nullable=False),
        sa.Column("actions", JSONB(), nullable=False),
        sa.Column("hidden_hints", JSONB(), nullable=False),
        sa.Column("reached_by", sa.String(), nullable=True),
        sa.Column("shot_id", UUID(as_uuid=True), nullable=True),
        _created_at(),
    )
    op.create_table(
        "explorer_health_issue",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _run_fk(),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("shot_id", UUID(as_uuid=True), nullable=True),
        _created_at(),
    )


def downgrade() -> None:
    for table in (
        "explorer_health_issue",
        "explorer_screen",
        "explorer_shot",
        "explorer_event",
        "explorer_run",
    ):
        op.drop_table(table)
