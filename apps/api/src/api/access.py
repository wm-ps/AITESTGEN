"""Who may see an Application, and as what role (team workspaces).

One rule, used by every route that reaches an application, directly or through
a child row (journey, scenario, run, schedule, ...):

* **Super admin** — `app_admin` on every *team* application of their
  organisation. Personal applications are private, even from them.
* **Team admin** — `app_admin` on every application of their team.
* **Anyone else** — the role on their `application_member` row; no row means
  the application does not exist for them (404, never 403, so a hidden
  application can't be told apart from a missing one).

The caller's identity reaches these helpers through the request's database
session (`session.info`), set once by `auth.current_user`. A route that never
authenticated therefore has no actor and is refused — the lookups fail closed
instead of silently running without a role check. The minimum role defaults
from the HTTP method (read -> viewer, anything else -> contributor); routes
that need more (settings, credentials, access) or less pass `min_role`.

ponytail: the actor travels in `session.info` rather than as an explicit
argument so the ~130 existing application lookups keep their signature. A
fuller version threads the user through every helper; `min_role` stays optional
for the same reason.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from domain import (
    APP_ADMIN_ROLE,
    APP_ROLES,
    CONTRIBUTOR_ROLE,
    DEFAULT_TEAM_NAME,
    TEAM_ADMIN_ROLE,
    TEAM_MEMBER_ROLE,
    VIEWER_APP_ROLE,
    Application,
    ApplicationMember,
    PlatformUser,
    Team,
    TeamMember,
    application_role,
)
from fastapi import Depends, HTTPException, Request
from sqlalchemy import ColumnElement, and_, func, or_, true
from sqlmodel import Session, select

from api.auth import ACTOR_KEY, METHOD_KEY, SUPER_ADMIN_ROLE, CurrentUserDep, SessionDep

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class ApplicationHidden(Exception):
    """The caller has no access to this application at all."""


def actor(session: Session) -> PlatformUser:
    user = session.info.get(ACTOR_KEY)
    if user is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return user


def default_min_role(session: Session) -> str:
    method = session.info.get(METHOD_KEY, "POST")
    return VIEWER_APP_ROLE if method in _SAFE_METHODS else CONTRIBUTOR_ROLE


def role_at_least(role: str, minimum: str) -> bool:
    return APP_ROLES.index(role) >= APP_ROLES.index(minimum)


def authorize(
    session: Session,
    application: Application,
    organization_id: uuid.UUID,
    min_role: str | None = None,
) -> str:
    """The caller's role on `application`. Raises `ApplicationHidden` when they
    can't see it (the caller turns that into its own 404), 403 when they can
    but their role is too low."""
    user = actor(session)
    if application.organization_id != organization_id:
        raise ApplicationHidden
    role = application_role(session, user, application)
    if role is None:
        raise ApplicationHidden
    needed = min_role or default_min_role(session)
    if not role_at_least(role, needed):
        # Same wording the old org-level checks used.
        raise HTTPException(
            status_code=403, detail="admin role required" if needed == APP_ADMIN_ROLE else "view-only access"
        )
    return role


def require_application(
    session: Session,
    application: Application | None,
    organization_id: uuid.UUID,
    not_found: str,
    min_role: str | None = None,
) -> Application:
    """`authorize` for the child-row helpers: 404 with the helper's own message
    when the application (or its parent row) is missing or hidden."""
    if application is None:
        raise HTTPException(status_code=404, detail=not_found)
    try:
        authorize(session, application, organization_id, min_role)
    except ApplicationHidden:
        raise HTTPException(status_code=404, detail=not_found) from None
    return application


def visibility_clause(user: PlatformUser) -> ColumnElement[bool]:
    """SQL filter: the applications this user can see (any role)."""
    granted = Application.id.in_(  # type: ignore[attr-defined]
        select(ApplicationMember.application_id).where(ApplicationMember.user_id == user.id)
    )
    if user.role == SUPER_ADMIN_ROLE:
        return or_(granted, Application.team_id.is_not(None))  # type: ignore[union-attr]
    administers = Application.team_id.in_(  # type: ignore[union-attr]
        select(TeamMember.team_id).where(TeamMember.user_id == user.id, TeamMember.role == TEAM_ADMIN_ROLE)
    )
    return or_(granted, administers)


def admin_clause(user: PlatformUser) -> ColumnElement[bool]:
    """SQL filter: the applications this user administers (`app_admin`)."""
    granted = Application.id.in_(  # type: ignore[attr-defined]
        select(ApplicationMember.application_id).where(
            ApplicationMember.user_id == user.id, ApplicationMember.role == APP_ADMIN_ROLE
        )
    )
    if user.role == SUPER_ADMIN_ROLE:
        return or_(granted, Application.team_id.is_not(None))  # type: ignore[union-attr]
    administers = Application.team_id.in_(  # type: ignore[union-attr]
        select(TeamMember.team_id).where(TeamMember.user_id == user.id, TeamMember.role == TEAM_ADMIN_ROLE)
    )
    return or_(granted, administers)


def default_team_id(session: Session, user: PlatformUser) -> uuid.UUID | None:
    """The organisation's Default team, if the user is in it — where a new
    application lands until the workspace switcher chooses one explicitly."""
    return session.exec(
        select(Team.id)
        .join(TeamMember, and_(TeamMember.team_id == Team.id, TeamMember.user_id == user.id))  # type: ignore[arg-type]
        .where(Team.organization_id == user.organization_id, Team.is_default)  # type: ignore[arg-type]
    ).first()


def access_summary(session: Session, user: PlatformUser, application: Application) -> tuple[bool, bool, int]:
    """For the Applications list: did this user add it, was it shared with them
    (a grant that isn't their own adder row), and how many people it is shared
    with besides its adder."""
    added_by_me = application.created_by_id == user.id
    shared_with_me = (
        not added_by_me
        and session.exec(
            select(ApplicationMember.id).where(
                ApplicationMember.application_id == application.id, ApplicationMember.user_id == user.id
            )
        ).first()
        is not None
    )
    shared_with = session.exec(
        select(func.count(ApplicationMember.id)).where(  # type: ignore[arg-type]
            ApplicationMember.application_id == application.id,
            ApplicationMember.user_id != application.created_by_id,
        )
    ).one()
    return added_by_me, shared_with_me, shared_with


def ensure_default_team(session: Session, organization_id: uuid.UUID) -> Team:
    """The organisation's Default team, created on first use (the migration
    makes one for every organisation that exists today)."""
    team = session.exec(select(Team).where(Team.organization_id == organization_id, Team.is_default)).first()  # type: ignore[arg-type]
    if team is None:
        team = Team(organization_id=organization_id, name=DEFAULT_TEAM_NAME, is_default=True)
        session.add(team)
        session.flush()
    return team


def join_default_team(session: Session, user: PlatformUser) -> None:
    """New users start in the Default team. Caller commits."""
    team = ensure_default_team(session, user.organization_id)
    session.add(TeamMember(team_id=team.id, user_id=user.id, role=TEAM_MEMBER_ROLE))


def add_application_admin(session: Session, application: Application, user: PlatformUser) -> None:
    """Records who added the application and makes them its locked admin."""
    application.created_by_id = user.id
    application.created_by_name = user.name
    session.add(ApplicationMember(application_id=application.id, user_id=user.id, role=APP_ADMIN_ROLE, granted_by_id=user.id))


# --- the active workspace ----------------------------------------------------

WORKSPACE_HEADER = "X-Team-Id"
PERSONAL_WORKSPACE = "personal"


@dataclass(frozen=True)
class Workspace:
    """The workspace a list/create request is about: a team, or the caller's
    personal one (`team` is None)."""

    team: Team | None = None

    @property
    def is_personal(self) -> bool:
        return self.team is None


def active_workspace(request: Request, session: SessionDep, user: CurrentUserDep) -> Workspace | None:
    """The workspace named by the `X-Team-Id` header: a team's external id or
    "personal". Only list/create routes read it — routes addressed by an id find
    their application and ignore it. A team the caller isn't in is a 403 whether
    or not it exists.

    ponytail: no header means "everything I can see", not an error, so existing
    clients keep working; a fuller version makes it required on the routes that
    create things, so a forgotten header can never file an application under the
    wrong workspace."""
    header = request.headers.get(WORKSPACE_HEADER)
    if header is None or header == "":
        return None
    if header == PERSONAL_WORKSPACE:
        return Workspace(None)
    try:
        external_id = uuid.UUID(header)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid workspace") from None
    team = session.exec(
        select(Team).where(Team.external_id == external_id, Team.organization_id == user.organization_id)
    ).first()
    member = (
        team is not None
        and session.exec(select(TeamMember.id).where(TeamMember.team_id == team.id, TeamMember.user_id == user.id)).first()
        is not None
    )
    if team is None or not (member or user.role == SUPER_ADMIN_ROLE):
        raise HTTPException(status_code=403, detail="you are not in this team")
    return Workspace(team)


ActiveWorkspaceDep = Annotated[Workspace | None, Depends(active_workspace)]


def workspace_clause(workspace: Workspace | None) -> ColumnElement[bool]:
    """SQL filter for the active workspace; none = no filter."""
    if workspace is None:
        return true()
    if workspace.team is None:
        return Application.team_id.is_(None)  # type: ignore[union-attr]
    return Application.team_id == workspace.team.id
