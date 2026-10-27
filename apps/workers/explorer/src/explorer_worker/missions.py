"""Stage 2 — missions (PLAN.md Step 3 + §5).

After the user confirms the App Summary, Explorer turns it into a Mission
Board, then works through the missions in parallel browsers. Each mission:
- is screen-recorded (captions come from its own feed events);
- pursues its goal with the shared understanding (Mind), so every screen it
  reaches lands on the App Map — screens first found under a branch
  mission's condition are hidden screens;
- is judged against what SHOULD happen (trusted sources, never the app), and
  a mismatch becomes a Possible bug.
"""

import os
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from explorer_core import ExplorerMission, ExplorerRecording, ExplorerRun, ExplorerScreen
from sqlmodel import Session, col, select

from explorer_worker import brain
from explorer_worker.browser import Eyes
from explorer_worker.db import engine
from explorer_worker.goal import ensure_scope, screens_in_goal
from explorer_worker.journal import Journal
from explorer_worker.memory import ask, remember_record
from explorer_worker.mind import Mind
from explorer_worker.pursue import Pursuit, forget_route, path_to, pursue
from explorer_worker.sense import keeps_state
from explorer_worker.session import load_target, open_signed_in
from explorer_worker.testkit import replay

MISSION_STEPS = int(os.environ.get("EXPLORER_MISSION_STEPS", "20"))
MAX_MISSIONS = 15
# A task mission can walk its flow more than once: the same path every time
# means a stable flow; screens seen on only some attempts are conditional.
# Once by default — each extra walk costs as much as the first, and the
# scenario stage replays flows several times anyway. ponytail: tasks only.
TASK_PASSES = int(os.environ.get("EXPLORER_TASK_PASSES", "1"))


def mission_cap(screen_count: int) -> int:
    """Missions worth running for an app this size: a 20-screen app needs
    about 10, not 15 (each one is a full walk through the app)."""
    return max(6, min(MAX_MISSIONS, screen_count // 3 + 4))


async def fast_forward(
    eyes: Eyes, journal: Journal, run_id: uuid.UUID, screen: str | None
) -> list[dict[str, str]] | None:
    """Get to `screen` by replaying the clicks that reached it before (no
    model calls, a few seconds) instead of walking in from home. Returns the
    replayed path, or None when there is none or it no longer works (the
    caller then walks in from where the browser is)."""
    path = path_to(run_id, screen)
    if not path or len(path) < 2:
        return None  # nothing recorded, or it is the start screen itself
    journal.event(
        "action",
        f"Fast-forwarding to {screen}",
        f"Replaying the {max(0, len(path) - 1)} steps that reached it before, instead of walking in again.",
    )
    start = path[0].get("url") if path and path[0].get("do") == "goto" else None
    replayed = await replay(eyes, path)
    await eyes.stop_starting_fresh()  # the mission itself decides about resume prompts
    if replayed:
        return path
    journal.event(
        "thought", f"Couldn't fast-forward to {screen}", "Walking in from the start instead."
    )
    assert screen is not None
    forget_route(run_id, screen)  # the walk in records one that works today
    if start:
        await eyes.goto(str(start))
    return None


def _screens_payload(journal: Journal) -> list[dict[str, object]]:
    return [
        {"name": s.name, "business_thing": s.entity, "kind": s.view_kind, "purpose": s.purpose}
        for s in journal.screen_rows()
    ]


async def plan_missions(run_id: uuid.UUID) -> int:
    journal = Journal(run_id)
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None or run.status in ("stopped", "paused"):
            return 0
        brief, branch_points, notes = run.brief or {}, run.branch_points, run.notes
    journal.update_run(status="planning", headline="Planning missions")
    journal.event(
        "phase", "Planning missions", "Turning the confirmed App Summary into goals to explore."
    )
    skip = set(brief.get("skip_screens") or [])  # left out by you at review
    screens = [s for s in _screens_payload(journal) if s.get("name") not in skip]
    planned = await brain.plan_missions(brief, branch_points, screens, notes)
    planned = [m for m in planned if m.get("start_screen") not in skip]
    # Most important first, then only as many as the app's size warrants.
    planned.sort(key=lambda m: -(m.get("priority") if isinstance(m.get("priority"), int) else 3))
    cap = mission_cap(len(screens))
    planned = planned[:cap]
    with Session(engine) as session:
        for m in planned:
            priority = m.get("priority")
            session.add(
                ExplorerMission(
                    run_id=run_id,
                    title=str(m.get("title") or m["goal"])[:200],
                    goal=str(m["goal"])[:1000],
                    kind=str(m.get("kind") or "task")[:20],
                    why=_text(m.get("why")),
                    priority=priority if isinstance(priority, int) else 3,
                    instructions=_text(m.get("instructions")),
                    condition=_text(m.get("condition")),
                    expected=_text(m.get("expected")),
                    start_screen=_text(m.get("start_screen")),
                )
            )
        session.commit()
    count = len(planned)
    if count == 0:
        # The workflow ends here: never leave the run showing "exploring" (an
        # active status that would block every new run for the app).
        reason = "Couldn't plan any missions from the App Summary"
        journal.event("error", reason, "Press Resume to try planning again.")
        journal.update_run(status="failed", headline=reason, error=reason)
        return 0
    journal.update_run(status="exploring", headline=f"Exploring: {count} missions planned")
    journal.event(
        "phase",
        f"Mission Board ready: {count} missions",
        "Working through them a few at a time — each one is recorded.",
    )
    return count


def _text(value: object) -> str | None:
    return str(value)[:1000] if value else None


def one_at_a_time(session: Session, run_id: uuid.UUID) -> bool:
    """An app that keeps progress per account (saved drafts, a cart) can't
    take parallel agents on one sign-in: they overwrite each other's state
    and the mess gets reported as app bugs."""
    screens = session.exec(
        select(ExplorerScreen.name, ExplorerScreen.purpose).where(ExplorerScreen.run_id == run_id)
    ).all()
    return keeps_state([f"{name} {purpose or ''}" for name, purpose in screens])


def queued_missions(run_id: uuid.UUID) -> list[str]:
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None or run.status in ("stopped", "paused"):
            return []
        rows = [
            str(r)
            for r in session.exec(
                select(ExplorerMission.id)
                .where(ExplorerMission.run_id == run_id, ExplorerMission.status == "queued")
                .order_by(col(ExplorerMission.priority).desc(), col(ExplorerMission.created_at))
            ).all()
        ]
        if not one_at_a_time(session, run_id):
            return rows
        busy = session.exec(
            select(ExplorerMission.id).where(
                ExplorerMission.run_id == run_id,
                # a mission waiting for your answer still holds its browser
                col(ExplorerMission.status).in_(("running", "waiting")),
                # one started longer ago than a mission may run died with its worker
                col(ExplorerMission.started_at) > datetime.now(UTC) - timedelta(minutes=45),
            )
        ).first()
        # The workflow pool asks again once the running one ends.
        return [] if busy is not None else rows[:1]


async def run_mission(
    run_id: uuid.UUID, mission_id: uuid.UUID, heartbeat: Callable[[], None]
) -> str:
    journal = Journal(run_id, mission_id)
    with Session(engine) as session:
        mission = session.get(ExplorerMission, mission_id)
        if mission is None or mission.status != "queued":
            return "not-queued"
        title, goal, kind = mission.title, mission.goal, mission.kind
        added_by = mission.added_by
        instructions, condition, expected = (
            mission.instructions,
            mission.condition,
            mission.expected,
        )
        start_screen = mission.start_screen
    if journal.status() == "stopped":
        journal.update_mission(status="skipped")
        return "skipped"

    journal.update_mission(status="running", started_at=datetime.now(UTC))
    with Session(engine) as session:
        statuses = session.exec(
            select(ExplorerMission.status).where(ExplorerMission.run_id == run_id)
        ).all()
    number = sum(1 for s in statuses if s not in ("queued",))
    journal.event("phase", f"Mission {number} of {len(statuses)}: {title}", goal)
    target = load_target(run_id)

    with tempfile.TemporaryDirectory(
        prefix="explorer-rec-", ignore_cleanup_errors=True
    ) as record_dir:
        started_at = datetime.now(UTC)
        started = time.monotonic()
        eyes = await open_signed_in(target, journal, record_dir=record_dir)
        if eyes is None:
            journal.update_mission(
                status="failed", outcome="Couldn't sign in", finished_at=datetime.now(UTC)
            )
            return "failed"
        status = "failed"
        try:
            with Session(engine) as session:
                stateful = one_at_a_time(session, run_id)
            # An app that keeps progress per user (FNOL's wizard) shows a
            # mid-flow screen empty, or bounces it, when opened by address:
            # the earlier answers aren't in memory. Walk in from the start.
            known = {} if stateful else {s.name: s.url for s in journal.screen_rows()}
            lead_in = await fast_forward(eyes, journal, run_id, start_screen) if stateful else None
            if start_screen and start_screen in known:
                await eyes.goto(known[start_screen])
            mind = Mind(
                journal,
                target.notes,
                heartbeat,
                condition=condition,
                home_url=target.app_url,
                goal_rule=(await ensure_scope(run_id) or {}).get("rule"),
            )

            def stop_requested() -> bool:
                return journal.status() == "stopped" or journal.mission_status() == "skipped"

            async def asker(
                kind: str,
                question: str,
                why: str | None,
                options: list[str],
                shot: uuid.UUID | None,
            ) -> str | None:
                return await ask(journal, kind, question, why, options, shot, heartbeat)

            paths: list[list[str]] = []
            ends: list[str] = []
            mind.on_screen = lambda _visit, name: paths[-1].append(name)
            steps_taken, result = 0, Pursuit()
            for attempt in range(TASK_PASSES if kind == "task" else 1):
                if attempt:
                    journal.event(
                        "phase",
                        f"Walking “{title}” again (attempt {attempt + 1} of {TASK_PASSES})",
                        "Checking the flow stays the same, and looking for screens that only "
                        "appear sometimes.",
                    )
                    await eyes.goto(known.get(start_screen or "") or target.app_url)
                    if stateful:
                        lead_in = await fast_forward(eyes, journal, run_id, start_screen)
                    mind.last_screen_id = None  # a fresh start, not a click from the last screen
                paths.append([])
                result = await pursue(
                    eyes,
                    mind,
                    journal,
                    goal,
                    target.notes,
                    heartbeat,
                    instructions=instructions,
                    known_screens=known,
                    # walking in from the start costs the steps a jump saved
                    max_steps=MISSION_STEPS + (10 if stateful and not lead_in else 0),
                    stop_requested=stop_requested,
                    non_production=target.non_production,
                    ask=asker,
                    lead_in=lead_in,
                    # A mission you added yourself is carried out even outside the goal.
                    obey_goal=added_by != "user",
                )
                steps_taken += result.steps
                ends.append(result.ended)
                # Walking a path again after it got stuck or went in circles
                # only repeats the same dead end.
                if result.ended in ("stopped", "stuck"):
                    break
            stability = _compare_paths(journal, title, paths, ends)
            if result.ended == "stopped":
                status = "skipped"
                journal.update_mission(
                    status=status, outcome="Stopped before finishing", finished_at=datetime.now(UTC)
                )
                return status

            assert eyes.page is not None
            final = await eyes.look(eyes.page.url, None, 0)
            verdict = await brain.judge_outcome(
                final.shot,
                goal,
                expected,
                result.history,
                result.ended,
                load_target(run_id).notes,  # re-read: answers may have arrived meanwhile
            )
            matches = verdict.get("matches")
            matches = matches if isinstance(matches, bool) else None
            record = verdict.get("created_record")
            if isinstance(record, dict) and record.get("value") and record.get("what"):
                fact = remember_record(
                    run_id,
                    str(record["what"])[:80],
                    str(record["value"])[:80],
                    f"created by: {title}",
                )
                if fact:
                    journal.event(
                        "thought", f"Noted for later: {record['what']} {record['value']}", fact
                    )
            summary = str(verdict.get("summary") or result.outcome) + (
                f" {stability}" if stability else ""
            )
            # A mission that got stuck never saw the real outcome: "it didn't
            # happen" is about Explorer's walk, not the app. Don't call it a bug.
            if matches is False and verdict.get("difference") and result.ended != "stuck":
                shot_id = journal.shot(final.shot)
                difference = str(verdict["difference"])
                journal.health_issue(
                    "looks_wrong",
                    "medium",
                    f"{title}: {difference[:160]}",
                    difference,
                    final.url,
                    shot_id,
                )
                journal.event("health", f"Possible bug: {title}", difference, shot_id)
                # Ask without blocking: your answer decides whether this is a
                # bug or the rule should change (PLAN.md §4.3).
                await ask(
                    journal,
                    "rule",
                    str(verdict.get("ask_user") or "").strip()
                    or f"{difference} Is that how it should work?",
                    f"While trying to: {title}. What the app did: {difference}",
                    ["It's a bug", "It's correct — that's how it should work"],
                    shot_id,
                    heartbeat,
                    wait=False,
                    issue_id=journal.issue_id(f"{title}: {difference[:160]}"),
                )
            status = "blocked" if result.ended == "stuck" else "done"
            if journal.mission_status() == "skipped":
                # Skipped while it was finishing up: your skip wins.
                journal.update_mission(outcome="Skipped by you", finished_at=datetime.now(UTC))
                return "skipped"
            journal.update_mission(
                status=status,
                outcome=summary[:1000],
                matches_expected=matches,
                steps=steps_taken,
                new_screens=mind.new_screens,
                finished_at=datetime.now(UTC),
            )
            journal.event(
                "summary",
                f"Mission {'finished' if status == 'done' else 'got stuck'}: {title}",
                summary,
            )
            last = next((p[-1] for p in reversed(paths) if p), None)
            _queue_follow_ups(journal, title, result, last)
            return status
        finally:
            video = await eyes.close()
            if video and Path(video).exists():
                with Session(engine) as session:
                    session.add(
                        ExplorerRecording(
                            run_id=run_id,
                            mission_id=mission_id,
                            data=Path(video).read_bytes(),
                            started_at=started_at,
                            duration_seconds=round(time.monotonic() - started, 1),
                        )
                    )
                    session.commit()


def follow_ups(
    parent: str,
    result: Pursuit,
    last_screen: str | None,
    last_kind: str | None,
    planned_from: set[str],
    taken: set[str],
) -> list[dict[str, str]]:
    """Ways forward a mission saw but didn't take, on screens the Mission
    Board was planned without (first reached by a mission): each other option
    of a choice there, and carrying on from a form/wizard step the mission
    ended on because its own goal was met. Screens the plan already knew had
    their branch points planned for, so they're skipped. `taken` holds the
    run's mission titles (no repeats) and is updated."""

    def route_to(screen: str) -> str:
        # How the parent got there, for a walk in when fast-forward can't.
        steps: list[str] = []
        for line in result.history:
            if line.startswith(f"{screen}:"):
                break
            steps.append(line)
        return f"Get to {screen} the way “{parent}” did: " + "; ".join(steps)[:800]

    out: list[dict[str, str]] = []
    for branch in result.branches:
        step, question = str(branch.get("step") or ""), str(branch.get("question") or "")
        if not step or step in planned_from:
            continue
        for option in (branch.get("options_worth_trying_later") or [])[:4]:
            option = str(option).strip()
            title = f"Try “{option}” on {step}"[:200]
            if option and title not in taken:
                taken.add(title)
                out.append(
                    {
                        "title": title,
                        "kind": "branch",
                        "goal": f"On {step}, choose “{option}” for “{question}”, then carry on "
                        "as far as that path goes.",
                        "condition": f"“{question}” is “{option}”",
                        "start_screen": step,
                        "instructions": route_to(step),
                    }
                )
    title = f"Carry on from {last_screen}"
    if (
        result.ended == "done"
        and last_screen
        and last_screen not in planned_from
        and last_kind in ("form", "wizard")
        and title not in taken
    ):
        taken.add(title)
        out.append(
            {
                "title": title,
                "kind": "task",
                "goal": f"Start on {last_screen} and carry on through the steps that follow it, "
                "as far as the flow goes.",
                "start_screen": last_screen,
                "instructions": route_to(last_screen),
            }
        )
    return out


def _queue_follow_ups(
    journal: Journal, parent: str, result: Pursuit, last_screen: str | None
) -> None:
    """Queue `follow_ups` as missions; the workflow's pool picks them up."""
    with Session(engine) as session:
        missions = session.exec(
            select(ExplorerMission).where(ExplorerMission.run_id == journal.run_id)
        ).all()
        planned_at = min(m.created_at for m in missions)
        screens = journal.screen_rows()
        planned_from = {s.name for s in screens if s.created_at < planned_at}
        kinds = {s.name: s.view_kind for s in screens}
        new = follow_ups(
            parent,
            result,
            last_screen,
            kinds.get(last_screen or ""),
            planned_from,
            {m.title for m in missions},
        )
        # ponytail: two missions finishing at the same moment may both add the
        # same follow-up; a unique (run_id, title) constraint if that shows up.
        room = max(0, MAX_MISSIONS - len(missions))
        for m in new[:room]:
            session.add(ExplorerMission(run_id=journal.run_id, priority=2, **m))
        session.commit()
    for m in new[:room]:
        journal.event("phase", f"Follow-up mission added: {m['title']}", m["goal"])
    if new[room:]:
        journal.event(
            "thought",
            f"Not explored: {len(new) - room} more way(s) forward",
            f"The run has its {MAX_MISSIONS} missions: "
            + "; ".join(m["title"] for m in new[room:])[:800],
        )


def _compare_paths(journal: Journal, title: str, paths: list[list[str]], ends: list[str]) -> str:
    """Same screens in the same order on every attempt = a stable flow.
    Otherwise the screens missing from some attempts are conditional — mark
    them so tests and the App Map know they only appear sometimes."""
    # Re-reading the same screen (a rejected Continue) is one step, not two.
    paths = [[name for i, name in enumerate(p) if i == 0 or p[i - 1] != name] for p in paths]
    if len(paths) < 2:
        return ""
    # Only attempts that reached the end say anything about which screens a
    # flow has: one that got stuck early simply never saw the later ones.
    finished = [p for p, end in zip(paths, ends, strict=True) if end in ("done", "final") and p]
    stuck = [
        (i + 1, p[-1] if p else "the start")
        for i, (p, end) in enumerate(zip(paths, ends, strict=True))
        if end not in ("done", "final")
    ]
    # Attempts that stopped on different screens didn't do the same thing —
    # one simply got less far. Only attempts ending on the same screen are
    # compared screen by screen.
    groups: dict[str, list[list[str]]] = {}
    for p in finished:
        groups.setdefault(p[-1], []).append(p)
    same = max(groups.values(), key=len, default=[])
    if (stuck and finished) or len(groups) > 1:
        where = "; ".join(
            [f"attempt {n} got stuck on {screen}" for n, screen in stuck]
            + ([f"attempts ended on {', '.join(groups)}"] if len(groups) > 1 else [])
        )
        journal.event(
            "thought",
            f"Not repeatable: {title}",
            f"The same steps gave different results ({where}).",
        )
        note = f"The flow isn't repeatable: {where}."
        return note + (" " + _compare_finished(journal, title, same) if len(same) >= 2 else "")
    if len(same) < 2:
        return ""
    return _compare_finished(journal, title, same)


def _compare_finished(journal: Journal, title: str, paths: list[list[str]]) -> str:
    if all(p == paths[0] for p in paths):
        journal.event(
            "thought",
            f"Same path on all {len(paths)} attempts: {title}",
            " → ".join(paths[0])[:900],
        )
        return f"The flow was the same on all {len(paths)} attempts."
    sometimes = sorted(set().union(*paths) - set.intersection(*(set(p) for p in paths)))
    journal.event(
        "thought",
        f"The path changed between attempts: {title}",
        "\n".join(f"Attempt {i + 1}: {' → '.join(p)}" for i, p in enumerate(paths))[:900],
    )
    if sometimes:
        condition = (
            f"it shows on some attempts at “{title}” but not others — probably because of "
            "what an earlier attempt left behind (a saved draft, an earlier report)"
        )
        with Session(engine) as session:
            for screen in session.exec(
                select(ExplorerScreen).where(
                    ExplorerScreen.run_id == journal.run_id,
                    col(ExplorerScreen.name).in_(sometimes),
                    col(ExplorerScreen.condition).is_(None),
                )
            ).all():
                screen.condition = condition[:500]
                session.add(screen)
                journal.event(
                    "screen",
                    f"Conditional screen found: {screen.name}",
                    f"Only appears when {condition}.",
                )
            session.commit()
        return (
            f"The flow changed between {len(paths)} attempts; these screens only appeared "
            f"sometimes: {', '.join(sometimes)}."
        )
    return f"The same screens appeared on all {len(paths)} attempts, but in a different order."


CUT_OFF_ONCE = "Cut off once"


def requeue_mission(mission_id: uuid.UUID) -> None:
    """A mission whose worker died mid-run (restart, crash) goes back in the
    queue instead of showing as running forever."""
    with Session(engine) as session:
        mission = session.get(ExplorerMission, mission_id)
        if mission is not None and mission.status in ("running", "waiting"):
            # Once only: cut off again, it is given up (loop guard).
            if mission.outcome == CUT_OFF_ONCE:
                mission.status, mission.outcome = "blocked", "Couldn't finish this mission"
            else:
                mission.status, mission.outcome = "queued", CUT_OFF_ONCE
            mission.started_at = None
            session.add(mission)
            session.commit()


def finish_exploring(run_id: uuid.UUID) -> None:
    journal = Journal(run_id)
    if journal.status() in ("stopped", "paused"):
        return  # paused: Resume carries on, so leave the queue as it is
    screens = journal.screen_rows()
    hidden = sum(1 for s in screens if s.condition)
    with Session(engine) as session:
        missions = session.exec(
            select(ExplorerMission).where(ExplorerMission.run_id == run_id)
        ).all()
    # Loop guard: a mission whose worker died twice must not show as running.
    with Session(engine) as session:
        for m in session.exec(
            select(ExplorerMission).where(
                ExplorerMission.run_id == run_id,
                col(ExplorerMission.status).in_(("queued", "running", "waiting")),
            )
        ).all():
            m.status, m.outcome = "blocked", "Couldn't finish this mission"
            session.add(m)
        session.commit()
        missions = session.exec(
            select(ExplorerMission).where(ExplorerMission.run_id == run_id)
        ).all()
    done = sum(1 for m in missions if m.status == "done")
    bugs = sum(1 for m in missions if m.matches_expected is False)
    journal.update_run(
        status="explored",
        headline=f"Explored: {len(screens)} screens, {hidden} hidden",
    )
    journal.event(
        "summary",
        "Exploration complete",
        f"{done} of {len(missions)} missions completed. {len(screens)} screens understood, "
        f"{hidden} of them hidden behind a choice or situation. {bugs} possible bug(s) where the app "
        "did something different from what it should.",
    )
