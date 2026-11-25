"""Who may edit a workspace's settings, and where they are stored.

Settings used to be organisation-wide (one row each). They are now per
workspace: a team's, or a person's own for their personal workspace. The old
rows stay as the organisation default, and a workspace stores only what it
changed (`domain.WorkspaceSettings`); everything else keeps following the
default. Without an active workspace (an older client) the routes behave as
before: the organisation default, for super admins.

* A team's settings: its team admins and super admins.
* A personal workspace's settings: its owner.
* Everyone else gets the same 403 as before.
"""

from domain import (
    SUPER_ADMIN_ROLE,
    TEAM_ADMIN_ROLE,
    PlatformUser,
    TeamMember,
    WorkspaceSettings,
    settings_for_person,
    settings_for_team,
)
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api.access import Workspace


def require_settings_editor(session: Session, user: PlatformUser, workspace: Workspace | None) -> None:
    if workspace is None:
        allowed = user.role == SUPER_ADMIN_ROLE
    elif workspace.team is None:
        allowed = True  # your own personal workspace
    else:
        allowed = user.role == SUPER_ADMIN_ROLE or (
            session.exec(
                select(TeamMember.role).where(TeamMember.team_id == workspace.team.id, TeamMember.user_id == user.id)
            ).first()
            == TEAM_ADMIN_ROLE
        )
    if not allowed:
        raise HTTPException(status_code=403, detail="admin role required")


def settings_row(
    session: Session, user: PlatformUser, workspace: Workspace | None, *, create: bool
) -> WorkspaceSettings | None:
    """The workspace's own settings row (None for the organisation default); created on first save."""
    if workspace is None:
        return None
    row = (
        settings_for_person(session, user.id) if workspace.team is None else settings_for_team(session, workspace.team.id)
    )
    if row is None and create:
        row = WorkspaceSettings(
            organization_id=user.organization_id,
            team_id=None if workspace.team is None else workspace.team.id,
            owner_user_id=user.id if workspace.team is None else None,
        )
        # Two first saves at once: the loser's insert hits the unique key, so it uses the winner's row.
        try:
            with session.begin_nested():
                session.add(row)
        except IntegrityError:
            row = (
                settings_for_person(session, user.id)
                if workspace.team is None
                else settings_for_team(session, workspace.team.id)
            )
    return row
