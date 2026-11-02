"""Explorer limits (Settings → Explorer limits): the AI budget and run time
check that pauses a run, and the caps the stages take from the run."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from explorer_worker import limits
from explorer_worker.missions import mission_cap
from explorer_worker.tests_stage import test_cap as scenario_cap

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def _run(spent: float = 0.0, confirmed_minutes_ago: float | None = 10, **own: object) -> Any:
    confirmed = NOW - timedelta(minutes=confirmed_minutes_ago) if confirmed_minutes_ago else None
    return SimpleNamespace(limits=own, ai_spent_usd=spent, brief_confirmed_at=confirmed)


def test_no_limits_never_stop_a_run() -> None:
    assert limits.over_limit(_run(spent=999, confirmed_minutes_ago=9999), NOW) is None


def test_the_ai_budget_is_reached_at_the_amount() -> None:
    assert limits.over_limit(_run(spent=4.99, ai_budget_usd=5), NOW) is None
    assert limits.over_limit(_run(spent=5.0, ai_budget_usd=5), NOW) == "ai_budget"


def test_run_time_counts_from_confirm_not_from_the_summary_wait() -> None:
    assert limits.over_limit(_run(confirmed_minutes_ago=59, run_time_limit_minutes=60), NOW) is None
    assert (
        limits.over_limit(_run(confirmed_minutes_ago=60, run_time_limit_minutes=60), NOW)
        == "run_time"
    )
    # Not confirmed yet (still on the App Summary): no run time used.
    assert (
        limits.over_limit(_run(confirmed_minutes_ago=None, run_time_limit_minutes=1), NOW) is None
    )


def test_writing_scenarios_from_whats_explored_lifts_both_limits() -> None:
    run = _run(spent=50, ai_budget_usd=5, run_time_limit_minutes=1, wrap_up=True)
    assert limits.over_limit(run, NOW) is None


def test_the_pause_message_says_which_limit() -> None:
    assert limits.reached_message("ai_budget", {"ai_budget_usd": 5}, 5.123) == (
        "Reached the AI budget: $5.12 of $5.00"
    )
    assert limits.reached_message("run_time", {"run_time_limit_minutes": 90}, 0) == (
        "Reached the run time limit of 1 h 30 min"
    )
    assert limits.reached_message("run_time", {"run_time_limit_minutes": 120}, 0) == (
        "Reached the run time limit of 2 h"
    )


def test_caps_follow_the_settings_and_keep_their_built_in_shape() -> None:
    assert mission_cap(20) == 10 and mission_cap(20, 4) == 4  # never more than the setting
    assert mission_cap(100, 15) == 15
    assert scenario_cap(3) == 45 and scenario_cap(3, 20) == 20
    assert scenario_cap(1, 5) == 5  # a small setting is never raised to the minimum


def test_a_run_from_before_limits_keeps_the_built_in_values() -> None:
    assert limits.BUILT_IN["mission_time_limit_minutes"] == 45
    assert limits.BUILT_IN["max_missions"] == 15 and limits.BUILT_IN["max_scenarios"] == 150
