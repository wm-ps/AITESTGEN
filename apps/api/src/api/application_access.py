"""Manage access — who can see an application, and as what role.

Only the people who administer an application (its adder, the team admins of
its team, super admins on team applications, anyone granted `app_admin`) may
use these routes. The adder and the team admins always have full access and
show as locked rows: they can't be edited or removed here.

A team application can only be shared with members of its team; a personal one
with anyone in the organisation. Everyone unknown to the caller — no such
person, another organisation, not in the team — gets the same 404.
"""

import uuid
from typing import Annotated

from domain import (
    APP_ADMIN_ROLE,
    APP_ROLES,
    TEAM_ADMIN_ROLE,
    VIEWER_APP_ROLE,
    Application,
    ApplicationMember,
    PlatformUser,
    TeamMember,
)
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, model_validator
from sqlalchemy import or_
from sqlmodel import Session, col, select

from api.access import require_application
from api.activity import record_activity
from api.auth import SUPER_ADMIN_ROLE, CurrentOrgIdDep, CurrentUserDep, SessionDep

router = APIRouter()

CANDIDATE_LIMIT = 8


class AccessEntryRead(BaseModel):
    name: str
    email: str
    role: str
    # True for the adder, team admins and super admins: full access that can't be edited.
    locked: bool
    # Why a locked row is locked: "Added by" | "Team Admin" | "Super Admin".
    reason: str | None = None


class CandidateRead(BaseModel):
    name: str
    email: str


class AccessGrantPayload(BaseModel):
    email: str
    role: str = VIEWER_APP_ROLE

    @model_validator(mode="after")
    def _valid_role(self) -> AccessGrantPayload:
        if self.role not in APP_ROLES:
            raise ValueError(f"role must be one of {', '.join(APP_ROLES)}")
        return self


class AccessRolePayload(BaseModel):
    role: str

    @model_validator(mode="after")
    def _valid_role(self) -> AccessRolePayload:
        if self.role not in APP_ROLES:
            raise ValueError(f"role must be one of {', '.join(APP_ROLES)}")
        return self


def _managed_application(
    session: Session, organization_id: uuid.UUID, external_id: uuid.UUID
) -> Application:
    application = session.exec(
        select(Application).where(
            Application.external_id == external_id,
            Application.organization_id == organization_id,
            col(Application.deleted_at).is_(None),
        )
    ).first()
    return require_application(session, application, organization_id, "application not found", APP_ADMIN_ROLE)


def _team_admin_ids(session: Session, application: Application) -> set[uuid.UUID]:
    if application.team_id is None:
        return set()
    return set(
        session.exec(
            select(TeamMember.user_id).where(
                TeamMember.team_id == application.team_id, TeamMember.role == TEAM_ADMIN_ROLE
            )
        ).all()
    )


def _super_admin_ids(session: Session, application: Application) -> set[uuid.UUID]:
    """Super admins administer every team application; personal ones stay private."""
    if application.team_id is None:
        return set()
    return set(
        session.exec(
            select(PlatformUser.id).where(
                PlatformUser.organization_id == application.organization_id,
                PlatformUser.role == SUPER_ADMIN_ROLE,
            )
        ).all()
    )


def _full_access_ids(session: Session, application: Application) -> set[uuid.UUID]:
    """People who already hold admin on this application without a grant."""
    ids = _team_admin_ids(session, application) | _super_admin_ids(session, application)
    if application.created_by_id is not None:
        ids.add(application.created_by_id)
    return ids


def _target(session: Session, application: Application, email: str) -> PlatformUser:
    """The person to share with: in this organisation and, for a team
    application, in its team (a Super Admin is in every team, with no membership
    row, and is then refused as already having full access). Anything else is a
    plain 404."""
    stmt = select(PlatformUser).where(
        PlatformUser.email == email, PlatformUser.organization_id == application.organization_id
    )
    if application.team_id is not None:
        in_team = select(TeamMember.user_id).where(TeamMember.team_id == application.team_id)
        stmt = stmt.where(or_(PlatformUser.role == SUPER_ADMIN_ROLE, col(PlatformUser.id).in_(in_team)))
    person = session.exec(stmt).first()
    if person is None:
        raise HTTPException(status_code=404, detail="person not found")
    return person


def _grant(session: Session, application: Application, user_id: uuid.UUID) -> ApplicationMember | None:
    return session.exec(
        select(ApplicationMember).where(
            ApplicationMember.application_id == application.id, ApplicationMember.user_id == user_id
        )
    ).first()


@router.get("/applications/{external_id}/access", response_model=list[AccessEntryRead])
def list_access(
    external_id: uuid.UUID, session: SessionDep, organization_id: CurrentOrgIdDep, user: CurrentUserDep
) -> list[AccessEntryRead]:
    application = _managed_application(session, organization_id, external_id)
    team_admins = _team_admin_ids(session, application)
    super_admins = _super_admin_ids(session, application)
    rows = session.exec(
        select(ApplicationMember, PlatformUser)
        .join(PlatformUser, col(PlatformUser.id) == col(ApplicationMember.user_id))
        .where(ApplicationMember.application_id == application.id)
    ).all()
    locked: list[AccessEntryRead] = []
    shared: list[AccessEntryRead] = []
    seen: set[uuid.UUID] = set()
    for grant, person in rows:
        seen.add(person.id)
        if person.id == application.created_by_id:
            locked.append(AccessEntryRead(name=person.name, email=person.email, role=APP_ADMIN_ROLE, locked=True, reason="Added by"))
        elif person.id in team_admins:
            locked.append(AccessEntryRead(name=person.name, email=person.email, role=APP_ADMIN_ROLE, locked=True, reason="Team Admin"))
        elif person.id in super_admins:
            locked.append(AccessEntryRead(name=person.name, email=person.email, role=APP_ADMIN_ROLE, locked=True, reason="Super Admin"))
        else:
            shared.append(AccessEntryRead(name=person.name, email=person.email, role=grant.role, locked=False))
    # Team admins and super admins hold admin without a grant row.
    for person in session.exec(select(PlatformUser).where(col(PlatformUser.id).in_(team_admins - seen))).all():
        locked.append(AccessEntryRead(name=person.name, email=person.email, role=APP_ADMIN_ROLE, locked=True, reason="Team Admin"))
    for person in session.exec(
        select(PlatformUser).where(col(PlatformUser.id).in_(super_admins - team_admins - seen))
    ).all():
        locked.append(AccessEntryRead(name=person.name, email=person.email, role=APP_ADMIN_ROLE, locked=True, reason="Super Admin"))
    reason_order = {"Added by": 0, "Team Admin": 1, "Super Admin": 2}
    locked.sort(key=lambda e: (reason_order.get(e.reason or "", 3), e.name.lower()))
    shared.sort(key=lambda e: e.name.lower())
    return locked + shared


@router.get("/applications/{external_id}/access/candidates", response_model=list[CandidateRead])
def list_access_candidates(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
    user: CurrentUserDep,
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> list[CandidateRead]:
    """Type-ahead for the share box: people who could be given access and don't
    have it yet. Name and email only."""
    application = _managed_application(session, organization_id, external_id)
    have = _full_access_ids(session, application) | set(
        session.exec(select(ApplicationMember.user_id).where(ApplicationMember.application_id == application.id)).all()
    )
    pattern = f"%{q.strip()}%"
    stmt = select(PlatformUser).where(
        PlatformUser.organization_id == application.organization_id,
        or_(col(PlatformUser.name).ilike(pattern), col(PlatformUser.email).ilike(pattern)),
    )
    if application.team_id is not None:
        stmt = stmt.join(
            TeamMember, (TeamMember.user_id == PlatformUser.id) & (TeamMember.team_id == application.team_id)  # type: ignore[arg-type]
        )
    people = session.exec(stmt.order_by(PlatformUser.name)).all()
    return [CandidateRead(name=p.name, email=p.email) for p in people if p.id not in have][:CANDIDATE_LIMIT]


@router.post("/applications/{external_id}/access", response_model=AccessEntryRead, status_code=201)
def share_application(
    external_id: uuid.UUID,
    payload: AccessGrantPayload,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
    user: CurrentUserDep,
) -> AccessEntryRead:
    application = _managed_application(session, organization_id, external_id)
    person = _target(session, application, payload.email)
    if person.id in _full_access_ids(session, application):
        raise HTTPException(status_code=409, detail="This person already has full access to the application.")
    if _grant(session, application, person.id) is not None:
        raise HTTPException(status_code=409, detail="This person already has access. Change their role instead.")
    session.add(
        ApplicationMember(
            application_id=application.id, user_id=person.id, role=payload.role, granted_by_id=user.id
        )
    )
    record_activity(
        session, user, "settings", f"Gave {person.name} {payload.role} access to {application.name}", application=application
    )
    session.commit()
    return AccessEntryRead(name=person.name, email=person.email, role=payload.role, locked=False)


def _editable_grant(
    session: Session, application: Application, email: str
) -> tuple[PlatformUser, ApplicationMember]:
    person = session.exec(
        select(PlatformUser).where(
            PlatformUser.email == email, PlatformUser.organization_id == application.organization_id
        )
    ).first()
    grant = _grant(session, application, person.id) if person is not None else None
    if person is None or grant is None:
        raise HTTPException(status_code=404, detail="person not found")
    if person.id in _full_access_ids(session, application):
        raise HTTPException(status_code=409, detail="This person's full access can't be changed here.")
    return person, grant


@router.patch("/applications/{external_id}/access/{email}", response_model=AccessEntryRead)
def change_access_role(
    external_id: uuid.UUID,
    email: str,
    payload: AccessRolePayload,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
    user: CurrentUserDep,
) -> AccessEntryRead:
    application = _managed_application(session, organization_id, external_id)
    person, grant = _editable_grant(session, application, email)
    if grant.role != payload.role:
        record_activity(
            session,
            user,
            "settings",
            f"Changed {person.name}'s access to {application.name} from {grant.role} to {payload.role}",
            application=application,
        )
        grant.role = payload.role
        session.add(grant)
        session.commit()
    return AccessEntryRead(name=person.name, email=person.email, role=grant.role, locked=False)


@router.delete("/applications/{external_id}/access/{email}", status_code=204)
def remove_access(
    external_id: uuid.UUID,
    email: str,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
    user: CurrentUserDep,
) -> None:
    application = _managed_application(session, organization_id, external_id)
    person, grant = _editable_grant(session, application, email)
    record_activity(
        session, user, "settings", f"Removed {person.name}'s access to {application.name}", application=application
    )
    session.delete(grant)
    session.commit()
