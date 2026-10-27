"""Stage 5 — proven test cases in 5 kinds (PLAN.md §6).

1. Plan: the model proposes tests grounded in what Explorer actually saw;
   tests naming screens it never saw are dropped.
2. Build: carry the test out in a browser, recording the exact actions, and
   pick a real on-screen proof (a message, a heading, an address).
3. Prove: first replay it with the decisive step removed, where the proof
   must NOT hold (cheap, so weak tests go early); then replay the recorded
   actions PROOF_RUNS times (no model) — the proof must hold every time.
   Anything else is dropped with the reason.
4. Trust: when the app does something different from what should happen,
   the test is kept as a Known bug, never as correct behaviour (§4).
"""

import asyncio
import os
import re
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from explorer_core import (
    TEST_KINDS,
    ExplorerHealthIssue,
    ExplorerMission,
    ExplorerRecording,
    ExplorerRun,
    ExplorerScreen,
    ExplorerTestCase,
    ExplorerTransition,
)
from sqlmodel import Session, col, select

from explorer_worker import brain, quality
from explorer_worker.browser import Visit
from explorer_worker.db import engine
from explorer_worker.goal import ensure_scope, screens_in_goal
from explorer_worker.journal import Journal
from explorer_worker.mind import Mind
from explorer_worker.missions import fast_forward, one_at_a_time
from explorer_worker.pursue import Pursuit, path_to, pursue
from explorer_worker.sense import about_resuming, route_starts_at_entry, same_place, url_pattern
from explorer_worker.session import (
    Target,
    load_target,
    needs_sign_in,
    open_signed_in,
    open_signed_out,
)
from explorer_worker.testkit import (
    ABSENT_WAIT_MS,
    api_call_count,
    broken_variants,
    holds,
    playwright_code,
    replay,
)

MAX_TESTS = 150
SCREENS_PER_PLAN = 3


def test_cap(screen_count: int) -> int:
    """Scenarios worth proving for an app this size (each one is proven by
    several full replays): enough for every checklist item a screen has, 10 to MAX_TESTS."""
    return max(10, min(MAX_TESTS, 15 * screen_count))


# Replays without the model, in a clean browser, that must all pass before a
# scenario is kept. They use the very locators and proof check the exported
# test uses (recorded locators, `holds`), from the entry point, so a route
# that only worked in the live browser is caught here, never in your test
# run. One by default (the broken-on-purpose run comes first); 2 also catch
# an app that behaves differently from run to run; 0 turns proving off.
PROOF_RUNS = int(os.environ.get("EXPLORER_PROOF_RUNS", "1"))

# Journey scenarios: one whole business flow each, from the app's start to the
# task's final outcome — built first, so even a stopped run has them.
MAX_JOURNEYS = 8
JOURNEY_STEPS = 40  # FNOL's full claim is ~27 actions; screen checks get 20-24
_FOLLOW_UP = re.compile(r"^(Try “|Carry on from )")


def journeys_from(missions: list[ExplorerMission]) -> list[ExplorerMission]:
    """The missions worth a whole-flow scenario: finished, not a rule check,
    a real walk (5+ steps), and either planned or a follow-up that found new
    screens. Most new screens first. ponytail: a follow-up that found nothing
    new is taken as a variant of a covered route (another field value, same
    screens); comparing recorded routes would be exact."""
    picked = [
        m
        for m in missions
        if m.status == "done"
        and m.kind != "rule"
        and m.steps >= 5
        and (m.new_screens > 0 or not _FOLLOW_UP.match(m.title))
    ]
    picked.sort(key=lambda m: (-m.new_screens, -m.steps))
    return picked[:MAX_JOURNEYS]

SIGN_IN_RULES = (
    "This browser is signed out. To sign in with the saved test login, type exactly "
    "{{username}} and {{password}} (Explorer fills in the real ones). For a wrong login, "
    "use a made-up username, never the saved one, so the real account is not locked. "
)


class QuietMind(Mind):
    """Carrying out a planned test doesn't need every screen re-read by the
    model — that already happened while exploring. Names come from the
    page itself; nothing new is learned. It still saves the screenshot, so
    the Live view keeps moving while scenarios are tried (no screenshot
    here left Live frozen on the last mission for the whole stage)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Screens a route may be saved for (see `route_screens`); empty = none.
        self.screen_ids: dict[str, uuid.UUID] = {}
        self.visited: set[str] = set()  # address patterns this walk was on
        # Address pattern -> the screen's place against the run's Goal
        # (explorer_worker.goal); empty = no goal.
        self.goal_fits: dict[str, str] = {}
        self.last_goal_fit: str | None = None

    async def take_in(self, visit: Visit, reached_by: str | None, action: str | None = None) -> str:
        self.heartbeat()
        self.visited.add(url_pattern(visit.url))
        self.last_goal_fit = self.goal_fits.get(url_pattern(visit.url))
        self.last_screen_id = self.screen_ids.get(url_pattern(visit.url))
        headings = visit.inventory.get("headings") or []
        name = str(headings[0] if headings else visit.inventory.get("title") or "screen")[:80]
        self.journal.event("thought", f"On {name}", None, self.journal.shot(visit.shot))
        return name


# The checklist items that only check a screen opens with its main content.
_OPENS = re.compile(r"^(F|L|P)-01\b")
_HAS_DIGIT = re.compile(r"\d")


def opens_check(meta: dict[str, Any]) -> bool:
    return bool(_OPENS.match(str(meta.get("coverage") or "")))


def heading_proof(inventory: dict[str, Any]) -> dict[str, str] | None:
    """The screen's first heading that stays the same on every replay (no
    numbers: references, dates and counts change) — its page title when it
    has no heading tags (styled labels). A title that is on every screen
    (the app's name) fails the broken-on-purpose run and is never kept."""
    for heading in [*(inventory.get("headings") or []), inventory.get("title") or ""]:
        text = " ".join(str(heading).split())
        if 3 <= len(text) <= 120 and not _HAS_DIGIT.search(text):
            return {"kind": "text_visible", "value": text}
    return None


async def screen_opens_proof(eyes: Any) -> tuple[dict[str, str], Visit] | None:
    assert eyes.page is not None
    final = await eyes.look(eyes.page.url, None, 0)
    check = heading_proof(final.inventory)
    if check is None or not await holds(eyes, check):
        return None  # nothing usable: the model builds it as usual
    return check, final


def reached_screen(screens: list[ExplorerScreen], name: str | None, visited: set[str]) -> bool:
    """Did a walk get to the screen called `name`? Known only where its
    address shows that screen alone; anywhere else (an app that keeps one
    address for many screens, an unknown screen) it may have: True."""
    unique = route_screens(screens)
    own = [s.url_pattern for s in screens if s.name == name]
    if not own or any(pattern not in unique for pattern in own):
        return True
    return any(pattern in visited for pattern in own)


def goal_fits_by_address(screens: list[ExplorerScreen]) -> dict[str, str]:
    """Address pattern -> that screen's place against the run's Goal, for the
    addresses that show exactly one screen (like `route_screens`)."""
    fits = {s.id: s.goal_fit for s in screens if s.goal_fit}
    return {pattern: fits[sid] for pattern, sid in route_screens(screens).items() if sid in fits}


def route_screens(screens: list[ExplorerScreen]) -> dict[str, uuid.UUID]:
    """Address pattern -> screen, for the addresses that show exactly one
    screen: there, a scenario's walk can be saved as that screen's route. An
    app that keeps one address for many screens gets none (missions, which
    read every screen, still save theirs)."""
    by_pattern: dict[str, list[uuid.UUID]] = {}
    for screen in screens:
        by_pattern.setdefault(screen.url_pattern, []).append(screen.id)
    return {pattern: ids[0] for pattern, ids in by_pattern.items() if len(ids) == 1}


async def plan_tests(run_id: uuid.UUID) -> int:
    journal = Journal(run_id)
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None or run.status in ("stopped", "paused"):
            return 0
        brief = run.brief or {}
        notes = load_target(run_id).notes  # includes everything remembered
        screens = session.exec(select(ExplorerScreen).where(ExplorerScreen.run_id == run_id)).all()
        names = {s.id: s.name for s in screens}
        # States the hunt faked (no data, server error, a year from now) can't
        # be reached by a test: plan only on screens a user can really open.
        # Screens you left out at review get no scenarios.
        skip = set(brief.get("skip_screens") or [])
        screens = [
            s
            for s in screens
            if not (s.condition or "").startswith("Simulated") and s.name not in skip
        ]
        links = [
            f"{names.get(t.from_screen_id)} --{t.action}--> {names.get(t.to_screen_id)}"
            for t in session.exec(
                select(ExplorerTransition).where(ExplorerTransition.run_id == run_id)
            ).all()
        ]
        missions = [
            {"title": m.title, "outcome": m.outcome, "as_it_should": m.matches_expected}
            for m in session.exec(
                select(ExplorerMission).where(ExplorerMission.run_id == run_id)
            ).all()
            if m.outcome
        ]
        bugs = [
            i.title
            for i in session.exec(
                select(ExplorerHealthIssue).where(
                    ExplorerHealthIssue.run_id == run_id, ExplorerHealthIssue.kind == "looks_wrong"
                )
            ).all()
        ]
        screen_info = [
            {
                "name": s.name,
                "business_thing": s.entity,
                "kind": s.view_kind,
                "purpose": s.purpose,
                "fields": [
                    {
                        "label": f.get("label"),
                        "required": f.get("required"),
                        "notes": f.get("notes"),
                    }
                    for f in s.fields
                ][:25],
                "buttons": [a.get("label") for a in s.actions][:20],
            }
            for s in screens
        ]
    journal.update_run(status="testing", headline="Working out scenarios")
    journal.event(
        "phase",
        "Working out scenarios",
        "Turning what I learned into scenarios to test. I'll try each one in the app and "
        "make sure it works the same way every time.",
    )
    # A few screens per model call, several calls at once: one call could not
    # write the whole checklist for every screen.
    names = [str(s["name"]) for s in screen_info]
    chunks = [names[i : i + SCREENS_PER_PLAN] for i in range(0, len(names), SCREENS_PER_PLAN)]
    gate = asyncio.Semaphore(4)
    target = load_target(run_id)
    may_save = target.non_production

    async def plan_part(index: int, only: list[str]) -> list[dict[str, Any]]:
        async with gate:
            return await brain.plan_tests(
                brief,
                screen_info,
                links,
                missions,
                bugs,
                notes,
                may_save=may_save,
                only=only,
                # An app with no login gets no sign-in scenarios.
                sign_in=index == 0 and target.requires_login,
            )

    parts = await asyncio.gather(
        *(plan_part(i, c) for i, c in enumerate(chunks or [[]])), return_exceptions=True
    )
    planned = [t for part in parts if isinstance(part, list) for t in part]
    # Review the whole plan once before trying anything: a duplicate, or a
    # scenario needing a flow exploring never saw, cost minutes each to try.
    try:
        verdicts = await brain.review_plan(planned, screen_info, links, missions)
    except Exception:  # noqa: BLE001 — the review only saves time; never block planning
        verdicts = []
    skipped = left_out(planned, verdicts)
    if skipped:
        journal.event(
            "thought",
            f"Left out {len(skipped)} scenario(s) before trying them",
            "Duplicates of another scenario, or needing a screen or step exploring never saw.",
        )
    reviewed = [t for i, t in enumerate(planned) if i not in skipped]
    known = {s["name"] for s in screen_info}
    kept = 0
    with Session(engine) as session:
        # Journeys first: the whole flows missions completed, start to finish.
        home = min(screens, key=lambda s: s.created_at).name if screens else None
        rows = session.exec(select(ExplorerMission).where(ExplorerMission.run_id == run_id))
        journeys = journeys_from(list(rows.all()))
        for m in journeys if home else []:
            session.add(
                ExplorerTestCase(
                    run_id=run_id,
                    kind="journey",
                    title=m.title[:200],
                    purpose=m.goal[:500],
                    start_screen=home,
                    steps=[m.goal[:500]],
                    expected=(m.expected or "The task completes and the app confirms it.")[:1000],
                    trust="standard",
                    script=[
                        {
                            "how_to_run": (
                                f"{m.goal} {m.instructions or ''} Do the whole task from the "
                                "start to its final outcome, the way a customer would."
                            )[:1000],
                            "rule": "",
                            "coverage": "X-Journey",
                            "linked_to": "",
                            "signed_out": False,
                        }
                    ],
                    status="planned",
                )
            )
            kept += 1
        tried = [(t, None) for t in balanced(reviewed, test_cap(len(screen_info)))]
        for t, reason in tried + [(planned[i], why) for i, why in skipped.items()]:
            kind = str(t.get("kind") or "")
            if kind not in TEST_KINDS or not t.get("title") or not t.get("expected"):
                continue
            start = str(t.get("start_screen") or "")
            if start in skip:
                continue
            # A sign-in test may start on a sign-in screen Explorer never
            # mapped (it signs in before exploring): the login address is used.
            grounded = start in known or bool(t.get("signed_out"))
            session.add(
                ExplorerTestCase(
                    run_id=run_id,
                    kind=kind,
                    title=str(t["title"])[:200],
                    purpose=str(t.get("purpose") or "")[:500],
                    technique=_text(t.get("technique")),
                    business_thing=_text(t.get("business_thing")),
                    start_screen=start or None,
                    steps=[str(s) for s in (t.get("steps") or [])][:15],
                    expected=str(t["expected"])[:1000],
                    trust=str(t.get("trust") or "standard")[:20],
                    script=[
                        {
                            "how_to_run": str(t.get("how_to_run") or "")[:1000],
                            "rule": str(t.get("rule") or "")[:500],
                            "coverage": str(t.get("coverage") or "")[:120],
                            "linked_to": str(t.get("linked_to") or "")[:20],
                            "signed_out": bool(t.get("signed_out")),
                        }
                    ],
                    status="planned" if grounded and not reason else "dropped",
                    drop_reason=reason
                    or (None if grounded else "Refers to a screen Explorer never saw"),
                )
            )
            kept += grounded and not reason
        # Page-quality checks, measured by the browser: one set per real
        # screen. Screens of a step-by-step flow can't be opened directly.
        checks = 0
        if not one_at_a_time(session, run_id):
            one_per_page = {s.url_pattern: s for s in screens}.values()
            for screen in one_per_page:
                for name in quality.planned_checks({"fields": screen.fields}):
                    row = quality.test_row(name, {"name": screen.name})
                    session.add(
                        ExplorerTestCase(
                            run_id=run_id,
                            kind="page_quality",
                            title=row["title"][:200],
                            purpose=row["purpose"],
                            start_screen=screen.name,
                            steps=row["steps"],
                            expected=row["expected"],
                            trust="standard",
                            check=row["check"],
                            script=[],
                            status="planned",
                        )
                    )
                    checks += 1
        session.commit()
    cap = test_cap(len(screen_info))
    journal.event(
        "phase",
        f"{kept} scenarios to try",
        f"The plan had {len(planned)} ideas"
        + (
            f"; the {cap} most important are tried (up to 6 per screen)"
            if len(planned) > cap
            else ""
        )
        + (f", plus {checks} page-quality checks" if checks else "")
        + ". Trying each one in the app now.",
    )
    return kept + checks


async def _prove_quality(
    journal: Journal,
    test_id: uuid.UUID,
    title: str,
    name: str,
    url: str,
    target: Target,
) -> str:
    """Measure a page-quality check PROOF_RUNS times. Always fine: proven.
    Always failing: a bug found (the exported test is parked as known bug).
    Anything else: dropped, never a flaky test."""
    eyes = await open_signed_in(target, journal)
    if eyes is None:
        return drop(journal, test_id, title, "Couldn't sign in")
    results: list[list[str]] = []
    shot_id = None
    try:
        for _ in range(max(1, PROOF_RUNS)):  # measured at least once
            found = await quality.measure(eyes, name, url)
            assert eyes.page is not None
            if not same_place(eyes.page.url, url):
                return drop(journal, test_id, title, "This screen can't be opened by its address")
            if found is None:
                return drop(journal, test_id, title, "Nothing on this screen to check")
            results.append(found)
            if shot_id is None:
                shot_id = journal.shot((await eyes.look(eyes.page.url, None, 0)).shot)
    finally:
        await eyes.close()
    if all(results) != any(results):
        return drop(journal, test_id, title, "Gave different results on repeat runs")
    failing = "; ".join(results[0][:5]) if results[0] else None
    tag = (
        "@auth"
        if needs_sign_in(target.auth_method, target.secret_ref, target.requires_login)
        else "@public"
    )
    status = "known_bug" if failing else "proven"
    _update(
        test_id,
        status=status,
        observed=(failing or "Fine on every run")[:1000],
        script=[{"do": "goto", "url": url}],
        evidence_shot_id=shot_id,
        proof_runs=len(results),
        proof_passes=len(results),
        catches_breakage=True,
        code=quality.playwright_code(title, name, url, tag, failing),
        finished_at=datetime.now(UTC),
    )
    journal.event(
        "summary",
        f"{'Possible bug' if failing else 'Scenario ready'}: {title}",
        (f"Every run found: {failing}" if failing else f"Fine on all {len(results)} runs.")[:600],
        shot_id,
    )
    return status


def _text(value: object) -> str | None:
    return str(value)[:300] if value else None


def screen_by_screen(rows: Any) -> list[str]:
    """(id, kind, start screen) in plan order -> ids, journeys first, then
    every scenario of a screen together: the first one walks in and saves the
    route, the rest of that screen replay it at once (pursue.remember_route).
    Each scenario still starts from the entry point in a clean browser."""
    rows = list(rows)
    first: dict[str, int] = {}
    for index, (_, _, screen) in enumerate(rows):
        first.setdefault(str(screen), index)
    ordered = sorted(
        range(len(rows)),
        key=lambda i: (rows[i][1] != "journey", first[str(rows[i][2])], i),
    )
    return [str(rows[i][0]) for i in ordered]


def planned_tests(run_id: uuid.UUID) -> list[str]:
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None or run.status in ("stopped", "paused"):
            return []
        rows = screen_by_screen(
            session.exec(
                select(ExplorerTestCase.id, ExplorerTestCase.kind, ExplorerTestCase.start_screen)
                .where(ExplorerTestCase.run_id == run_id, ExplorerTestCase.status == "planned")
                .order_by(col(ExplorerTestCase.created_at))
            ).all()
        )
        if not one_at_a_time(session, run_id):
            return rows
        busy = session.exec(
            select(ExplorerTestCase.id).where(
                ExplorerTestCase.run_id == run_id, ExplorerTestCase.status == "building"
            )
        ).first()
        return [] if busy is not None else rows[:1]  # see missions.one_at_a_time


def _update(test_id: uuid.UUID, **changes: Any) -> None:
    with Session(engine) as session:
        test = session.get(ExplorerTestCase, test_id)
        if test is None:
            return
        for key, value in changes.items():
            setattr(test, key, value)
        session.add(test)
        session.commit()


def drop(journal: Journal, test_id: uuid.UUID, title: str, reason: str) -> str:
    _update(test_id, status="dropped", drop_reason=reason, finished_at=datetime.now(UTC))
    journal.event("thought", f"Left out: {title}", reason)
    return "dropped"


async def build_and_prove(
    run_id: uuid.UUID, test_id: uuid.UUID, heartbeat: Callable[[], None]
) -> str:
    journal = Journal(run_id)
    with Session(engine) as session:
        test = session.get(ExplorerTestCase, test_id)
        if test is None or test.status != "planned":
            return "not-planned"
        title, kind, expected = test.title, test.kind, test.expected
        check_name = str((test.check or {}).get("value") or "")
        start_screen = test.start_screen
        meta = test.script[0] if test.script else {}
        test_info = {
            "title": title,
            "kind": kind,
            "expected": expected,
            "coverage": (test.script[0] if test.script else {}).get("coverage"),
        }
    if journal.status() == "stopped":
        return "stopped"
    _update(test_id, status="building")
    target = load_target(run_id)
    known = {s.name: s.url for s in journal.screen_rows()}
    # Sign-in tests run in their own browser that never signed in, so they
    # can sign in, fail to, or sign out without touching the session every
    # other test shares.
    signed_out = bool(meta.get("signed_out"))
    start_url = known.get(start_screen or "") or (
        (target.login_url or target.app_url) if signed_out else None
    )
    if not start_url:
        return drop(journal, test_id, title, "Its starting screen isn't on the map")
    if kind == "page_quality":
        return await _prove_quality(journal, test_id, title, check_name, start_url, target)
    with Session(engine) as session:
        stateful = one_at_a_time(session, run_id)
    if stateful and not signed_out:
        # Same reason as missions: a mid-flow screen opened by address is
        # empty or bounces. The test (and its replay) start at the home page.
        start_url = target.app_url
    done, total = _progress(run_id)
    journal.event(
        "action",
        f"Scenario {done + 1} of {total}: {title}",
        (
            f"First I try it once, then replay it {PROOF_RUNS} times to prove it works "
            "the same way. "
            if PROOF_RUNS
            else "I try it once in the app (repeat runs are off). "
        )
        + (meta.get("how_to_run") or ""),
    )

    # 1) Build: do it once with the model, recording exact actions.
    eyes = await open_signed_out(target) if signed_out else await open_signed_in(target, journal)
    if eyes is None:
        return drop(journal, test_id, title, "Couldn't sign in")
    # Every test, for every app, starts at an entry point (the app's start,
    # where sign-in lands) and reaches its screen the way a user does: by the
    # recorded clicks that got there before, or by walking there itself —
    # never by the screen's address. An inner page opened by address only
    # worked live because that browser still held the earlier steps' state; a
    # clean browser lands elsewhere (sense.route_starts_at_entry). Starting
    # on the screen also made every check of what it shows "already on
    # screen before the test acted".
    # ponytail: a screen that IS the sign-in landing page still can't be
    # proven this way; reloading it isn't an act.
    try:
        if signed_out:
            await eyes.goto(start_url)
            lead_in = None
        else:
            await eyes.goto(target.app_url)
            eyes.remember_entry()
            lead_in = await fast_forward(eyes, journal, run_id, start_screen)
        # Unless the scenario is about resuming, a saved-progress prompt left
        # by an earlier run is answered with start over: the recorded route
        # then never depends on whichever draft the account happens to hold.
        if not signed_out and not about_resuming(f"{title} {meta.get('how_to_run') or ''}"):
            await eyes.start_fresh_on_resume_prompts()
        # A "this screen opens" check (F-01 / L-01 / P-01) needs no model: the
        # saved route got here, and the screen's own heading is the proof —
        # what the model picked for these anyway. Proven like any other below.
        quick = await screen_opens_proof(eyes) if lead_in and opens_check(meta) else None
        if quick is not None:
            check, final = quick
            matches, observed = True, f"{start_screen} opened and showed “{check['value']}”."
            result = Pursuit(actions=[{"do": "goto", "url": target.app_url}])
            journal.event(
                "thought",
                "Built without the model",
                "Replayed the saved route; the screen's own heading is the proof.",
            )
        else:
            walks_in = not signed_out and not lead_in and bool(start_screen)
            how_to_run = (
                (
                    f"First get to {start_screen} from here using the app's own menus, links "
                    "and buttons. "
                    if walks_in
                    else ""
                )
                + (SIGN_IN_RULES if signed_out else "")
                + (meta.get("how_to_run") or "")
                + (
                    f" Last time this did not get far enough: {meta['lesson']} Do it "
                    "differently this time."
                    if meta.get("lesson")
                    else ""
                )
            )
            assert eyes.page is not None
            if signed_out:
                # Opening the address is this test's first act (a protected screen
                # sending the visitor to sign in is the very thing it checks).
                start_text, start_url_now = "", ""
            else:
                start_text = await eyes.page.evaluate(
                    "() => document.body ? document.body.innerText : ''"
                )
                start_url_now = eyes.page.url
            eyes.mark_calls()  # an API proof counts only what the test itself caused
            mind = QuietMind(journal, target.notes, heartbeat)
        if await ensure_scope(run_id):
            mind.goal_fits = goal_fits_by_address(journal.screen_rows())
            if not signed_out and eyes.starts_fresh:
                # A clean walk in (not signed out, not continuing a draft) is a
                # route the next scenario on the same screen can replay.
                mind.screen_ids = route_screens(journal.screen_rows())
            result = await pursue(
                eyes,
                mind,
                journal,
                f"Test “{title}” — {how_to_run or expected}",
                target.notes,
                heartbeat,
                instructions=how_to_run
                + " Carry out every step above first (enter the values, press the buttons, reopen"
                " the record when asked); stop (done) only once the outcome is visible on screen.",
                # Checklist items such as "save, reopen, compare" take more steps.
                max_steps=(
                    JOURNEY_STEPS if kind == "journey" else 24 if stateful and not lead_in else 20
                ),
                non_production=target.non_production,
                lead_in=lead_in,
                # Lets "open its address directly" tests do exactly that.
                known_screens={},  # never jump to a screen by its address
                stay_signed_out=signed_out,
            )
            assert eyes.page is not None
            final = await eyes.look(eyes.page.url, None, 0)
            # The proof must be something the test CAUSED — not text that was on
            # screen before it did anything (e.g. a permanent "* Required" note).
            rejected: list[str] = []
            for _ in range(3):
                verdict = await brain.decide_check(
                    final.shot,
                    final.inventory,
                    test_info,
                    result.history,
                    rejected,
                    calls=eyes.calls_since_mark(),
                )
                check = verdict.get("check") if isinstance(verdict.get("check"), dict) else None
                if not check or not proof_was_there_before(
                    check, start_text, start_url_now, eyes.calls_since_mark()
                ):
                    break
                rejected.append(str(check.get("value")))
            else:
                return drop(
                    journal,
                    test_id,
                    title,
                    "Every proof it found was already on screen before the test acted",
                )
            matches = verdict.get("matches_expected")
            observed = str(verdict.get("observed") or "")
            half_done = matches is None or not isinstance(matches, bool)
            set_up_failed = matches is False and verdict.get("set_up_ok") is False
            # A second try only helps when the first got to the scenario's screen
            # and went wrong there; one that never got there fails the same way
            # (and a screen Explorer can't reach is given up on, below).
            got_there = lead_in is not None or reached_screen(
                journal.screen_rows(), start_screen, mind.visited
            )
            if (half_done or set_up_failed) and not meta.get("lesson") and got_there:
                # One more try with what went wrong; the lesson makes it the last.
                _update(
                    test_id,
                    status="planned",
                    script=[{**meta, "lesson": (observed or "it stopped early")[:400]}],
                )
                journal.event("thought", f"Trying again differently: {title}", observed or None)
                return "retry"
            if half_done:
                outcome = drop(
                    journal, test_id, title, f"Couldn't carry it out far enough: {observed}"[:400]
                )
                give_up_on_screen(journal, start_screen)
                return outcome
            if set_up_failed:
                # Never report a bug the test caused itself (trust over coverage).
                return drop(
                    journal, test_id, title, f"Couldn't set up what the test needed: {observed}"[:400]
                )
            if not check or not await holds(eyes, check):
                return drop(journal, test_id, title, "Couldn't find a reliable proof on the screen")
    finally:
        await eyes.close()
    # A fast-forwarded test still starts from home: the replayed path, then
    # what the test itself did (minus its "open where I was" first step).
    script = [*lead_in, *result.actions[1:]] if lead_in else result.actions
    if not signed_out and not route_starts_at_entry(script, eyes.entry_urls):
        return drop(
            journal,
            test_id,
            title,
            "Its steps open an inner page by its address instead of getting there from the "
            "start, so it would break in a clean browser",
        )
    if signed_out:
        # The address it opened, not the sign-in page it may have bounced to.
        # Marked so the hand-off knows this test runs without the shared login.
        script = [{"do": "goto", "url": start_url, "signed_out": True}, *script[1:]]
    home_script = [{"do": "goto", "url": target.app_url}]
    # Where the test's own steps begin, after the route to its screen.
    route = lead_in or (None if signed_out else path_to(run_id, start_screen))
    own_from = len(route) if route and script[: len(route)] == route else None

    # 2) Break it on purpose first, without the model: a proof that still
    # holds without the step it depends on proves nothing, and finding that
    # out now spares the repeat runs (same verdict, a fraction of the time).
    eyes = await open_signed_out(target) if signed_out else await open_signed_in(target, journal)
    if eyes is None:
        return drop(journal, test_id, title, "Couldn't sign in for the proof runs")
    catches = False
    try:
        for broken in broken_variants(script, own_from) or [home_script]:
            heartbeat()
            if signed_out:
                await eyes.forget_session()
            await replay(eyes, broken)
            await eyes.settle()  # let a slow answer arrive before looking briefly
            if not await holds(eyes, check, ABSENT_WAIT_MS):
                catches = True
                break
    finally:
        await eyes.close()
    journal.event(
        "action",
        "Broken-on-purpose check: "
        + ("the test caught it" if catches else "the test did not notice"),
        "Replayed without its key step, to make sure the test fails when the app misbehaves.",
    )
    if not catches:
        _update(test_id, catches_breakage=False)
        return drop(
            journal,
            test_id,
            title,
            "Still passed with its key step removed, so it wouldn't catch a real problem",
        )

    # 3) Prove: replay without the model, recorded as the proof video.
    with tempfile.TemporaryDirectory(
        prefix="explorer-proof-", ignore_cleanup_errors=True
    ) as record_dir:
        started_at, started = datetime.now(UTC), time.monotonic()
        eyes = (
            await open_signed_out(target, record_dir=record_dir)
            if signed_out
            else await open_signed_in(target, journal, record_dir=record_dir)
        )
        if eyes is None:
            return drop(journal, test_id, title, "Couldn't sign in for the proof runs")
        passes, shot_id = 0, None
        try:
            failed_steps: list[str] = []
            for attempt in range(PROOF_RUNS):
                heartbeat()
                failed_before = len(failed_steps)
                if signed_out:
                    await eyes.forget_session()  # the last replay may have signed in
                worked = await replay(eyes, script, failed_steps) and await holds(eyes, check)
                if worked:
                    passes += 1
                    if shot_id is None:
                        assert eyes.page is not None
                        shot_id = journal.shot((await eyes.look(eyes.page.url, None, 0)).shot)
                journal.event(
                    "action",
                    f"Replay {attempt + 1} of {PROOF_RUNS}: {'worked' if worked else 'did not work'}",
                    None
                    if worked
                    else (
                        f"Stopped while {failed_steps[-1]}"
                        if len(failed_steps) > failed_before
                        else "The proof wasn't on screen at the end"
                    ),
                )
        finally:
            video = await eyes.close()
            if video and Path(video).exists() and PROOF_RUNS:
                with Session(engine) as session:
                    session.add(
                        ExplorerRecording(
                            run_id=run_id,
                            test_case_id=test_id,
                            data=Path(video).read_bytes(),
                            started_at=started_at,
                            duration_seconds=round(time.monotonic() - started, 1),
                        )
                    )
                    session.commit()

    _update(test_id, proof_runs=PROOF_RUNS, proof_passes=passes, catches_breakage=catches)
    if passes < PROOF_RUNS:
        return drop(
            journal,
            test_id,
            title,
            f"Gave different results on repeat runs ({passes}/{PROOF_RUNS} passed)"
            + (f" — it got stuck {failed_steps[0]}" if failed_steps else ""),
        )
    if shot_id is None:  # no repeat runs: the live run's end is the evidence
        shot_id = journal.shot(final.shot)
    status = "proven" if matches else "known_bug"
    steps = _steps(test_id)
    _update(
        test_id,
        status=status,
        observed=observed[:1000],
        check=check,
        script=script,
        evidence_shot_id=shot_id,
        code=playwright_code(
            title,
            steps,
            script,
            check,
            expected,
            None if matches else observed,
            tag="@auth"
            if not signed_out
            and needs_sign_in(target.auth_method, target.secret_ref, target.requires_login)
            else "@public",
        ),
        finished_at=datetime.now(UTC),
    )
    journal.event(
        "summary",
        f"{'Scenario ready' if matches else 'Possible bug'}: {title}",
        (
            (
                f"Worked the same way {PROOF_RUNS} times. "
                if PROOF_RUNS
                else "Worked when tried (repeat runs are off). "
            )
            + f"It passes when the screen shows “{check['value']}”."
            if matches
            else f"Should: {expected} — the app instead: {observed}"
        )[:600],
        shot_id,
    )
    return status


def proof_was_there_before(
    check: dict[str, Any],
    start_text: str,
    start_url: str,
    calls: list[tuple[str, str, int]] | None = None,
) -> bool:
    value = str(check.get("value") or "").strip().lower()
    if not value:
        return True
    if check.get("kind") == "api_call":
        # Only calls made after the test started are counted — and one the
        # app makes on many steps (saving progress on every Continue) can't
        # tell this test's outcome apart: the steps before it make it too.
        return api_call_count(calls or [], str(check.get("value"))) > 1
    if check.get("kind") == "url_contains":
        return value in start_url.lower()
    return " ".join(value.split()) in " ".join(start_text.lower().split())


def _steps(test_id: uuid.UUID) -> list[str]:
    with Session(engine) as session:
        test = session.get(ExplorerTestCase, test_id)
        return list(test.steps) if test else []


# A screen Explorer failed to carry out this many scenarios on, with none
# working there yet, is one it can't reliably reach: the rest are left out
# instead of each costing minutes (and a second try) to fail the same way.
GIVE_UP_AFTER = 3
_FELL_SHORT = "Couldn't carry it out far enough"


def should_give_up(statuses: list[tuple[str, str | None]]) -> bool:
    """(status, drop reason) of a screen's finished scenarios."""
    worked = any(status in ("proven", "known_bug") for status, _ in statuses)
    fell_short = sum(1 for _, reason in statuses if (reason or "").startswith(_FELL_SHORT))
    return not worked and fell_short >= GIVE_UP_AFTER


def give_up_on_screen(journal: Journal, screen: str | None) -> None:
    if not screen:
        return
    with Session(engine) as session:
        rows = session.exec(
            select(ExplorerTestCase).where(
                ExplorerTestCase.run_id == journal.run_id, ExplorerTestCase.start_screen == screen
            )
        ).all()
        if not should_give_up([(r.status, r.drop_reason) for r in rows]):
            return
        waiting = [r for r in rows if r.status == "planned"]
        for row in waiting:
            row.status, row.finished_at = "dropped", datetime.now(UTC)
            row.drop_reason = (
                f"Left out: {GIVE_UP_AFTER} scenarios on {screen} couldn't be carried out and "
                "none worked there, so Explorer couldn't reliably reach this screen"
            )
            session.add(row)
        session.commit()
    if waiting:
        journal.event(
            "thought",
            f"Left out {len(waiting)} more scenario(s) on {screen}",
            f"{GIVE_UP_AFTER} scenarios there couldn't be carried out and none worked, so the "
            "rest would most likely fail the same way.",
        )


def finish_testing(run_id: uuid.UUID) -> None:
    journal = Journal(run_id)
    # paused: Resume carries on, so leave the queue as it is. failed (test
    # planning crashed): keep the error showing, never paper over it as "tested".
    if journal.status() in ("stopped", "paused", "failed"):
        return
    with Session(engine) as session:
        tests = session.exec(
            select(ExplorerTestCase).where(ExplorerTestCase.run_id == run_id)
        ).all()
    # Loop guard: a test whose worker died twice never finished; it must not
    # show "Trying it" forever.
    with Session(engine) as session:
        for t in session.exec(
            select(ExplorerTestCase).where(
                ExplorerTestCase.run_id == run_id,
                col(ExplorerTestCase.status).in_(("planned", "building")),
            )
        ).all():
            t.status, t.drop_reason = "dropped", "Couldn't finish trying it"
            session.add(t)
        session.commit()
        tests = session.exec(
            select(ExplorerTestCase).where(ExplorerTestCase.run_id == run_id)
        ).all()
    proven = sum(1 for t in tests if t.status == "proven")
    bugs = sum(1 for t in tests if t.status == "known_bug")
    dropped = sum(1 for t in tests if t.status == "dropped")
    journal.update_run(status="tested", headline=f"Done: {proven + bugs} scenarios ready")
    journal.event(
        "summary",
        "Scenarios ready",
        f"{proven + bugs} scenarios are ready ({bugs} of them show a possible bug). "
        f"{dropped} idea(s) were left out (they didn't hold up in the app, or weren't needed). "
        "Next: open Scenarios and press “Generate tests”.",
    )


CUT_OFF_ONCE = "Cut off once"


def requeue_test(test_id: uuid.UUID) -> None:
    """A test whose worker died mid-build goes back to planned — once. Cut
    off again, it is given up, so a one-at-a-time queue never waits on a
    test nobody is building (loop guard)."""
    with Session(engine) as session:
        test = session.get(ExplorerTestCase, test_id)
        if test is not None and test.status == "building":
            if test.drop_reason == CUT_OFF_ONCE:
                test.status, test.drop_reason = "dropped", "Couldn't finish trying it"
            else:
                test.status, test.drop_reason = "planned", CUT_OFF_ONCE
            session.add(test)
            session.commit()


def _progress(run_id: uuid.UUID) -> tuple[int, int]:
    """(scenarios finished, scenarios in total) for the log's "3 of 12"."""
    with Session(engine) as session:
        rows = session.exec(
            select(ExplorerTestCase.status).where(ExplorerTestCase.run_id == run_id)
        ).all()
    total = len(rows)
    finished = sum(1 for status in rows if status in ("proven", "known_bug", "dropped"))
    return finished, total


def _round_robin(items: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    """One of each group in turn, keeping the order inside each group."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        groups.setdefault(str(item.get(field) or ""), []).append(item)
    queues, out = list(groups.values()), []
    while any(queues):
        for queue in queues:
            if queue:
                out.append(queue.pop(0))
    return out


def left_out(planned: list[dict[str, Any]], verdicts: list[dict[str, Any]]) -> dict[int, str]:
    """The review's verdicts (brain.review_plan) -> {index: reason}. Only a
    duplicate of an EARLIER scenario that is kept, or a flow never seen; a
    review that would leave out more than a third of the plan is ignored
    (something went wrong, and coverage matters more than time)."""
    out: dict[int, str] = {}
    for verdict in verdicts:
        index, of = verdict.get("index"), verdict.get("of")
        if not isinstance(index, int) or not 0 <= index < len(planned) or index in out:
            continue
        if verdict.get("why") == "duplicate":
            if isinstance(of, int) and 0 <= of < index and of not in out:
                title = str(planned[of].get("title") or "")
                out[index] = f"Left out before trying: the same check as “{title}”"
        elif verdict.get("why") == "never_seen":
            reason = str(verdict.get("reason") or "").strip()
            out[index] = (
                "Left out before trying: it needs something exploring never saw"
                + (f" — {reason}" if reason else "")
            )[:400]
    return out if len(out) * 3 <= len(planned) else {}


def balanced(planned: list[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
    """Up to `cap` scenarios, taking each screen in turn and, within a
    screen, each kind of check in turn — so a cap never silently drops a
    whole screen or kind; the planner's order is kept inside each. The
    checklist items come before Explorer's own extras ("X-..."), so a cap
    trims extras first."""

    def is_extra(t: dict[str, Any]) -> bool:
        return str(t.get("coverage") or "").upper().startswith("X")

    checklist = [t for t in planned if not is_extra(t)]
    extras = [t for t in planned if is_extra(t)]
    ordered = _round_robin(_round_robin(checklist, "kind"), "start_screen")
    return (ordered + _round_robin(extras, "start_screen"))[:cap]
