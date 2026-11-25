"""Team — a shared workspace, and `TeamMember` — who is in which team.

A person can be in many teams; a team has many people (`team_member`). The
team role (`team_admin` | `team_member`) is separate from the organisation
role (`super_admin` | `standard_user`, on `PlatformUser`) and from the
per-application role (`ApplicationMember`). Team membership gives access to
the *workspace*, not to every application in it.

`Application.team_id` NULL means a personal application — there is no row for a
personal workspace.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

TEAM_ADMIN_ROLE = "team_admin"
TEAM_MEMBER_ROLE = "team_member"
TEAM_ROLES = (TEAM_ADMIN_ROLE, TEAM_MEMBER_ROLE)
DEFAULT_TEAM_NAME = "Migrated"


class Team(SQLModel, table=True):
    __tablename__ = "team"  # pyright: ignore[reportAssignmentType]
    # Names are unique per organisation, ignoring case.
    __table_args__ = (Index("ux_team_org_lower_name", "organization_id", func.lower(text("name")), unique=True),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")),
    )
    external_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), unique=True, nullable=False, index=True),
    )
    organization_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True),
    )
    name: str
    # The team every existing user and application moved into when teams
    # shipped. Exactly one per organisation.
    is_default: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false")))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class TeamMember(SQLModel, table=True):
    __tablename__ = "team_member"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member_team_user"),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")),
    )
    team_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("team.id", ondelete="CASCADE"), nullable=False, index=True),
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("platform_user.id", ondelete="CASCADE"), nullable=False, index=True
        ),
    )
    role: str = Field(default=TEAM_MEMBER_ROLE, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
