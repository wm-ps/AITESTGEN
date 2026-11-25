"""ApplicationMember — who has access to an Application, and as what role.

One row per (application, person). An application is visible only to the
people with a row here, plus the team admins and super admins who hold
implicit admin rights (see `api.access`). The person who added an application
gets an `app_admin` row at creation; that row is "locked" (`user_id ==
Application.created_by_id`) and can't be edited or removed.

Roles, lowest to highest: `viewer` (read only), `contributor` (run, edit,
generate; no settings), `app_admin` (everything, including sharing).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

APP_ADMIN_ROLE = "app_admin"
CONTRIBUTOR_ROLE = "contributor"
VIEWER_APP_ROLE = "viewer"
# Lowest first: a role satisfies a minimum when its index is >= the minimum's.
APP_ROLES = (VIEWER_APP_ROLE, CONTRIBUTOR_ROLE, APP_ADMIN_ROLE)


class ApplicationMember(SQLModel, table=True):
    __tablename__ = "application_member"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("application_id", "user_id", name="uq_application_member_app_user"),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")),
    )
    application_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("application.id", ondelete="CASCADE"), nullable=False, index=True
        ),
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("platform_user.id", ondelete="CASCADE"), nullable=False, index=True
        ),
    )
    role: str = Field(default=VIEWER_APP_ROLE, nullable=False)
    granted_by_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("platform_user.id", ondelete="SET NULL"), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
