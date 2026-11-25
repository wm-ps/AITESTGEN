"""Teams: who is in which team, and the workspace switcher.

A team is a shared workspace. Only a super admin creates teams and changes who
is in them; a team admin gets a read-only view of their own team. Team
membership gives access to the workspace, not to every application in it — that
is `ApplicationMember` (`api.application_access`).

Guards, enforced under row locks so two admins acting at once can't break them:
a team always keeps at least one team admin, and an organisation at least one
super admin (`api.main`).
"""

import uuid

from domain import (
    TEAM_ADMIN_ROLE,
    TEAM_MEMBER_ROLE,
    TEAM_ROLES,
    Application,
    ApplicationMember,
    PlatformUser,
    Team,
    TeamMember,
)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from api.access import PERSONAL_WORKSPACE, application_role, visibility_clause
from api.activity import record_activity
from api.auth import SUPER_ADMIN_ROLE, CurrentAdminDep, CurrentUserDep, SessionDep

router = APIRouter()

TEAM_NAME_TAKEN = "A team with this name already exists."
MAX_TEAM_NAME = 80


class WorkspaceRead(BaseModel):
    id: str  # a team's external id, or "personal"
    name: str
    kind: str  # "personal" | "team"
    # The caller's role there: super_admin | team_admin | team_member (null for personal).
    role: str | None = None
    is_default: bool = False
    application_count: int


class MyWorkspacesRead(BaseModel):
    personal: WorkspaceRead
    teams: list[WorkspaceRead]
    last_workspace: str | None = None


class TeamRead(BaseModel):
    id: uuid.UUID
    name: str
    is_default: bool
    team_admins: list[str]
    member_count: int
    application_count: int


class TeamPersonRead(BaseModel):
    name: str
    email: str
    role: str


class TeamApplicationRead(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    added_by_name: str | None
    # "Working on it": everyone with access.
    people: list[str]
    people_count: int
    my_role: str | None


class TeamCreate(BaseModel):
    name: str
    team_admin_emails: list[str] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value or len(value) > MAX_TEAM_NAME:
            raise ValueError(f"Enter a team name of up to {MAX_TEAM_NAME} characters.")
        return value


class TeamMemberAdd(BaseModel):
    email: str
    role: str = TEAM_MEMBER_ROLE

    @model_validator(mode="after")
    def _valid_role(self) -> TeamMemberAdd:
        if self.role not in TEAM_ROLES:
            raise ValueError(f"role must be one of {', '.join(TEAM_ROLES)}")
        return self


class TeamMemberRole(BaseModel):
    role: str

    @model_validator(mode="after")
    def _valid_role(self) -> TeamMemberRole:
        if self.role not in TEAM_ROLES:
            raise ValueError(f"role must be one of {', '.join(TEAM_ROLES)}")
        return self


class WorkspacePayload(BaseModel):
    workspace: str


# --- helpers -----------------------------------------------------------------


def _get_team(session: Session, organization_id: uuid.UUID, external_id: uuid.UUID) -> Team:
    team = session.exec(
        select(Team).where(Team.external_id == external_id, Team.organization_id == organization_id)
    ).first()
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    return team


def _viewable_team(session: Session, user: PlatformUser, external_id: uuid.UUID) -> Team:
    """A team the caller may look at: any team for a super admin, only their own
    for a team admin. Everyone else gets the same 404 as an unknown team."""
    team = _get_team(session, user.organization_id, external_id)
    if user.role != SUPER_ADMIN_ROLE:
        role = session.exec(
            select(TeamMember.role).where(TeamMember.team_id == team.id, TeamMember.user_id == user.id)
        ).first()
        if role != TEAM_ADMIN_ROLE:
            raise HTTPException(status_code=404, detail="team not found")
    return team


def _org_user(session: Session, organization_id: uuid.UUID, email: str) -> PlatformUser:
    """Unknown, in another organisation: the same 404."""
    person = session.exec(
        select(PlatformUser).where(PlatformUser.email == email, PlatformUser.organization_id == organization_id)
    ).first()
    if person is None:
        raise HTTPException(status_code=404, detail="person not found")
    return person


def _application_count(session: Session, team: Team) -> int:
    return session.exec(
        select(func.count(Application.id)).where(  # type: ignore[arg-type]
            Application.team_id == team.id,
            col(Application.deleted_at).is_(None),
        )
    ).one()


def _team_read(session: Session, team: Team) -> TeamRead:
    rows = session.exec(
        select(TeamMember.role, PlatformUser.name)
        .join(PlatformUser, col(PlatformUser.id) == col(TeamMember.user_id))
        .where(TeamMember.team_id == team.id)
        .order_by(PlatformUser.name)
    ).all()
    return TeamRead(
        id=team.external_id,
        name=team.name,
        is_default=team.is_default,
        team_admins=[name for role, name in rows if role == TEAM_ADMIN_ROLE],
        member_count=len(rows),
        application_count=_application_count(session, team),
    )


def _lock_team_admins(session: Session, team: Team) -> list[TeamMember]:
    """Locks every team-admin row of the team (in id order, the same for every
    caller, so they can't deadlock) before anyone counts them."""
    return list(
        session.exec(
            select(TeamMember)
            .where(TeamMember.team_id == team.id, TeamMember.role == TEAM_ADMIN_ROLE)
            .order_by(TeamMember.id)  # type: ignore[arg-type]
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    )


def _only_admin_message(person: PlatformUser, team: Team) -> str:
    return f"{person.name} is the only Team Admin of {team.name}. Assign another Team Admin first."


# --- the workspace switcher --------------------------------------------------


def _visible_count(session: Session, user: PlatformUser, *, team: Team | None) -> int:
    where = Application.team_id.is_(None) if team is None else Application.team_id == team.id  # type: ignore[union-attr]
    return session.exec(
        select(func.count(Application.id)).where(  # type: ignore[arg-type]
            Application.organization_id == user.organization_id,
            col(Application.deleted_at).is_(None),
            where,
            visibility_clause(user),
        )
    ).one()


@router.get("/me/workspaces", response_model=MyWorkspacesRead)
def my_workspaces(session: SessionDep, user: CurrentUserDep) -> MyWorkspacesRead:
    """What the switcher lists: the personal workspace plus the teams the caller
    is in — every team for a super admin, who can enter any of them."""
    roles = dict(
        session.exec(select(TeamMember.team_id, TeamMember.role).where(TeamMember.user_id == user.id)).all()
    )
    stmt = select(Team).where(Team.organization_id == user.organization_id).order_by(Team.name)
    if user.role != SUPER_ADMIN_ROLE:
        stmt = stmt.where(col(Team.id).in_(list(roles)))
    teams = [
        WorkspaceRead(
            id=str(team.external_id),
            name=team.name,
            kind="team",
            role=SUPER_ADMIN_ROLE if user.role == SUPER_ADMIN_ROLE else roles[team.id],
            is_default=team.is_default,
            application_count=_visible_count(session, user, team=team),
        )
        for team in session.exec(stmt).all()
    ]
    return MyWorkspacesRead(
        personal=WorkspaceRead(
            id=PERSONAL_WORKSPACE,
            name="My workspace",
            kind="personal",
            application_count=_visible_count(session, user, team=None),
        ),
        teams=teams,
        last_workspace=user.last_workspace,
    )


@router.patch("/me/workspace", status_code=204)
def remember_workspace(payload: WorkspacePayload, session: SessionDep, user: CurrentUserDep) -> None:
    """Where the user lands next time. A team they can't enter is refused."""
    target = payload.workspace
    if target != PERSONAL_WORKSPACE:
        try:
            external_id = uuid.UUID(target)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid workspace") from None
        team = _get_team(session, user.organization_id, external_id)
        in_team = session.exec(
            select(TeamMember.id).where(TeamMember.team_id == team.id, TeamMember.user_id == user.id)
        ).first()
        if in_team is None and user.role != SUPER_ADMIN_ROLE:
            raise HTTPException(status_code=403, detail="you are not in this team")
    user.last_workspace = target
    session.add(user)
    session.commit()


# --- teams -------------------------------------------------------------------


@router.get("/teams", response_model=list[TeamRead])
def list_teams(session: SessionDep, admin: CurrentAdminDep) -> list[TeamRead]:
    teams = session.exec(
        select(Team).where(Team.organization_id == admin.organization_id).order_by(Team.name)
    ).all()
    return [_team_read(session, team) for team in teams]


@router.post("/teams", response_model=TeamRead, status_code=201)
def create_team(payload: TeamCreate, session: SessionDep, admin: CurrentAdminDep) -> TeamRead:
    people: list[PlatformUser] = []
    for email in dict.fromkeys(payload.team_admin_emails):  # de-duplicated, order kept
        people.append(_org_user(session, admin.organization_id, email))
    team = Team(organization_id=admin.organization_id, name=payload.name)
    session.add(team)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail=TEAM_NAME_TAKEN) from None
    for person in people:
        session.add(TeamMember(team_id=team.id, user_id=person.id, role=TEAM_ADMIN_ROLE))
    record_activity(session, admin, "settings", f"Created team {team.name}")
    session.commit()
    return _team_read(session, team)


@router.get("/teams/{external_id}", response_model=TeamRead)
def get_team(external_id: uuid.UUID, session: SessionDep, user: CurrentUserDep) -> TeamRead:
    return _team_read(session, _viewable_team(session, user, external_id))


@router.delete("/teams/{external_id}", status_code=204)
def delete_team(external_id: uuid.UUID, session: SessionDep, admin: CurrentAdminDep) -> None:
    """Deletes an empty team. A team that still has applications — added by its
    members or at team scope — has to be cleaned up first: deleting them is the
    team's call, not a side effect of removing the team."""
    team = _get_team(session, admin.organization_id, external_id)
    applications = _application_count(session, team)
    if applications:
        noun = "application" if applications == 1 else "applications"
        raise HTTPException(
            status_code=409,
            detail=f"This team still has {applications} {noun}. Delete or move them before deleting the team.",
        )
    name = team.name
    # Deleted applications keep their row (soft delete) and so their team_id,
    # which has no ON DELETE — let go of it so the team row can go.
    for application in session.exec(select(Application).where(Application.team_id == team.id)).all():
        application.team_id = None
        session.add(application)
    for person in session.exec(
        select(PlatformUser).where(
            PlatformUser.organization_id == admin.organization_id,
            PlatformUser.last_workspace == str(team.external_id),
        )
    ).all():
        person.last_workspace = None
        session.add(person)
    session.delete(team)  # members and workspace settings cascade
    record_activity(session, admin, "settings", f"Deleted team {name}")
    session.commit()


@router.get("/teams/{external_id}/members", response_model=list[TeamPersonRead])
def list_team_members(external_id: uuid.UUID, session: SessionDep, user: CurrentUserDep) -> list[TeamPersonRead]:
    team = _viewable_team(session, user, external_id)
    rows = session.exec(
        select(TeamMember.role, PlatformUser)
        .join(PlatformUser, col(PlatformUser.id) == col(TeamMember.user_id))
        .where(TeamMember.team_id == team.id)
    ).all()
    rows = sorted(rows, key=lambda r: (r[0] != TEAM_ADMIN_ROLE, r[1].name.lower()))
    return [TeamPersonRead(name=person.name, email=person.email, role=role) for role, person in rows]


@router.post("/teams/{external_id}/members", response_model=TeamPersonRead, status_code=201)
def add_team_member(
    external_id: uuid.UUID, payload: TeamMemberAdd, session: SessionDep, admin: CurrentAdminDep
) -> TeamPersonRead:
    team = _get_team(session, admin.organization_id, external_id)
    person = _org_user(session, admin.organization_id, payload.email)
    session.add(TeamMember(team_id=team.id, user_id=person.id, role=payload.role))
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="This person is already in the team.") from None
    record_activity(session, admin, "settings", f"Added {person.name} to team {team.name} as {payload.role}")
    session.commit()
    return TeamPersonRead(name=person.name, email=person.email, role=payload.role)


def _member(session: Session, team: Team, person: PlatformUser) -> TeamMember:
    member = session.exec(
        select(TeamMember)
        .where(TeamMember.team_id == team.id, TeamMember.user_id == person.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if member is None:
        raise HTTPException(status_code=404, detail="person not found")
    return member


@router.patch("/teams/{external_id}/members/{email}", response_model=TeamPersonRead)
def change_member_role_in_team(
    external_id: uuid.UUID, email: str, payload: TeamMemberRole, session: SessionDep, admin: CurrentAdminDep
) -> TeamPersonRead:
    team = _get_team(session, admin.organization_id, external_id)
    person = _org_user(session, admin.organization_id, email)
    admins = _lock_team_admins(session, team)
    member = _member(session, team, person)
    if member.role == TEAM_ADMIN_ROLE and payload.role != TEAM_ADMIN_ROLE and len(admins) <= 1:
        raise HTTPException(status_code=409, detail=_only_admin_message(person, team))
    if member.role != payload.role:
        record_activity(
            session, admin, "settings", f"Changed {person.name}'s role in team {team.name} from {member.role} to {payload.role}"
        )
        member.role = payload.role
        session.add(member)
    session.commit()
    return TeamPersonRead(name=person.name, email=person.email, role=member.role)


@router.delete("/teams/{external_id}/members/{email}", status_code=204)
def remove_member_from_team(external_id: uuid.UUID, email: str, session: SessionDep, admin: CurrentAdminDep) -> None:
    """Takes the person out of the team and out of every application of the team
    that was shared with them. Applications they added stay with the team, under
    its team admins."""
    team = _get_team(session, admin.organization_id, external_id)
    person = _org_user(session, admin.organization_id, email)
    admins = _lock_team_admins(session, team)
    member = _member(session, team, person)
    if member.role == TEAM_ADMIN_ROLE and len(admins) <= 1:
        raise HTTPException(status_code=409, detail=_only_admin_message(person, team))
    team_applications = select(Application.id).where(Application.team_id == team.id)
    for grant in session.exec(
        select(ApplicationMember).where(
            col(ApplicationMember.user_id) == person.id,
            col(ApplicationMember.application_id).in_(team_applications),
        )
    ).all():
        session.delete(grant)
    session.delete(member)
    record_activity(session, admin, "settings", f"Removed {person.name} from team {team.name}")
    session.commit()


@router.get("/teams/{external_id}/applications", response_model=list[TeamApplicationRead])
def list_team_applications(
    external_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> list[TeamApplicationRead]:
    """Read-only: the team's applications and who is working on each."""
    team = _viewable_team(session, user, external_id)
    applications = session.exec(
        select(Application)
        .where(Application.team_id == team.id, col(Application.deleted_at).is_(None))
        .order_by(col(Application.created_at).desc())
    ).all()
    by_application: dict[uuid.UUID, list[str]] = {a.id: [] for a in applications}
    for application_id, name in session.exec(
        select(ApplicationMember.application_id, PlatformUser.name)
        .join(PlatformUser, col(PlatformUser.id) == col(ApplicationMember.user_id))
        .where(col(ApplicationMember.application_id).in_(list(by_application)))
        .order_by(PlatformUser.name)
    ).all():
        by_application[application_id].append(name)
    return [
        TeamApplicationRead(
            id=a.external_id,
            name=a.name,
            url=a.url,
            added_by_name=a.created_by_name,
            people=by_application[a.id][:5],
            people_count=len(by_application[a.id]),
            my_role=application_role(session, user, a),
        )
        for a in applications
    ]
