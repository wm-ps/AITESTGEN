"""The limits a run works within (Settings → Explorer limits), and the AI
budget / run time check that pauses a run when one is reached.

A run carries its own copy (ExplorerRun.limits, taken at start and on
Resume). A run from before limits existed has none: it keeps the values
Explorer always used (the built-ins below)."""

import os
import uuid
from datetime import UTC, datetime
from typing import Any

from domain import DiscoveryRun
from explorer_core import ExplorerEvent, ExplorerRun, explorer_workflow_id
from sqlmodel import Session, col, select
from temporalio import activity

from explorer_worker.db import engine

BUILT_IN: dict[str, Any] = {
    "question_wait_minutes": int(os.environ.get("EXPLORER_WAIT_MINUTES", "10")),
    "mission_time_limit_minutes": 45,
    "run_time_limit_minutes": None,
    "first_look_time_limit_minutes": float(os.environ.get("EXPLORER_FIRST_LOOK_MINUTES", "120")),
    "hidden_screen_search_minutes": 25,
    "ai_budget_usd": None,
    "first_look_max_screens": int(os.environ.get("EXPLORER_FIRST_LOOK_SCREENS", "150")),
    "max_missions": 15,
    "steps_per_mission": int(os.environ.get("EXPLORER_MISSION_STEPS", "20")),
    "steps_per_scenario": 20,
    "steps_per_journey": 40,  # FNOL's full claim is ~27 actions
    "max_scenarios": 150,
    "proof_replays": int(os.environ.get("EXPLORER_PROOF_RUNS", "1")),
    # A walk (mission or scenario) gives up after landing on the same screen
    # this many times in a row, visiting one screen more than this often, or
    # a button doing nothing this many retries over.
    "same_screen_repeats": 3,
    "screen_visits": 4,
    "press_retries": 2,
}


def of(run_id: uuid.UUID) -> dict[str, Any]:
    """This run's limits: its own copy over the built-in values."""
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        own = dict(run.limits or {}) if run is not None else {}
    return {**BUILT_IN, **{k: v for k, v in own.items() if k in BUILT_IN}}


def over_limit(run: ExplorerRun, now: datetime) -> str | None:
    """Which limit the run has reached ("ai_budget" | "run_time"), if any.
    Run time counts from Confirm (the App Summary wait isn't Explorer's time).
    After "Write scenarios from what's explored" neither applies."""
    limits = run.limits or {}
    if limits.get("wrap_up"):
        return None
    budget = limits.get("ai_budget_usd")
    if budget is not None and run.ai_spent_usd >= float(budget):
        return "ai_budget"
    minutes = limits.get("run_time_limit_minutes")
    started = run.brief_confirmed_at
    if minutes is not None and started is not None:
        if (now - started).total_seconds() >= float(minutes) * 60:
            return "run_time"
    return None


def reached_message(reason: str, limits: dict[str, Any], spent: float) -> str:
    if reason == "ai_budget":
        return f"Reached the AI budget: ${spent:.2f} of ${float(limits['ai_budget_usd']):.2f}"
    return f"Reached the run time limit of {_duration(limits['run_time_limit_minutes'])}"


def _duration(minutes: Any) -> str:
    m = int(minutes)
    return f"{m // 60} h {m % 60} min".replace(" 0 min", "") if m >= 60 else f"{m} min"


async def may_continue(run_id: uuid.UUID) -> bool:
    """Called between missions and between scenarios. Past a limit, the run
    pauses exactly like the Pause button (nothing done is lost) and tells
    the person their two choices; returns False."""
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None or run.status in ("stopped", "paused"):
            return False
        reason = over_limit(run, datetime.now(UTC))
        if reason is None:
            return True
        message = reached_message(reason, run.limits or {}, run.ai_spent_usd)
        run.limits = {**(run.limits or {}), "reached": reason}
        run.status, run.headline, run.updated_at = "paused", message, datetime.now(UTC)
        session.add(run)
        if not run.prompt:  # the app's discovery record shows it, as on Pause
            record = session.exec(
                select(DiscoveryRun)
                .where(
                    DiscoveryRun.application_id == run.application_id,
                    DiscoveryRun.source == "crawler",
                )
                .order_by(col(DiscoveryRun.created_at).desc())
            ).first()
            if record is not None:
                record.status = "paused"
                session.add(record)
        session.add(
            ExplorerEvent(
                run_id=run.id,
                kind="phase",
                title=message,
                detail="Paused — nothing done is lost. Write scenarios from what's explored "
                "so far, or raise the limit in Settings and resume exploring.",
            )
        )
        session.commit()
        workflow_id = explorer_workflow_id(run.external_id)
    try:
        await activity.client().get_workflow_handle(workflow_id).cancel()
    except Exception:  # noqa: BLE001 — "paused" above already stops every next step
        pass
    return False
