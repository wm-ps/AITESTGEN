"""add activity_event

Revision ID: b7e3f1a9c2d4
Revises: b7e3d9a1c4f2
Create Date: 2026-10-26 00:00:00.000000

The admin Activity page's own records — config/team/schedule changes and
generation starts (see `domain.activity_event`). `application_id` is SET
NULL on purge so CleanupWorkflow's hard delete of an Application never
trips over its activity history.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b7e3f1a9c2d4"
down_revision: str | None = "b7e3d9a1c4f2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("application_name", sa.String(), nullable=True),
        sa.Column("actor_name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_activity_event_external_id"), "activity_event", ["external_id"], unique=True)
    op.create_index(op.f("ix_activity_event_organization_id"), "activity_event", ["organization_id"])
    op.create_index(op.f("ix_activity_event_application_id"), "activity_event", ["application_id"])
    op.create_index(op.f("ix_activity_event_created_at"), "activity_event", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_activity_event_created_at"), table_name="activity_event")
    op.drop_index(op.f("ix_activity_event_application_id"), table_name="activity_event")
    op.drop_index(op.f("ix_activity_event_organization_id"), table_name="activity_event")
    op.drop_index(op.f("ix_activity_event_external_id"), table_name="activity_event")
    op.drop_table("activity_event")
