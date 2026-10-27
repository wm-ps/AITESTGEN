"""The run's Goal as a strict scope (docs/superpowers/specs/2026-10-27-explorer-goal-scope-design.md).

The App Summary's "Goal for this run" text is read once, after the summary
is confirmed: one model call turns it into a strict rule and places every
known screen against it (explorer_core.GOAL_FITS). Screens found later are
placed while they are read (brain.perceive). An empty goal changes nothing:
no scope, every screen counts as inside."""

import uuid
from typing import Any

from explorer_core import GOAL_FITS

from explorer_worker import brain
from explorer_worker.journal import Journal


async def ensure_scope(run_id: uuid.UUID) -> dict[str, Any] | None:
    """The run's scope ({"rule", "fits"}), made on first use and kept on the
    run's brief — so a run confirmed before this existed gets one too."""
    journal = Journal(run_id)
    brief = journal.run_brief()
    text = str(brief.get("focus") or "").strip()
    if not text:
        return None
    if isinstance(brief.get("scope"), dict):
        return brief["scope"]
    screens = [
        {"name": s.name, "business_thing": s.entity, "kind": s.view_kind, "purpose": s.purpose}
        for s in journal.screen_rows()
    ]
    read = await brain.read_goal(text, screens)
    fits = {str(k): str(v) for k, v in read["fits"].items() if v in GOAL_FITS}
    scope = {"rule": read["rule"], "fits": fits}
    journal.update_run(brief={**brief, "scope": scope})
    journal.set_goal_fit(fits)
    journal.event("thought", "Following your goal", scope["rule"])
    return scope


def in_goal(fit: str | None) -> bool:
    """Plan and test here? Unjudged screens (no goal) count as inside."""
    return fit is None or fit == "inside"


def stops_walk(fit: str | None) -> bool:
    """Reaching this screen ends a walk: it is past the stop point or outside."""
    return fit in ("past_stop", "outside")


def screens_in_goal(screens: list[Any]) -> list[Any]:
    return [s for s in screens if in_goal(getattr(s, "goal_fit", None))]


def follow_ups_in_goal(missions: list[dict[str, Any]], fits: dict[str, str | None]) -> list[dict[str, Any]]:
    """Follow-up missions that start on a screen inside the goal (or on none)."""
    return [m for m in missions if not m.get("start_screen") or in_goal(fits.get(m["start_screen"]))]
