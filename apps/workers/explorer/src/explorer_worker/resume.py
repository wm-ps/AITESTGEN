"""Resume: carry on a paused, stopped or failed run from where it left off.

Everything Explorer learned is already saved row by row (screens, the App
Summary, each mission, each scenario), so the stage a run reached can be
read back from them. Work that was cut off mid-way (a mission or scenario
whose browser was closed) goes back in the queue and is done again from its
start; everything finished stays as it is.
"""

import uuid

from explorer_core import ExplorerMission, ExplorerRun, ExplorerTestCase
from sqlmodel import Session, select

from explorer_worker.db import engine
from explorer_worker.journal import Journal

# The stages a run goes through, in order (see workflow.STEPS).
_WHERE = {
    "understand": ("queued", "Getting ready", "looking around the app"),
    "confirm": (
        "awaiting_confirmation",
        "Please review the App Summary",
        "your App Summary review",
    ),
    "plan_missions": ("planning", "Planning missions", "planning missions"),
    "missions": ("exploring", "Exploring", "the missions still to do"),
    "hunt": ("hunting", "Hunting for hidden screens", "the hunt for hidden screens"),
    "build_tests": ("testing", "Trying scenarios", "the scenarios still to try"),
}
# What a mission cut off by a pause or stop says (missions.run_mission).
_CUT_OFF = "Stopped before finishing"


def resume_point(run_id: uuid.UUID) -> str:
    """Puts cut-off work back in the queue and returns the step to start
    from (one of workflow.STEPS)."""
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None:
            raise ValueError(f"explorer run {run_id} not found")
        missions = session.exec(
            select(ExplorerMission).where(ExplorerMission.run_id == run_id)
        ).all()
        tests = session.exec(
            select(ExplorerTestCase).where(ExplorerTestCase.run_id == run_id)
        ).all()
        for mission in missions:
            if mission.status in ("running", "waiting") or (
                mission.status == "skipped" and mission.outcome == _CUT_OFF
            ):
                mission.status, mission.started_at, mission.outcome = "queued", None, None
                session.add(mission)
        for test in tests:
            if test.status == "building":
                test.status = "planned"
                session.add(test)
        session.commit()

        if not run.brief:
            point = "understand"
        elif run.brief_confirmed_at is None:
            point = "confirm"
        elif not missions:
            point = "plan_missions"
        elif any(m.status == "queued" for m in missions):
            point = "missions"
        elif tests:
            point = "build_tests"
        else:
            point = "hunt"

    status, headline, what = _WHERE[point]
    journal = Journal(run_id)
    journal.update_run(status=status, headline=headline, error=None)
    journal.event("phase", "Resumed", f"Picking up from {what}. Finished work is kept.")
    return point
