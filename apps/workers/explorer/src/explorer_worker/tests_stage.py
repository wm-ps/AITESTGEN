"""Stage 5 — proven test cases in 5 kinds (PLAN.md §6).

1. Plan: the model proposes tests grounded in what Explorer actually saw;
   tests naming screens it never saw are dropped.
2. Build: carry the test out in a browser, recording the exact actions, and
   pick a real on-screen proof (a message, a heading, an address).
3. Prove: replay the recorded actions 3 times (no model) — the proof must
   hold every time — then once with the decisive step removed, where it
   must NOT hold. Anything else is dropped with the reason.
4. Trust: when the app does something different from what should happen,
   the test is kept as a Known bug, never as correct behaviour (§4).
"""

import asyncio
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
from explorer_worker.journal import Journal
from explorer_worker.mind import Mind
from explorer_worker.missions import fast_forward, one_at_a_time
from explorer_worker.pursue import pursue
from explorer_worker.sense import same_place
from explorer_worker.session import (
    Target,
    load_target,
    needs_sign_in,
    open_signed_in,
    open_signed_out,
)
from explorer_worker.testkit import holds, playwright_code, replay, without_decisive_step

MAX_TESTS = 150
SCREENS_PER_PLAN = 3


def test_cap(screen_count: int) -> int:
    """Scenarios worth proving for an app this size (each one is proven by
    several full replays): enough for every checklist item a screen has, 10 to MAX_TESTS."""
    return max(10, min(MAX_TESTS, 15 * screen_count))


PROOF_RUNS = 3

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

    async def take_in(self, visit: Visit, reached_by: str | None, action: str | None = None) -> str:
        self.heartbeat()
        headings = visit.inventory.get("headings") or []
        name = str(headings[0] if headings else visit.inventory.get("title") or "screen")[:80]
        self.journal.event("thought", f"On {name}", None, self.journal.shot(visit.shot))
        return name


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
    may_save = load_target(run_id).non_production

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
                sign_in=index == 0,
            )

    parts = await asyncio.gather(
        *(plan_part(i, c) for i, c in enumerate(chunks or [[]])), return_exceptions=True
    )
    planned = [t for part in parts if isinstance(part, list) for t in part]
    known = {s["name"] for s in screen_info}
    kept = 0
    with Session(engine) as session:
        for t in balanced(planned, test_cap(len(screen_info))):
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
                    status="planned" if grounded else "dropped",
                    drop_reason=None if grounded else "Refers to a screen Explorer never saw",
                )
            )
            kept += grounded
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
        for _ in range(PROOF_RUNS):
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
    tag = "@auth" if needs_sign_in(target.auth_method, target.secret_ref) else "@public"
    status = "known_bug" if failing else "proven"
    _update(
        test_id,
        status=status,
        observed=(failing or "Fine on every run")[:1000],
        script=[{"do": "goto", "url": url}],
        evidence_shot_id=shot_id,
        proof_runs=PROOF_RUNS,
        proof_passes=PROOF_RUNS,
        catches_breakage=True,
        code=quality.playwright_code(title, name, url, tag, failing),
        finished_at=datetime.now(UTC),
    )
    journal.event(
        "summary",
        f"{'Possible bug' if failing else 'Scenario ready'}: {title}",
        (f"Every run found: {failing}" if failing else f"Fine on all {PROOF_RUNS} runs.")[:600],
        shot_id,
    )
    return status


def _text(value: object) -> str | None:
    return str(value)[:300] if value else None


def planned_tests(run_id: uuid.UUID) -> list[str]:
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None or run.status in ("stopped", "paused"):
            return []
        rows = [
            str(r)
            for r in session.exec(
                select(ExplorerTestCase.id)
                .where(ExplorerTestCase.run_id == run_id, ExplorerTestCase.status == "planned")
                .order_by(col(ExplorerTestCase.created_at))
            ).all()
        ]
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
        f"First I try it once, then replay it {PROOF_RUNS} times to prove it works the same way. "
        + (meta.get("how_to_run") or ""),
    )

    # 1) Build: do it once with the model, recording exact actions.
    eyes = await open_signed_out(target) if signed_out else await open_signed_in(target, journal)
    if eyes is None:
        return drop(journal, test_id, title, "Couldn't sign in")
    # Every test starts where sign-in lands and opens its screen itself, the
    # way a user gets there. Starting on the screen made every check of what
    # it shows (data, empty states, refresh) "already on screen before the
    # test acted", and left the broken-run check only trivial steps to remove.
    # ponytail: a screen that IS the sign-in landing page still can't be
    # proven this way; reloading it isn't an act.
    opens_itself = not stateful and not signed_out
    how_to_run = (
        (f"First open {start_screen}. " if opens_itself else "")
        + (SIGN_IN_RULES if signed_out else "")
        + (meta.get("how_to_run") or "")
        + (
            f" Last time this did not get far enough: {meta['lesson']} Do it differently this time."
            if meta.get("lesson")
            else ""
        )
    )
    try:
        if not opens_itself:
            await eyes.goto(start_url)
        lead_in = (
            await fast_forward(eyes, journal, run_id, start_screen)
            if stateful and not signed_out
            else None
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
        result = await pursue(
            eyes,
            QuietMind(journal, target.notes, heartbeat),
            journal,
            f"Test “{title}” — {how_to_run or expected}",
            target.notes,
            heartbeat,
            instructions=how_to_run
            + " Carry out every step above first (enter the values, press the buttons, reopen"
            " the record when asked); stop (done) only once the outcome is visible on screen.",
            # Checklist items such as "save, reopen, compare" take more steps.
            max_steps=24 if stateful and not lead_in else 20,
            non_production=target.non_production,
            lead_in=lead_in,
            # Lets "open its address directly" tests do exactly that.
            known_screens=dict(known),
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
            if not check or not proof_was_there_before(check, start_text, start_url_now):
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
        if (half_done or set_up_failed) and not meta.get("lesson"):
            # One more try with what went wrong; the lesson makes it the last.
            _update(
                test_id,
                status="planned",
                script=[{**meta, "lesson": (observed or "it stopped early")[:400]}],
            )
            journal.event("thought", f"Trying again differently: {title}", observed or None)
            return "retry"
        if half_done:
            return drop(
                journal, test_id, title, f"Couldn't carry it out far enough: {observed}"[:400]
            )
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
    if signed_out:
        # The address it opened, not the sign-in page it may have bounced to.
        # Marked so the hand-off knows this test runs without the shared login.
        script = [{"do": "goto", "url": start_url, "signed_out": True}, *script[1:]]
    home_script = [{"do": "goto", "url": target.app_url}]
    broken = without_decisive_step(script)
    if broken == script:
        broken = home_script

    # 2) Prove: replay without the model, recorded as the proof video.
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
            if signed_out:
                await eyes.forget_session()
            await replay(eyes, broken)
            catches = not await holds(eyes, check)
            journal.event(
                "action",
                "Broken-on-purpose check: "
                + ("the test caught it" if catches else "the test did not notice"),
                "Replayed without its key step, to make sure the test fails when the app misbehaves.",
            )
        finally:
            video = await eyes.close()
            if video and Path(video).exists():
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
    if not catches:
        return drop(
            journal,
            test_id,
            title,
            "Still passed with its key step removed, so it wouldn't catch a real problem",
        )
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
            if not signed_out and needs_sign_in(target.auth_method, target.secret_ref)
            else "@public",
        ),
        finished_at=datetime.now(UTC),
    )
    journal.event(
        "summary",
        f"{'Scenario ready' if matches else 'Possible bug'}: {title}",
        (
            f"Worked the same way {PROOF_RUNS} times. It passes when the screen shows “{check['value']}”."
            if matches
            else f"Should: {expected} — the app instead: {observed}"
        )[:600],
        shot_id,
    )
    return status


def proof_was_there_before(check: dict[str, Any], start_text: str, start_url: str) -> bool:
    value = str(check.get("value") or "").strip().lower()
    if not value:
        return True
    if check.get("kind") == "api_call":
        return False  # only calls made after the test started are counted
    if check.get("kind") == "url_contains":
        return value in start_url.lower()
    return " ".join(value.split()) in " ".join(start_text.lower().split())


def _steps(test_id: uuid.UUID) -> list[str]:
    with Session(engine) as session:
        test = session.get(ExplorerTestCase, test_id)
        return list(test.steps) if test else []


def finish_testing(run_id: uuid.UUID) -> None:
    journal = Journal(run_id)
    if journal.status() in ("stopped", "paused"):
        return  # paused: Resume carries on, so leave the queue as it is
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
