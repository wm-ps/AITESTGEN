"""Schedule — a user-created recurring trigger for "Run All Tests"
(Schedules feature).

Targets an Application, not a TestSuite: `TestSuite` is scoped per Journey x
generation_run, so there is no single canonical "the test suite" for an
Application, and `_prepare_test_run_sync` already executes every current
TestAsset for the Application unconditionally. One row per user-authored
cadence ("Nightly Regression", "Weekly Regression").

This row is the source of truth for the *authored* cadence (name, cadence
type, local wall-clock time, days, IANA zone). The live Temporal Schedule
(`temporal_schedule_id`) is the source of truth for whether occurrences
actually fire — `enabled` here is a cached projection of Temporal's own
`ScheduleState.paused`, written only after a successful Temporal call, and
reconciled from Temporal on every list read (see the Schedules API in
apps/api/src/api/main.py).

Soft-deleted (`deleted_at`), same convention as `Application` — a
`TestRun.schedule_id` FK points here, and hard-deleting would either orphan
that FK or need an `ondelete` behavior no FK in this schema uses. The
*Temporal* Schedule is hard-deleted at the same moment — it's the live
object, there is nothing historical about it.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

ScheduleCadenceType = Literal["daily", "weekly", "monthly", "custom_cron"]


class Schedule(SQLModel, table=True):
    __tablename__ = "schedule"  # pyright: ignore[reportAssignmentType]
    # No table-level UniqueConstraint on (application_id, name): uniqueness
    # has to exclude soft-deleted rows so a name can be reused after
    # deletion — that needs a partial index, created in the migration
    # (`uq_schedule_application_id_name`, `postgresql_where=deleted_at IS NULL`).

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")),
    )
    external_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), unique=True, nullable=False, index=True),
    )
    application_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("application.id"), nullable=False, index=True
        ),
    )
    name: str = Field(sa_column=Column(String, nullable=False))
    cadence_type: str = Field(sa_column=Column(String, nullable=False))

    # Local wall-clock time in `time_zone`, for daily/weekly/monthly. NULL
    # only for custom_cron, where the cron expression carries the time.
    hour: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    minute: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))

    # weekly only. Temporal's own day numbering (0 = Sunday .. 6 = Saturday,
    # ScheduleCalendarSpec.day_of_week) — stored in Temporal's numbering, not
    # ISO's, so the spec builder is a straight pass-through with no
    # off-by-one conversion layer to get wrong. Empty list for other cadences.
    days_of_week: list[int] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    # monthly only, 1-28 — every Gregorian month has at least 28 days, so
    # this range guarantees the chosen day exists every month, every year.
    # 29-31 would silently skip short months; Custom Cron is the escape hatch.
    day_of_month: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    # custom_cron only — the user's raw 5-field expression, already
    # validated by `schedule_spec.validate_cron_expression` before this row
    # is ever written.
    cron_expression: str | None = Field(default=None, sa_column=Column(String, nullable=True))

    # Explicit IANA name, never a raw UTC offset — same reasoning as
    # create_cleanup_schedule.py's `time_zone_name="Asia/Kolkata"`: an
    # offset silently breaks across DST, a zone name does not.
    time_zone: str = Field(sa_column=Column(String, nullable=False))

    enabled: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    # Deterministic, derived once at create time from `external_id`
    # (f"app-schedule-{external_id}") and never rewritten — so the handle
    # is reconstructible from this row alone with no extra lookup.
    temporal_schedule_id: str = Field(
        sa_column=Column(String, nullable=False, unique=True, index=True)
    )
    created_by_name: str | None = Field(default=None, sa_column=Column(String, nullable=True))

    deleted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
