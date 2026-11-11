"""Explorer's limits (ExplorerSettings) as a plain dict copied onto a run, so
the worker reads one place and Settings changes never alter a running run."""

from typing import Any

from sqlmodel import Session

from explorer_core.models import ExplorerSettings

LIMIT_KEYS = (
    "question_wait_minutes",
    "mission_time_limit_minutes",
    "run_time_limit_minutes",
    "first_look_time_limit_minutes",
    "hidden_screen_search_minutes",
    "ai_budget_usd",
    "first_look_max_screens",
    "max_missions",
    "steps_per_mission",
    "steps_per_scenario",
    "steps_per_journey",
    "max_scenarios",
    "proof_replays",
    "same_screen_repeats",
    "screen_visits",
    "press_retries",
)


def current_settings(session: Session) -> ExplorerSettings:
    """The settings row (created with the defaults the first time)."""
    settings = session.get(ExplorerSettings, 1)
    if settings is None:
        settings = ExplorerSettings(id=1)
        session.add(settings)
        session.flush()
    return settings


def snapshot(session: Session, own: dict[str, Any] | None = None) -> dict[str, Any]:
    """The limits a run starting now uses: the organisation's, with the
    application's own (`Application.explorer_limits`, Application settings
    page) on top."""
    settings = current_settings(session)
    return {key: (own or {}).get(key, getattr(settings, key)) for key in LIMIT_KEYS}
