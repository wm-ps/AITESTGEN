"""Missions and scenarios for exactly the user's request — the authoring
counterpart of missions.plan_missions and tests_stage.plan_tests. Explorer
walks only the request's flow, and writes only the scenarios asked for (or,
for a flow alone, the flow and its positive and negative edge cases)."""

import json
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from explorer_core import (
    TEST_KINDS,
    ExplorerMission,
    ExplorerRun,
    ExplorerScreen,
    ExplorerTestCase,
    ExplorerTransition,
)
from sqlmodel import Session, col, select

from explorer_worker import brain, missions
from explorer_worker.db import engine
from explorer_worker.goal import ensure_scope, screens_in_goal
from explorer_worker.journal import Journal
from explorer_worker.llm import THINKING_MODEL, ask_json
from explorer_worker.session import load_target
from explorer_worker.tests_stage import SIGN_IN_RULES, approved_presses

# Marks the missions planned for the request: the authoring pool runs these
# (and any the user adds), never Explorer's automatic follow-ups.
REQUEST_MISSION = "Your request"
NOT_ASKED = "Not part of your request"


def _request(brief: dict[str, Any], prompt: str) -> dict[str, Any]:
    return brief.get("request") or {"flow": prompt, "scenarios": []}


# --- Missions ----------------------------------------------------------------


def request_mission(prompt: str, request: dict[str, Any]) -> dict[str, Any]:
    """The walk is the request itself, word for word: Explorer carries out the
    user's steps from the app's home screen, once, and nothing else."""
    return {
        "title": str(request.get("title") or prompt)[:200],
        "goal": str(request.get("flow") or prompt)[:1000],
        "instructions": (
            "Follow the user's request exactly, step by step, in this order. Do not explore "
            "anything else, and stop when the request ends:\n" + prompt
        )[:4000],
        # "custom" is walked once (a "task" is walked again to find other screens).
        "kind": "custom",
        "why": REQUEST_MISSION,
        "priority": 5,
    }


async def plan_missions(run_id: uuid.UUID) -> int:
    journal = Journal(run_id)
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None or run.status in ("stopped", "paused"):
            return 0
        prompt = run.prompt or ""
        mission = request_mission(prompt, _request(run.brief or {}, prompt))
        session.add(ExplorerMission(run_id=run_id, **mission))
        session.commit()
    journal.update_run(status="exploring", headline=f"Following your request: {mission['title']}")
    journal.event("phase", "Following your request, step by step", prompt[:1000])
    return 1


def _text(value: object) -> str | None:
    return str(value)[:1000] if value else None


def queued_missions(run_id: uuid.UUID) -> list[str]:
    """Like missions.queued_missions, but only the request's missions and the
    ones the user added — Explorer's automatic follow-ups stay unrun."""
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None or run.status in ("stopped", "paused"):
            return []
        rows = [
            str(r)
            for r in session.exec(
                select(ExplorerMission.id)
                .where(
                    ExplorerMission.run_id == run_id,
                    ExplorerMission.status == "queued",
                    (col(ExplorerMission.why) == REQUEST_MISSION)
                    | (col(ExplorerMission.added_by) == "user"),
                )
                .order_by(col(ExplorerMission.priority).desc(), col(ExplorerMission.created_at))
            ).all()
        ]
        if not missions.one_at_a_time(session, run_id):
            return rows
        busy = session.exec(
            select(ExplorerMission.id).where(
                ExplorerMission.run_id == run_id,
                col(ExplorerMission.status).in_(("running", "waiting")),
                col(ExplorerMission.started_at) > datetime.now(UTC) - timedelta(minutes=45),
            )
        ).first()
        return [] if busy is not None else rows[:1]


BLANK_RETRIES = 2
NOTHING_SEEN = (
    "The app only showed a blank page, so I couldn't follow your request. Check that the "
    "app opens normally in a browser, then author again."
)


def retry_if_nothing_seen(run_id: uuid.UUID) -> bool:
    """The walk saw no screen at all (the app showed a blank page — seen when
    it fails to load): walk the request again, up to BLANK_RETRIES times."""
    journal = Journal(run_id)
    if journal.status() in ("stopped", "paused") or journal.screen_rows():
        return False
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None:
            return False
        insights = dict(run.insights or {})
        tries = int(insights.get("blank_retries") or 0)
        if tries >= BLANK_RETRIES:
            return False
        insights["blank_retries"] = tries + 1
        run.insights = insights
        session.add(run)
        for m in session.exec(
            select(ExplorerMission).where(
                ExplorerMission.run_id == run_id, ExplorerMission.why == REQUEST_MISSION
            )
        ).all():
            m.status, m.outcome, m.started_at, m.finished_at = "queued", None, None, None
            session.add(m)
        session.commit()
    journal.event(
        "thought",
        f"The app showed a blank page — trying again ({tries + 2} of {BLANK_RETRIES + 1})",
        "It may still have been loading. Walking your request again.",
    )
    return True


def say_done(run_id: uuid.UUID) -> None:
    """The last word of an authoring run: where its test cases are (Explorer's
    own closing line points at "Generate tests", already done here)."""
    with Session(engine) as session:
        proven = session.exec(
            select(ExplorerTestCase.id).where(
                ExplorerTestCase.run_id == run_id, ExplorerTestCase.status == "proven"
            )
        ).all()
    if proven:
        Journal(run_id).event(
            "summary",
            f"{len(proven)} test case(s) ready",
            "Find them under Test cases → Author test cases.",
        )


def finish_exploring(run_id: uuid.UUID) -> None:
    """Follow-ups Explorer queued on its own were not asked for: say so, then
    finish exploring the way Explorer does."""
    if Journal(run_id).status() not in ("stopped", "paused"):
        with Session(engine) as session:
            for m in session.exec(
                select(ExplorerMission).where(
                    ExplorerMission.run_id == run_id, ExplorerMission.status == "queued"
                )
            ).all():
                if m.why == REQUEST_MISSION or m.added_by == "user":
                    continue
                m.status, m.outcome = "skipped", NOT_ASKED
                session.add(m)
            session.commit()
    missions.finish_exploring(run_id)


# --- Scenarios ---------------------------------------------------------------

_TESTS_SYSTEM = (
    brain.STANCE
    + """

The user asked for test cases with their own request, and Explorer has walked it. The \
main scenario — the request itself, word for word — is already written. Now write the \
OTHER scenarios worth testing on that flow, positive and negative, on the screens the \
flow goes through: its fields (required, invalid format, boundaries, wrong or unknown \
values), its choices, its lists and searches (a match, no match), its buttons \
(cancel/back). One rule each.
- Write exactly as many as you are told; when no number is given, the ones worth \
testing, at most 8. Follow any limit the user gave (e.g. positive only).
- Only screens, fields and buttons the flow's screens actually have; nothing on screens \
the flow does not reach. Never repeat the main scenario.
Every scenario is one of these kinds:
- navigation: links, tabs, Back and Refresh take the user to the right screen.
- validation: a field rule (required, format, range, length) is enforced with a clear message.
- error_state: what the user sees when something goes wrong or there is nothing to show.
- data_load: lists, searches and details show the right information.
- form_submission: completing a form or task works and the result is kept/confirmed.
Reply with ONLY:
{
  "tests": [
    {
      "kind": "navigation | validation | error_state | data_load | form_submission",
      "title": "short and specific",
      "purpose": "one plain line: which part of the request this covers",
      "technique": "e.g. happy path, boundary value, equivalence class, error guessing",
      "business_thing": "e.g. Claim",
      "start_screen": "EXACT name from the known screens list where the scenario begins",
      "signed_out": false,
      "steps": ["plain steps a person would follow"],
      "how_to_run": "precise instructions for the browser agent, with the exact test data",
      "expected": "what SHOULD happen, from the request, the user's answers or common sense",
      "rule": "the rule being tested in plain words"
    }
  ]
}
Rules:
- Only screens, fields and buttons from the known screens; never invent them.
- Use the test data from the request and the user's answers.
- Every scenario is "signed_out": false and never signs in or out, unless the request \
itself asks about signing in. """
    + SIGN_IN_RULES
    + """
- Describe dates relative to today ('tomorrow', '30 days ago'), never fixed dates."""
)


def proof_hint(text: str) -> str:
    """Steer the proof to a value the request names, alone — a proof must sit
    in one element, and "Email: brad.smith@mail.com" (label + value) never
    did, so a walk that worked was dropped for want of a proof."""
    named = list(dict.fromkeys(re.findall(r'["“]([^"”]{2,120})["”]', text)))
    return (
        " Prove it with a value the request names, exactly as the screen shows it and on "
        "its own — never joined with a label in front of it"
        + (f" (e.g. {', '.join(repr(v) for v in named)})." if named else ".")
    )


def more_wanted(request: dict[str, Any]) -> int:
    """How many scenarios beyond the request itself: none when the user listed
    them (exactly those), the number they asked for minus the request itself,
    else up to 8 worth testing on the flow."""
    if request.get("scenarios"):
        return 0
    count = request.get("count")
    return max(0, count - 1) if isinstance(count, int) else 8


def walk_end(screens: Sequence[ExplorerScreen]) -> str | None:
    """The furthest screen the request's walk reached by clicking (the last
    one with a recorded route beyond the home screen)."""
    reached = [s for s in screens if s.route and len(s.route) >= 2]
    return max(reached, key=lambda s: s.created_at).name if reached else None


def request_scenarios(
    prompt: str, request: dict[str, Any], start: str | None, home: str | None = None
) -> list[dict[str, Any]]:
    """The scenarios the user asked for, exactly as written — never reworded by
    the model (a rewording once swapped "pick him from the list" for a search
    box the app ignored). Each starts on `start`: the home screen, or for a
    flow the screen the walk ended on, which the build reaches by replaying
    the walk's recorded clicks (a menu label the model guessed wrong once
    kept a build on the home screen). The test still begins at the app's
    entry: the replayed clicks are its first steps."""
    asked = [str(x) for x in request.get("scenarios") or [] if str(x).strip()]
    texts = asked or [prompt]
    return [
        {
            "kind": "journey",
            "title": (str(request.get("title") or "") if not asked else text)[:200] or text[:200],
            "purpose": "Your request, exactly as you wrote it.",
            "technique": "happy path",
            "start_screen": start,
            "steps": [text[:500]],
            "how_to_run": (
                (
                    f"Start from {start}, reached the way the request says, and carry on from "
                    "there. "
                    if start and home and start != home
                    else ""
                )
                + "Do exactly this, step by step, in this order, the way a user would. Do not "
                "use any other control or path than the one the request describes:\n"
                + text
                + ("" if not asked else f"\n(The full request, for context: {prompt})")
            ),
            "expected": "Everything this asks to check is true: " + text + proof_hint(text),
            "rule": text[:500],
        }
        for text in texts
    ]


async def plan_tests(run_id: uuid.UUID) -> int:
    journal = Journal(run_id)
    await ensure_scope(run_id)
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None or run.status in ("stopped", "paused"):
            return 0
        brief, prompt = run.brief or {}, run.prompt or ""
        all_screens = session.exec(
            select(ExplorerScreen).where(ExplorerScreen.run_id == run_id)
        ).all()
        names = {s.id: s.name for s in all_screens}
        home = min(all_screens, key=lambda s: s.created_at).name if all_screens else None
        skip = set(brief.get("skip_screens") or [])
        screens = [
            s
            for s in screens_in_goal(all_screens)
            if not (s.condition or "").startswith("Simulated") and s.name not in skip
        ]
        links = [
            f"{names.get(t.from_screen_id)} --{t.action}--> {names.get(t.to_screen_id)}"
            for t in session.exec(
                select(ExplorerTransition).where(ExplorerTransition.run_id == run_id)
            ).all()
        ]
        walked = [
            {"title": m.title, "outcome": m.outcome}
            for m in session.exec(
                select(ExplorerMission).where(ExplorerMission.run_id == run_id)
            ).all()
            if m.outcome and m.outcome != NOT_ASKED
        ]
        if not screens:  # nothing to write scenarios about: say why, never "0 ready"
            journal.event("error", "Couldn't follow your request", NOTHING_SEEN)
            journal.update_run(
                status="failed", headline="Couldn't follow your request", error=NOTHING_SEEN
            )
            return 0
        screen_info = [
            {
                "name": s.name,
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
    journal.update_run(status="testing", headline="Writing your scenarios")
    journal.event("phase", "Writing your scenarios", "Turning your request into scenarios to try.")
    target = load_target(run_id)
    approved = sorted(approved_presses(run_id)) if target.non_production else []
    request = _request(brief, prompt)
    user = (
        brain.scope(brief)
        + f"The user's request: {prompt}\n"
        + f"The request read as: {json.dumps(request, ensure_ascii=False)}\n"
        + f"Home screen: {home}\n"
        + (
            "This is a test environment: scenarios may press final Save/Submit buttons, "
            if target.non_production
            else "This is NOT a test environment: scenarios can never press a final Save or "
            "Submit button, "
        )
        + "and never anything that moves money, pays, cancels, deletes or changes a password, "
        "unless listed as approved below.\n"
        + (
            f"The user approved pressing: {json.dumps(approved, ensure_ascii=False)}\n"
            if approved
            else ""
        )
        + f"Confirmed App Summary: {json.dumps(brief, ensure_ascii=False)[:15000]}\n"
        + f"Known screens: {json.dumps(screen_info, ensure_ascii=False)[:40000]}\n"
        + f"Ways between screens: {json.dumps(links, ensure_ascii=False)[:8000]}\n"
        + f"What the walk through the flow found: {json.dumps(walked, ensure_ascii=False)[:8000]}"
    )
    # A flow starts where the walk ended: the build replays the walk's
    # recorded clicks to get there (no model guessing a menu label again).
    start = home if request.get("scenarios") else (walk_end(all_screens) or home)
    planned = request_scenarios(prompt, request, start, home)
    more = more_wanted(request)
    if more:  # a flow alone: plus the other scenarios worth testing on it
        how_many = (
            f"Write exactly {more} more scenario(s).\n"
            if request.get("count")
            else "Write the other scenarios worth testing (at most 8).\n"
        )
        limit = f"The user's limit: {request['only']}\n" if request.get("only") else ""
        reply = await ask_json(_TESTS_SYSTEM, how_many + limit + user, model=THINKING_MODEL)
        others = [t for t in reply.get("tests") or [] if isinstance(t, dict)]
        planned += [t for t in others if t.get("kind") != "journey"][:more]
    known = {s["name"] for s in screen_info}
    kept = 0
    with Session(engine) as session:
        for t in planned:
            kind = str(t.get("kind") or "")
            if kind not in (*TEST_KINDS, "journey") or not t.get("title") or not t.get("expected"):
                continue
            start = str(t.get("start_screen") or "")
            if kind == "journey" and start not in known:
                start = home or start
            grounded = start in known or start == home or bool(t.get("signed_out"))
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
                    trust="confirmed",
                    script=[
                        {
                            "how_to_run": str(t.get("how_to_run") or "")[:4000],
                            "rule": str(t.get("rule") or "")[:500],
                            "coverage": "X-Your request",
                            "linked_to": "",
                            "signed_out": bool(t.get("signed_out")),
                        }
                    ],
                    status="planned" if grounded else "dropped",
                    drop_reason=None if grounded else "Refers to a screen Explorer never saw",
                )
            )
            kept += grounded
        session.commit()
    journal.event(
        "phase",
        f"{kept} scenarios to try",
        "Trying each one in the app now, and proving it works the same way every time.",
    )
    return kept
