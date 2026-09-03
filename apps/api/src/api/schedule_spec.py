"""Cadence -> temporalio ScheduleSpec normalization, plus the two
validators that must run before anything reaches Temporal (Schedules
feature).

Structured `ScheduleCalendarSpec` for daily/weekly/monthly (temporalio's
own docstring: "New uses should use `calendars` instead" of
cron_expressions), raw `cron_expressions` for the custom-cron cadence where
the user literally supplied a cron string. Every function here is pure —
no DB, no client, no `app` import — so cadence correctness is provable with
no Temporal server running at all (see test_schedule_spec.py).

Lives in apps/api rather than packages/workflows on purpose: `ScheduleSpec`
is a `temporalio.client` type, and packages/workflows is orchestration-only
(its modules import `temporalio.workflow`/`temporalio.common` and nothing
else, keeping the workflow sandbox's import graph clean). Only the API ever
builds a spec; no worker does.
"""

import re
from datetime import timedelta
from zoneinfo import available_timezones

from domain import Schedule
from temporalio.client import (
    ScheduleCalendarSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleRange,
    ScheduleSpec,
)

CADENCE_TYPES = ("daily", "weekly", "monthly", "custom_cron")

# 0 = Sunday .. 6 = Saturday — ScheduleCalendarSpec.day_of_week's own
# numbering, which `Schedule.days_of_week` stores verbatim.
DAY_OF_WEEK_LABELS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")

# 1-28 only. Every Gregorian month has at least 28 days (February,
# including non-leap years, has exactly 28) — so this range guarantees the
# chosen day exists in every month of every year, with zero exceptions,
# ever. 29/30/31 would silently skip short months (a "31st" monthly
# regression would run 7 times a year, not 12) — a footgun with no good UI
# answer in v1. Custom Cron is the documented escape hatch.
MAX_DAY_OF_MONTH = 28


class ScheduleSpecError(ValueError):
    """Invalid cadence input — mapped to HTTP 422 by the API layer."""


def validate_time_zone(time_zone: str) -> None:
    # zoneinfo is stdlib; `available_timezones()` is the authoritative set
    # the server itself would accept, so no curated list to drift.
    if time_zone not in available_timezones():
        raise ScheduleSpecError(f"unknown IANA time zone: {time_zone!r}")


_CRON_FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_CRON_TERM = re.compile(r"^(\*|\d+|\d+-\d+)(/\d+)?$")


def validate_cron_expression(expression: str) -> None:
    """Accepts classic 5-field cron only (minute hour dom month dow).

    Deliberately narrower than what Temporal accepts: no `@daily`-style
    nicknames, no 6/7-field forms with seconds or a year, no `@every`.
    Those either can't be rendered back into the UI's cadence picker or
    duplicate a cadence type that already exists here, and validating a
    narrow grammar server-side beats forwarding an unvalidated string and
    discovering the problem at 2am.
    """
    fields = expression.split()
    if len(fields) != 5:
        raise ScheduleSpecError(
            "cron expression must have exactly 5 fields: minute hour day-of-month month day-of-week"
        )
    for field, (low, high) in zip(fields, _CRON_FIELD_RANGES, strict=True):
        for term in field.split(","):
            match = _CRON_TERM.match(term)
            if match is None:
                raise ScheduleSpecError(f"unsupported cron term: {term!r}")
            if match.group(2) and int(match.group(2)[1:]) < 1:
                raise ScheduleSpecError(f"cron step must be >= 1: {term!r}")
            base = match.group(1)
            if base == "*":
                continue
            bounds = [int(part) for part in base.split("-")]
            if any(value < low or value > high for value in bounds):
                raise ScheduleSpecError(f"cron value out of range {low}-{high}: {term!r}")
            if len(bounds) == 2 and bounds[0] > bounds[1]:
                raise ScheduleSpecError(f"cron range is inverted: {term!r}")


def validate_cadence(
    *,
    cadence_type: str,
    hour: int | None,
    minute: int | None,
    days_of_week: list[int],
    day_of_month: int | None,
    cron_expression: str | None,
    time_zone: str,
) -> None:
    """Every cross-field rule, in one place, so create and update share
    exactly one definition of "valid" (a PATCH validates the *merged* row,
    never just the supplied fields)."""
    if cadence_type not in CADENCE_TYPES:
        raise ScheduleSpecError(f"unknown cadence type: {cadence_type!r}")
    validate_time_zone(time_zone)

    if cadence_type == "custom_cron":
        if not cron_expression:
            raise ScheduleSpecError("cron_expression is required for the custom_cron cadence")
        validate_cron_expression(cron_expression)
        return

    if hour is None or minute is None:
        raise ScheduleSpecError(f"hour and minute are required for the {cadence_type} cadence")
    if not 0 <= hour <= 23:
        raise ScheduleSpecError("hour must be 0-23")
    if not 0 <= minute <= 59:
        raise ScheduleSpecError("minute must be 0-59")

    if cadence_type == "weekly":
        if not days_of_week:
            raise ScheduleSpecError("at least one day of the week is required")
        if any(day < 0 or day > 6 for day in days_of_week):
            raise ScheduleSpecError("days of the week must be 0 (Sunday) - 6 (Saturday)")
        if len(set(days_of_week)) != len(days_of_week):
            raise ScheduleSpecError("duplicate day of the week")
    if cadence_type == "monthly":
        if day_of_month is None:
            raise ScheduleSpecError("day_of_month is required for the monthly cadence")
        if not 1 <= day_of_month <= MAX_DAY_OF_MONTH:
            raise ScheduleSpecError(
                f"day_of_month must be 1-{MAX_DAY_OF_MONTH} "
                "(29-31 would skip short months; use a custom cron expression instead)"
            )


def build_schedule_spec(schedule: Schedule) -> ScheduleSpec:
    """Row -> ScheduleSpec. Assumes `validate_cadence` already passed."""
    if schedule.cadence_type == "custom_cron":
        assert schedule.cron_expression is not None
        return ScheduleSpec(
            cron_expressions=[schedule.cron_expression],
            time_zone_name=schedule.time_zone,
        )

    assert schedule.hour is not None and schedule.minute is not None
    # ScheduleCalendarSpec's own defaults are: second=(0,), minute=(0,),
    # hour=(0,), day_of_month=(1-31,), month=(1-12,), day_of_week=(0-6,).
    # Every field is set explicitly below anyway — an omitted field would
    # silently inherit a default that is "match everything" for some fields
    # and "match zero" for others, which is exactly the kind of asymmetry a
    # partially-specified spec gets wrong.
    second = (ScheduleRange(0),)
    minute = (ScheduleRange(schedule.minute),)
    hour = (ScheduleRange(schedule.hour),)
    every_day_of_month = (ScheduleRange(1, 31),)
    every_month = (ScheduleRange(1, 12),)
    every_day_of_week = (ScheduleRange(0, 6),)

    if schedule.cadence_type == "daily":
        calendar = ScheduleCalendarSpec(
            second=second,
            minute=minute,
            hour=hour,
            day_of_month=every_day_of_month,
            month=every_month,
            day_of_week=every_day_of_week,
        )
    elif schedule.cadence_type == "weekly":
        calendar = ScheduleCalendarSpec(
            second=second,
            minute=minute,
            hour=hour,
            day_of_month=every_day_of_month,
            month=every_month,
            # One single-value ScheduleRange per selected day, not one wide
            # range — "Mon and Thu" is not a contiguous span, and
            # ScheduleRange(1, 4) would wrongly also match Tue/Wed.
            day_of_week=tuple(ScheduleRange(day) for day in sorted(schedule.days_of_week)),
        )
    elif schedule.cadence_type == "monthly":
        assert schedule.day_of_month is not None
        calendar = ScheduleCalendarSpec(
            second=second,
            minute=minute,
            hour=hour,
            day_of_month=(ScheduleRange(schedule.day_of_month),),
            month=every_month,
            day_of_week=every_day_of_week,
        )
    else:  # pragma: no cover - validate_cadence rejects anything else
        raise ScheduleSpecError(f"unknown cadence type: {schedule.cadence_type!r}")

    return ScheduleSpec(calendars=[calendar], time_zone_name=schedule.time_zone)


def build_schedule_policy() -> SchedulePolicy:
    """One policy for every schedule this feature creates.

    `overlap=SKIP` is the whole of schedule-vs-itself overlap handling: the
    scheduled action is `ScheduledExecutionWorkflow`, which *awaits* its
    execution child, so the parent stays open for the full duration of the
    run — SKIP therefore covers the entire execution, not just a gate
    check. Note this interacts with an execution-worker outage: a workflow
    whose first task was never picked up by a worker is still `RUNNING`
    from the schedule's own point of view, so SKIP treats every subsequent
    occurrence that would fire during the outage as overlapping with that
    stuck-open one and drops it — not queued, not backfired. Only the first
    occurrence that fired at outage-start ever actually runs, once a worker
    finally polls it. See ScheduledExecutionWorkflow's own docstring.

    `catchup_window` is cut from temporalio's 365-day default to 1 hour.
    That default means a multi-day *Temporal server* outage would, on
    recovery, replay every missed occurrence at once (a year's worth of
    nightly regressions). A nightly regression more than an hour late has
    no value. This is a *different* outage than the worker-down case above
    — catchup_window governs whether Temporal's own scheduler could
    *create* an occurrence at all; it has no bearing on what happens to an
    occurrence that was created on time but is waiting for a worker.

    `pause_on_failure=False` explicitly: a run whose tests fail (or whose
    execution workflow errors) must never silently disable the user's
    schedule. Failure visibility is the Runs tab, not the schedule's own
    enabled state.
    """
    return SchedulePolicy(
        overlap=ScheduleOverlapPolicy.SKIP,
        catchup_window=timedelta(hours=1),
        pause_on_failure=False,
    )


def build_cadence_label(schedule: Schedule) -> str:
    """The single human rendering of a cadence, server-side — same
    convention as `TestRunRead.trigger` being one pre-formatted string
    (see `_to_test_run_read`): one formatter, not one per client."""
    if schedule.cadence_type == "custom_cron":
        return f"Cron `{schedule.cron_expression}` ({schedule.time_zone})"
    assert schedule.hour is not None and schedule.minute is not None
    at = f"{schedule.hour:02d}:{schedule.minute:02d}"
    if schedule.cadence_type == "daily":
        return f"Every day at {at} ({schedule.time_zone})"
    if schedule.cadence_type == "weekly":
        days = ", ".join(DAY_OF_WEEK_LABELS[d] for d in sorted(schedule.days_of_week))
        return f"Every {days} at {at} ({schedule.time_zone})"
    return f"Day {schedule.day_of_month} of every month at {at} ({schedule.time_zone})"
