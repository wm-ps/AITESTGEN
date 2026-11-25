"""Organisation limits: the ceilings a super admin sets on resource settings.

Anyone who can edit a setting (a super admin on the organisation default, an
application admin on their application) may not save a value above a ceiling —
that is a 422 naming the setting and its maximum, never a silent cap. The
effective value is also held to the ceiling when read (`domain.capped`), so
lowering a limit applies to settings that were saved earlier without rewriting
them; a run already going keeps the values it started with.
"""

import uuid
from typing import Any

from domain import (
    LIMITABLE_KEYS,
    RETENTION_ORDER,
    Application,
    DiscoverySettings,
    OrganizationLimits,
    exceeded,
    limits_for,
    retention_too_short,
    settings_for_application,
)
from explorer_core.limits import LIMIT_KEYS, current_settings
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from sqlmodel import Session, col, select

from api.activity import record_activity
from api.auth import CurrentAdminDep, SessionDep

router = APIRouter()


class AboveRead(BaseModel):
    """A saved setting that is above a ceiling (it is held to it when used)."""

    scope: str
    setting: str
    value: float | None
    limit: float


class LimitsBody(BaseModel):
    maximums: dict[str, float] = {}
    min_delete_project_after: str | None = None

    @field_validator("maximums")
    @classmethod
    def _known_and_positive(cls, value: dict[str, float]) -> dict[str, float]:
        for key, maximum in value.items():
            if key not in LIMITABLE_KEYS:
                raise ValueError(f"{key} can't have a limit")
            if maximum <= 0:
                raise ValueError(f"The limit for {key} must be more than zero")
        return value

    @field_validator("min_delete_project_after")
    @classmethod
    def _known_period(cls, value: str | None) -> str | None:
        if value is not None and value not in RETENTION_ORDER:
            raise ValueError(f"retention must be one of {', '.join(RETENTION_ORDER)}")
        return value


class LimitsRead(LimitsBody):
    above: list[AboveRead] = []


def org_maximums(session: Session, organization_id: uuid.UUID) -> dict[str, Any]:
    limits = limits_for(session, organization_id)
    return dict(limits.maximums) if limits else {}


def explorer_overrides(session: Session, application: Application) -> dict[str, Any]:
    """The Explorer limits the application's workspace (team, or the person for a
    personal application) has set for itself."""
    workspace = settings_for_application(session, application)
    return dict(workspace.explorer) if workspace else {}


def enforce_changed(
    session: Session, organization_id: uuid.UUID, before: dict[str, Any], after: dict[str, Any]
) -> None:
    """422 when a setting that is being *changed* ends above its ceiling (or
    retention below its floor). Unchanged values are left alone, so an old
    value that a later, lower ceiling now exceeds never blocks saving something else."""
    limits = limits_for(session, organization_id)
    if limits is None:
        return
    changed = {key: value for key, value in after.items() if before.get(key) != value}
    for key, maximum in exceeded(changed, limits):
        raise HTTPException(
            status_code=422,
            detail=f"{key.replace('_', ' ').capitalize()} can't be more than {maximum:g} — "
            "the limit set for your organisation.",
        )
    if retention_too_short(changed.get("delete_project_after"), limits):
        raise HTTPException(
            status_code=422,
            detail=f"Retention can't be shorter than {limits.min_delete_project_after.replace('_', ' ')} — "  # type: ignore[union-attr]
            "the limit set for your organisation.",
        )


def _above(session: Session, organization_id: uuid.UUID, limits: OrganizationLimits | None) -> list[AboveRead]:
    if limits is None:
        return []
    found: list[AboveRead] = []
    discovery = session.exec(select(DiscoverySettings)).one()
    explorer = current_settings(session)
    org_values = {
        **{k: getattr(discovery, k) for k in LIMITABLE_KEYS if hasattr(discovery, k)},
        **{k: getattr(explorer, k) for k in LIMIT_KEYS},
    }
    for key, maximum in exceeded(org_values, limits):
        found.append(AboveRead(scope="Organisation default", setting=key, value=org_values[key], limit=maximum))
    for application in session.exec(
        # Team applications only: a personal application's name is private, even from super admins.
        select(Application).where(
            Application.organization_id == organization_id,
            col(Application.team_id).is_not(None),
            col(Application.deleted_at).is_(None),
        )
    ).all():
        own = {k: v for k, v in (application.generation_settings or {}).items() if k in LIMITABLE_KEYS}
        for key, maximum in exceeded(own, limits):
            found.append(AboveRead(scope=application.name, setting=key, value=own[key], limit=maximum))
    return found


def _read(session: Session, organization_id: uuid.UUID) -> LimitsRead:
    limits = limits_for(session, organization_id)
    return LimitsRead(
        maximums=dict(limits.maximums) if limits else {},
        min_delete_project_after=limits.min_delete_project_after if limits else None,
        above=_above(session, organization_id, limits),
    )


@router.get("/organization/limits", response_model=LimitsRead)
def get_organization_limits(session: SessionDep, admin: CurrentAdminDep) -> LimitsRead:
    return _read(session, admin.organization_id)


@router.put("/organization/limits", response_model=LimitsRead)
def set_organization_limits(payload: LimitsBody, session: SessionDep, admin: CurrentAdminDep) -> LimitsRead:
    """Replaces the organisation's limits. Settings saved earlier that are now
    above a ceiling are not rewritten; the response lists them (`above`) and
    they are held to the ceiling wherever they are used."""
    limits = limits_for(session, admin.organization_id)
    if limits is None:
        limits = OrganizationLimits(organization_id=admin.organization_id)
    limits.maximums = dict(payload.maximums)
    limits.min_delete_project_after = payload.min_delete_project_after
    session.add(limits)
    record_activity(session, admin, "settings", "Changed the organisation's resource limits")
    session.commit()
    return _read(session, admin.organization_id)
