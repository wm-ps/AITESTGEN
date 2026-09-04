"""Cadence -> ScheduleSpec normalization and validation (Schedules
feature). Pure functions, no DB/Temporal/Vault dependency — every test here
runs with nothing but the interpreter.
"""

import uuid
from datetime import timedelta

import pytest
from api.schedule_spec import (
    MAX_DAY_OF_MONTH,
    ScheduleSpecError,
    build_cadence_label,
    build_schedule_policy,
    build_schedule_spec,
    validate_cadence,
    validate_cron_expression,
    validate_time_zone,
)
from domain import Schedule
from temporalio.client import ScheduleOverlapPolicy, ScheduleRange


def _schedule(**overrides) -> Schedule:
    defaults = dict(
        application_id=uuid.uuid4(),
        name="Nightly Regression",
        cadence_type="daily",
        hour=2,
        minute=30,
        days_of_week=[],
        day_of_month=None,
        cron_expression=None,
        time_zone="Asia/Kolkata",
        temporal_schedule_id="app-schedule-test",
    )
    defaults.update(overrides)
    return Schedule(**defaults)


class TestBuildScheduleSpecDaily:
    def test_daily_produces_full_day_calendar(self) -> None:
        spec = build_schedule_spec(_schedule(cadence_type="daily", hour=2, minute=30))

        assert spec.cron_expressions == []
        assert spec.time_zone_name == "Asia/Kolkata"
        [calendar] = spec.calendars
        assert calendar.second == (ScheduleRange(0),)
        assert calendar.minute == (ScheduleRange(30),)
        assert calendar.hour == (ScheduleRange(2),)
        assert calendar.day_of_month == (ScheduleRange(1, 31),)
        assert calendar.month == (ScheduleRange(1, 12),)
        assert calendar.day_of_week == (ScheduleRange(0, 6),)


class TestBuildScheduleSpecWeekly:
    def test_non_contiguous_days_produce_one_range_each(self) -> None:
        """The single highest-value assertion in this module: Mon+Thu must
        become two single-value ScheduleRanges, never one wide range —
        ScheduleRange(1, 4) would wrongly also match Tue/Wed."""
        spec = build_schedule_spec(_schedule(cadence_type="weekly", days_of_week=[1, 4]))

        [calendar] = spec.calendars
        assert calendar.day_of_week == (ScheduleRange(1), ScheduleRange(4))

    def test_unsorted_input_is_sorted(self) -> None:
        spec = build_schedule_spec(_schedule(cadence_type="weekly", days_of_week=[4, 1]))

        [calendar] = spec.calendars
        assert calendar.day_of_week == (ScheduleRange(1), ScheduleRange(4))


class TestBuildScheduleSpecMonthly:
    def test_single_day_of_month(self) -> None:
        spec = build_schedule_spec(_schedule(cadence_type="monthly", day_of_month=15))

        [calendar] = spec.calendars
        assert calendar.day_of_month == (ScheduleRange(15),)
        assert calendar.day_of_week == (ScheduleRange(0, 6),)

    @pytest.mark.parametrize("day", range(1, MAX_DAY_OF_MONTH + 1))
    def test_every_day_1_to_28_is_representable(self, day: int) -> None:
        """Every Gregorian month has at least 28 days, so this range must
        never raise and must always produce exactly that day."""
        spec = build_schedule_spec(_schedule(cadence_type="monthly", day_of_month=day))

        [calendar] = spec.calendars
        assert calendar.day_of_month == (ScheduleRange(day),)


class TestBuildScheduleSpecCustomCron:
    def test_cron_expression_passed_through(self) -> None:
        spec = build_schedule_spec(
            _schedule(cadence_type="custom_cron", cron_expression="0 2 * * 1-5", hour=None, minute=None)
        )

        assert spec.cron_expressions == ["0 2 * * 1-5"]
        assert spec.calendars == []
        assert spec.time_zone_name == "Asia/Kolkata"


class TestTimeZonePreservation:
    def test_iana_zone_name_is_not_collapsed_to_an_offset(self) -> None:
        """DST correctness obligation: the IANA name survives unmodified —
        Temporal's server does the actual DST math at fire time, not us."""
        spec = build_schedule_spec(_schedule(cadence_type="daily", time_zone="America/New_York"))

        assert spec.time_zone_name == "America/New_York"


class TestBuildSchedulePolicy:
    def test_policy_values(self) -> None:
        policy = build_schedule_policy()

        assert policy.overlap is ScheduleOverlapPolicy.SKIP
        assert policy.catchup_window == timedelta(hours=1)
        assert policy.pause_on_failure is False


class TestValidateCronExpression:
    @pytest.mark.parametrize(
        "expression",
        [
            "0 2 * * *",
            "*/15 * * * *",
            "0 2 * * 1-5",
            "0 0,12 * * *",
            "30 3 1 * *",
            "0 0 * * 7",
        ],
    )
    def test_accepts_valid_expressions(self, expression: str) -> None:
        validate_cron_expression(expression)  # must not raise

    @pytest.mark.parametrize(
        "expression",
        [
            "0 2 * *",  # 4 fields
            "0 2 * * * *",  # 6 fields
            "@daily",
            "60 * * * *",  # minute out of range
            "0 24 * * *",  # hour out of range
            "0 2 32 * *",  # day-of-month out of range
            "0 2 * 13 *",  # month out of range
            "0 2 * * 8",  # day-of-week out of range
            "0 5-2 * * *",  # inverted range
            "*/0 * * * *",  # step must be >= 1
            "0 2 * * MON",  # names unsupported
        ],
    )
    def test_rejects_invalid_expressions(self, expression: str) -> None:
        with pytest.raises(ScheduleSpecError):
            validate_cron_expression(expression)


class TestValidateTimeZone:
    def test_accepts_known_iana_zone(self) -> None:
        validate_time_zone("Asia/Kolkata")  # must not raise

    def test_rejects_unknown_zone(self) -> None:
        with pytest.raises(ScheduleSpecError):
            validate_time_zone("Mars/Olympus")


class TestValidateCadence:
    def test_daily_requires_hour_and_minute(self) -> None:
        with pytest.raises(ScheduleSpecError):
            validate_cadence(
                cadence_type="daily", hour=None, minute=30, days_of_week=[],
                day_of_month=None, cron_expression=None, time_zone="UTC",
            )

    def test_weekly_requires_at_least_one_day(self) -> None:
        with pytest.raises(ScheduleSpecError):
            validate_cadence(
                cadence_type="weekly", hour=2, minute=0, days_of_week=[],
                day_of_month=None, cron_expression=None, time_zone="UTC",
            )

    def test_weekly_rejects_out_of_range_day(self) -> None:
        with pytest.raises(ScheduleSpecError):
            validate_cadence(
                cadence_type="weekly", hour=2, minute=0, days_of_week=[7],
                day_of_month=None, cron_expression=None, time_zone="UTC",
            )

    def test_weekly_rejects_duplicate_days(self) -> None:
        with pytest.raises(ScheduleSpecError):
            validate_cadence(
                cadence_type="weekly", hour=2, minute=0, days_of_week=[1, 1],
                day_of_month=None, cron_expression=None, time_zone="UTC",
            )

    def test_monthly_requires_day_of_month(self) -> None:
        with pytest.raises(ScheduleSpecError):
            validate_cadence(
                cadence_type="monthly", hour=2, minute=0, days_of_week=[],
                day_of_month=None, cron_expression=None, time_zone="UTC",
            )

    def test_monthly_rejects_day_31(self) -> None:
        with pytest.raises(ScheduleSpecError):
            validate_cadence(
                cadence_type="monthly", hour=2, minute=0, days_of_week=[],
                day_of_month=31, cron_expression=None, time_zone="UTC",
            )

    def test_custom_cron_requires_an_expression(self) -> None:
        with pytest.raises(ScheduleSpecError):
            validate_cadence(
                cadence_type="custom_cron", hour=None, minute=None, days_of_week=[],
                day_of_month=None, cron_expression=None, time_zone="UTC",
            )

    def test_rejects_unknown_cadence_type(self) -> None:
        with pytest.raises(ScheduleSpecError):
            validate_cadence(
                cadence_type="hourly", hour=2, minute=0, days_of_week=[],
                day_of_month=None, cron_expression=None, time_zone="UTC",
            )

    def test_rejects_unknown_time_zone(self) -> None:
        with pytest.raises(ScheduleSpecError):
            validate_cadence(
                cadence_type="daily", hour=2, minute=0, days_of_week=[],
                day_of_month=None, cron_expression=None, time_zone="Mars/Olympus",
            )

    def test_valid_daily_does_not_raise(self) -> None:
        validate_cadence(
            cadence_type="daily", hour=2, minute=0, days_of_week=[],
            day_of_month=None, cron_expression=None, time_zone="UTC",
        )


class TestBuildCadenceLabel:
    def test_daily(self) -> None:
        label = build_cadence_label(_schedule(cadence_type="daily", hour=2, minute=30))
        assert label == "Every day at 02:30"

    def test_weekly(self) -> None:
        label = build_cadence_label(
            _schedule(cadence_type="weekly", hour=2, minute=30, days_of_week=[4, 1])
        )
        assert label == "Every Mon, Thu at 02:30"

    def test_monthly(self) -> None:
        label = build_cadence_label(
            _schedule(cadence_type="monthly", hour=2, minute=30, day_of_month=15)
        )
        assert label == "Day 15 of every month at 02:30"

    def test_custom_cron(self) -> None:
        label = build_cadence_label(
            _schedule(cadence_type="custom_cron", cron_expression="0 2 * * 1-5", hour=None, minute=None)
        )
        assert label == "Cron `0 2 * * 1-5`"
