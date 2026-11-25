"""WorkspaceSettings — a team's or a person's own values for the settings that
used to be organisation-wide (Explorer limits, retention, discovery and
generation defaults).

The existing singleton rows (`DiscoverySettings`, `ExplorerSettings`) stay as the
organisation default. A workspace stores only what it changed, in two JSON
dicts, and everything else keeps following the default — so a new team starts
with the default, and the code that reads settings changes in one place
(`discovery_settings.generation_settings_for` and `explorer_core.limits`).

Exactly one of `team_id` (a team's settings) and `owner_user_id` (a personal
workspace's) is set.
"""

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, Column, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, Session, SQLModel, select

from domain.application import Application


class WorkspaceSettings(SQLModel, table=True):
    __tablename__ = "workspace_settings"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        CheckConstraint(
            "(team_id IS NOT NULL AND owner_user_id IS NULL) OR (team_id IS NULL AND owner_user_id IS NOT NULL)",
            name="workspace_settings_one_owner",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")),
    )
    organization_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True),
    )
    team_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("team.id", ondelete="CASCADE"), unique=True, nullable=True),
    )
    owner_user_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("platform_user.id", ondelete="CASCADE"), unique=True, nullable=True
        ),
    )
    # DiscoverySettings fields this workspace changed, and ExplorerSettings fields.
    discovery: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    )
    explorer: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    )


def settings_for_team(session: Session, team_id: uuid.UUID) -> WorkspaceSettings | None:
    return session.exec(select(WorkspaceSettings).where(WorkspaceSettings.team_id == team_id)).first()


def settings_for_person(session: Session, user_id: uuid.UUID) -> WorkspaceSettings | None:
    return session.exec(select(WorkspaceSettings).where(WorkspaceSettings.owner_user_id == user_id)).first()


def settings_for_application(session: Session, application: Application) -> WorkspaceSettings | None:
    """The settings of the workspace an application lives in: its team, or — for
    a personal application — the person who added it."""
    if application.team_id is not None:
        return settings_for_team(session, application.team_id)
    if application.created_by_id is not None:
        return settings_for_person(session, application.created_by_id)
    return None
