"""OrganizationLimits — the ceilings a super admin sets on resource settings.

One row per organisation, absent or empty = no limits. `maximums` maps a setting
name (an Explorer limit or a discovery/generation limit) to the most any
workspace or application may use; `min_delete_project_after` is a *floor* on
retention, since a shorter retention deletes data sooner. A ceiling is enforced
twice: a settings save above it is refused (422), and the effective value is
capped when read — so lowering a limit takes effect on existing settings without
rewriting them, and a run already going keeps the values it started with.
"""

import uuid
from typing import Any

from sqlalchemy import Column, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, Session, SQLModel

# Shortest first.
RETENTION_ORDER = ("1_day", "1_week", "1_month")

# Settings a ceiling can be set on.
LIMITABLE_KEYS = (
    # Explorer
    "question_wait_minutes",
    "mission_time_limit_minutes",
    "run_time_limit_minutes",
    "first_look_time_limit_minutes",
    "hidden_screen_search_minutes",
    "ai_budget_usd",
    "first_look_max_screens",
    "max_screens",
    "max_missions",
    "steps_per_mission",
    "steps_per_scenario",
    "steps_per_journey",
    "max_scenarios",
    # Discovery and generation
    "max_pages",
    "max_discovery_duration_minutes",
    "navigation_timeout_seconds",
    "max_journeys",
    "max_scenarios_per_journey",
    "max_test_cases_per_application",
    "max_heal_attempts",
)


class OrganizationLimits(SQLModel, table=True):
    __tablename__ = "organization_limits"  # pyright: ignore[reportAssignmentType]

    organization_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), primary_key=True
        ),
    )
    maximums: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    min_delete_project_after: str | None = Field(default=None)


def limits_for(session: Session, organization_id: uuid.UUID) -> OrganizationLimits | None:
    return session.get(OrganizationLimits, organization_id)


def exceeded(values: dict[str, Any], limits: OrganizationLimits | None) -> list[tuple[str, float]]:
    """The settings in `values` that are above their ceiling, with the ceiling.
    An unlimited value (None) is above any ceiling."""
    if limits is None:
        return []
    found = []
    for key, maximum in (limits.maximums or {}).items():
        if key in values and (values[key] is None or values[key] > maximum):
            found.append((key, maximum))
    return found


def retention_too_short(retention: str | None, limits: OrganizationLimits | None) -> bool:
    if limits is None or limits.min_delete_project_after is None or retention is None:
        return False
    return RETENTION_ORDER.index(retention) < RETENTION_ORDER.index(limits.min_delete_project_after)


def capped(values: dict[str, Any], limits: OrganizationLimits | None) -> dict[str, Any]:
    """A copy of `values` with every setting held to its ceiling and retention
    to its floor."""
    out = dict(values)
    if limits is None:
        return out
    for key, maximum in (limits.maximums or {}).items():
        if key in out and (out[key] is None or out[key] > maximum):
            out[key] = maximum
    if "delete_project_after" in out and retention_too_short(out["delete_project_after"], limits):
        out["delete_project_after"] = limits.min_delete_project_after
    return out
