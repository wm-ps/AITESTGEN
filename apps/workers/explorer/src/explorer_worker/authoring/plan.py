"""Missions and scenarios for exactly the user's request — the authoring
counterpart of missions.plan_missions and tests_stage.plan_tests. Explorer
walks only the request's flow, and writes only the scenarios asked for (or,
for a flow alone, the flow and its positive and negative edge cases)."""

import asyncio
import json
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from explorer_core import (
    TEST_KINDS,
    ExplorerMission,
    ExplorerQuestion,
    ExplorerRun,
    ExplorerScreen,
    ExplorerTestCase,
    ExplorerTransition,
)
from sqlmodel import Session, col, select

from explorer_worker import brain, missions, scope
from explorer_worker.db import engine
from explorer_worker.field_checks import CODE_LIMITS, field_checks
from explorer_worker.goal import ensure_scope, screens_in_goal
from explorer_worker.journal import Journal
from explorer_worker.llm import THINKING_MODEL, ask_json
from explorer_worker.memory import ask
from explorer_worker.session import load_target
from explorer_worker.tests_stage import (
    SCREENS_PER_PLAN,
    SIGN_IN_RULES,
    approved_presses,
    left_out,
)

# Marks the missions planned for the request: the authoring pool runs these
# (and any the user adds), never Explorer's automatic follow-ups.
REQUEST_MISSION = "Your request"
NOT_ASKED = "Not part of your request"
# A scenario becomes a test case only when its try in the app got through:
# proven, or it showed a possible bug. A dropped one (never carried out, or no
# proof found) has no checked code and would only fail when run.
ADDED = ("proven", "known_bug")


def _request(brief: dict[str, Any], prompt: str) -> dict[str, Any]:
    return brief.get("request") or {"flow": prompt, "scenarios": []}


# --- Missions ----------------------------------------------------------------


def understood(prompt: str, request: dict[str, Any]) -> str:
    """The request as understood — its steps in order and what to check —
    with the user's own words as context. Just the prompt when the reading
    found no steps."""
    steps = [str(s) for s in request.get("steps") or [] if str(s).strip()]
    if not steps:
        return prompt
    checks = [str(c) for c in request.get("checks") or [] if str(c).strip()]
    return (
        "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
        + ("\nCheck: " + "; ".join(checks) if checks else "")
        + f"\n(The user's words, for context: {prompt})"
    )


def request_mission(prompt: str, request: dict[str, Any]) -> dict[str, Any]:
    """The walk is the request as understood: Explorer carries out its steps
    from the app's home screen, once, and nothing else."""
    return {
        "title": str(request.get("title") or prompt)[:200],
        "goal": str(request.get("flow") or prompt)[:1000],
        "instructions": (
            "Follow the user's request exactly, step by step, in this order. Do not explore "
            "anything else, and stop when the request ends:\n" + understood(prompt, request)
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


def planned_tests(run_id: uuid.UUID) -> list[str]:
    """Like tests_stage.planned_tests, but always one at a time: a request's
    scenarios act on the same things (one account, one chat, one record), and
    tried in parallel they spoil each other (seen: three scenarios sending to
    one AI chat at once)."""
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None or run.status in ("stopped", "paused"):
            return []
        busy = session.exec(
            select(ExplorerTestCase.id).where(
                ExplorerTestCase.run_id == run_id, ExplorerTestCase.status == "building"
            )
        ).first()
        if busy is not None:
            return []
        first = session.exec(
            select(ExplorerTestCase.id)
            .where(ExplorerTestCase.run_id == run_id, ExplorerTestCase.status == "planned")
            .order_by(col(ExplorerTestCase.created_at))
        ).first()
    return [str(first)] if first else []


def say_done(run_id: uuid.UUID) -> None:
    """The last word of an authoring run: where its test cases are (Explorer's
    own closing line points at "Generate tests", already done here)."""
    with Session(engine) as session:
        statuses = session.exec(
            select(ExplorerTestCase.status).where(
                ExplorerTestCase.run_id == run_id,
                col(ExplorerTestCase.status).in_(ADDED),
            )
        ).all()
    if statuses:
        confirmed = statuses.count("proven")
        Journal(run_id).event(
            "summary",
            f"{len(statuses)} test case(s) ready",
            f"{confirmed} worked when tried in the app; the rest showed a possible bug. "
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
main scenario — the request as the user meant it — is already written. Now write the \
OTHER scenarios worth testing on that flow, positive and negative, on the screens the \
flow goes through: its fields (required, invalid format, boundaries, wrong or unknown \
values), its choices, its lists and searches (a match, no match), its buttons \
(cancel/back), and completing the whole form or task. One rule each.
- Write exactly as many as you are told; when no number is given, every scenario the \
requirement calls for. Follow any limit the user gave (e.g. positive only).
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


# No number given: every scenario the requirement calls for, up to this many.
# ponytail: a safety cap (each scenario is tried in the app, ~1 min each);
# raise it if a flow's screens need more.
CEILING = 60


# --- Clarity -----------------------------------------------------------------

UNCLEAR = "Stopped: your request isn't clear"
# How long a question about the user's own scenarios waits for an answer.
CLARIFY_MINUTES = 30

_CLARITY_SYSTEM = (
    brain.STANCE
    + """

The user listed the test scenarios they want. Explorer has walked the app. Check each \
scenario against the screens Explorer saw. A scenario is UNCLEAR only when it names a \
page, field, button, option or value that is on none of the screens (and nothing close \
to it is), contradicts what the app has, or can't be understood. A scenario that can be \
carried out on these screens is clear, even if worded loosely — never ask about those, \
and never ask what the app will show.
Reply with ONLY:
{"unclear": [{"index": 1, "question": "one short question to the user naming what is \
unclear and what Explorer did find, e.g. 'There is no Discount field on New Order; it \
has Price and Quantity. Which field did you mean?'", "why": "one short line"}]}
'index' is the scenario's number in the list (1 = first). [] when every scenario is clear."""
)


async def wait_for_answer(journal: Journal, question: str, why: str) -> str | None:
    """Ask in the Questions tab and wait up to CLARIFY_MINUTES; None when
    it goes unanswered, is dismissed or the run is stopped."""
    earlier = await ask(journal, "data", question, why, [], None, lambda: None, wait=False)
    if earlier:
        return earlier
    for _ in range(CLARIFY_MINUTES * 12):
        await asyncio.sleep(5)
        with Session(engine) as session:
            row = session.exec(
                select(ExplorerQuestion).where(
                    ExplorerQuestion.run_id == journal.run_id,
                    ExplorerQuestion.question == question[:600],
                )
            ).first()
        if row is None or row.status == "dismissed" or journal.status() == "stopped":
            return None
        if row.status == "answered":
            return row.answer
    return None


async def clarify_scenarios(
    journal: Journal, request: dict[str, Any], screen_info: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The user's own scenarios, checked against the screens seen: one that
    names something the app doesn't have is asked about, and the answer goes
    into that scenario. None = a question went unanswered (the run stops)."""
    scenarios = [str(x) for x in request.get("scenarios") or []]
    reply = await ask_json(
        _CLARITY_SYSTEM,
        f"The user's scenarios: {json.dumps(scenarios, ensure_ascii=False)}\n"
        f"Known screens: {json.dumps(screen_info, ensure_ascii=False)[:40000]}",
        model=THINKING_MODEL,
    )
    for item in (reply.get("unclear") or [])[:3]:
        if not isinstance(item, dict) or not item.get("question"):
            continue
        index = item.get("index")
        if not isinstance(index, int) or not 1 <= index <= len(scenarios):
            continue
        answer = await wait_for_answer(
            journal, str(item["question"]), f"About your scenario: {scenarios[index - 1]}"
        )
        if not answer:
            stop_unclear(journal.run_id)
            return None
        scenarios[index - 1] += f" (You answered: {answer})"
    return {**request, "scenarios": scenarios}


def stop_unclear(run_id: uuid.UUID) -> str:
    """End the run plainly: a question about the request went unanswered,
    so no test cases were guessed."""
    journal = Journal(run_id)
    status = journal.status()
    if status in ("stopped", "failed", "expired"):
        return status or "gone"
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        asked = [
            str(q.get("question"))
            for q in ((run.brief or {}).get("questions_for_you") or [] if run else [])
            if isinstance(q, dict)
        ] + [
            q.question
            for q in session.exec(
                select(ExplorerQuestion).where(
                    ExplorerQuestion.run_id == run_id, ExplorerQuestion.status == "open"
                )
            ).all()
        ]
    reason = (
        "Explorer asked about your request and got no answer, so it wrote no test cases "
        "rather than guess."
        + (f" Unanswered: {' | '.join(asked)}." if asked else "")
        + " Start a new run with the missing details in the request."
    )
    journal.event("error", UNCLEAR, reason)
    journal.update_run(status="failed", headline=UNCLEAR, error=reason[:300])
    return "failed"


def names_screen(name: str, prompt: str, brief: dict[str, Any]) -> bool:
    """Does the request name this screen? Every word of its name (4+
    letters) appears in the request or how it was read.
    ponytail: word match; a model call if pass-through pages still slip in."""
    asked = f"{prompt} {json.dumps(brief.get('request') or {}, ensure_ascii=False)}".lower()
    words = re.findall(r"[a-z]{4,}", name.lower())
    return bool(words) and all(w in asked for w in words)


def wants_full_scope(request: dict[str, Any]) -> bool:
    """The user named a flow but no tests of their own, no number and no
    limit: its screens get the whole scope Explorer covers (every field rule
    plus the list/form/element checklist). Anything the user specified is
    followed exactly instead."""
    return not (
        request.get("scenarios") or isinstance(request.get("count"), int) or request.get("only")
    )


async def _scope_scenarios(
    brief: dict[str, Any],
    screen_info: list[dict[str, Any]],
    links: list[str],
    walked: list[dict[str, Any]],
    notes: str | None,
    *,
    may_save: bool,
    approved: list[str],
) -> list[dict[str, Any]]:
    """Explorer's own scope for the flow's screens (tests_stage.plan_tests):
    a test per field rule, the checklist a few screens per model call, and
    one review that drops duplicates."""
    names = [str(s["name"]) for s in screen_info]
    chunks = [names[i : i + SCREENS_PER_PLAN] for i in range(0, len(names), SCREENS_PER_PLAN)]
    parts = await asyncio.gather(
        *(
            brain.plan_tests(
                brief,
                screen_info,
                links,
                walked,
                [],
                notes,
                may_save=may_save,
                approved=approved,
                only=chunk,
                sign_in=False,
            )
            for chunk in chunks
        ),
        return_exceptions=True,
    )
    planned = field_checks(screen_info) + [
        t for part in parts if isinstance(part, list) for t in part
    ]
    try:
        verdicts = await brain.review_plan(planned, screen_info, links, walked)
    except Exception:  # noqa: BLE001 — the review only saves time; never block planning
        verdicts = []
    skipped = left_out(planned, verdicts)
    return [t for i, t in enumerate(planned) if i not in skipped]


async def _gap_scenarios(user: str, missing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One scenario per scope item the plan still misses."""
    reply = await ask_json(
        _TESTS_SYSTEM, scope.gaps_text(missing) + "\n" + user, model=THINKING_MODEL
    )
    return [
        t for t in reply.get("tests") or [] if isinstance(t, dict) and t.get("kind") != "journey"
    ]


async def cover_scope(
    journal: Journal,
    user: str,
    brief: dict[str, Any],
    screen_info: list[dict[str, Any]],
    links: list[str],
    walked: list[dict[str, Any]],
    notes: str | None,
    *,
    may_save: bool,
    approved: list[str],
    shots: dict[str, bytes] | None = None,
) -> list[dict[str, Any]]:
    """The flow's whole scope: write it, then the shared scope check
    (scope.cover) — what is missing is written and checked again."""
    tests = await _scope_scenarios(
        brief, screen_info, links, walked, notes, may_save=may_save, approved=approved
    )
    return await scope.cover(
        journal,
        screen_info,
        tests,
        lambda missing: _gap_scenarios(user, missing),
        shots,
        CEILING,
    )


def more_wanted(request: dict[str, Any]) -> int:
    """How many scenarios beyond the main ones (the listed scenarios, or the
    flow itself): the number asked for minus those; none when the user listed
    scenarios without a number; else as many as the requirement needs."""
    count = request.get("count")
    main = len(request.get("scenarios") or []) or 1
    if isinstance(count, int):
        return max(0, count - main)
    return 0 if request.get("scenarios") else CEILING


def flow_screens(
    screens: Sequence[ExplorerScreen],
    end: str | None,
    home: str | None,
    prompt: str,
    brief: dict[str, Any],
) -> list[ExplorerScreen]:
    """The screens a flow's scope covers: the walk's end screen and those
    found after it. No end (the flow is on the home screen): all but the
    home screen, unless the request names it."""
    ended = next((s for s in screens if s.name == end), None)
    if ended is not None:
        return [s for s in screens if s.created_at >= ended.created_at]
    return [
        s for s in screens if s.name != home or names_screen(s.name, prompt, brief)
    ] or list(screens)


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
    count = request.get("count")
    if isinstance(count, int):
        asked = asked[:count]  # more listed than asked for: the first ones
    # Listed scenarios stay word for word; a flow alone is its understood steps.
    texts = asked or [understood(prompt, request)]
    steps = [str(s)[:500] for s in request.get("steps") or [] if str(s).strip()]
    checks = "; ".join(str(c) for c in request.get("checks") or [] if str(c).strip())
    return [
        {
            "kind": "journey",
            "title": (str(request.get("title") or "") if not asked else text)[:200] or text[:200],
            "purpose": "Your request." if not asked else "Your request, exactly as you wrote it.",
            "technique": "happy path",
            "start_screen": start,
            "steps": steps if not asked and steps else [text[:500]],
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
            "expected": "Everything this asks to check is true: "
            + (checks if not asked and checks else text)
            + proof_hint(text),
            "rule": (checks if not asked and checks else text)[:500],
        }
        for text in texts
    ]


async def _other_scenarios(
    user: str, limit: str, more: int, *, exact: bool
) -> list[dict[str, Any]]:
    """The scenarios beyond the main ones. With a number asked for, exactly
    that many: a short reply is asked once more for the rest."""
    found: list[dict[str, Any]] = []
    for _ in range(2 if exact else 1):
        wanted = more - len(found)
        how_many = (
            f"Write exactly {wanted} more scenario(s).\n"
            if exact
            else f"Write every other scenario the requirement calls for (at most {more}).\n"
        )
        written = (
            "Already written, never repeat them: "
            + json.dumps([t.get("title") for t in found], ensure_ascii=False)
            + "\n"
            if found
            else ""
        )
        reply = await ask_json(
            _TESTS_SYSTEM, how_many + limit + written + user, model=THINKING_MODEL
        )
        found += [
            t
            for t in reply.get("tests") or []
            if isinstance(t, dict) and t.get("kind") != "journey"
        ]
        if len(found) >= more:
            break
    return found[:more]


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
                "business_thing": s.entity,
                "kind": s.view_kind,
                "purpose": s.purpose,
                "fields": [
                    {
                        "label": f.get("label"),
                        "type": f.get("type"),
                        "required": f.get("required"),
                        "notes": f.get("notes"),
                        # The page code's limits and the form's own messages
                        # (field_probe): what the field-rule tests check.
                        **{k: f[k] for k in CODE_LIMITS if f.get(k)},
                        **({"messages": f["messages"]} if f.get("messages") else {}),
                    }
                    for f in s.fields
                ][:40],
                "buttons": [a.get("label") for a in s.actions][:20],
            }
            for s in screens
        ]
        # The scope is the request's own screens: where the walk ended (the
        # flow, e.g. the New account form) and what came after. The screens it
        # only passed through to get there (a dashboard, the list holding the
        # New button) are the route, not what was asked to be tested.
        in_scope = flow_screens(screens, walk_end(all_screens), home, prompt, brief)
        scope_info = [i for i, s in zip(screen_info, screens, strict=True) if s in in_scope]
        scope_shots = scope.screen_shots(session, in_scope)
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
    if request.get("scenarios"):  # the user's own scenarios: anything unclear is asked
        clarified = await clarify_scenarios(journal, request, screen_info)
        if clarified is None:
            return 0
        request = clarified
    flow_start = home if request.get("scenarios") else (walk_end(all_screens) or home)
    planned = request_scenarios(prompt, request, flow_start, home)
    more = more_wanted(request)
    if wants_full_scope(request):  # a flow alone: its whole scope
        planned += await cover_scope(
            journal,
            user,
            brief,
            scope_info,
            links,
            walked,
            target.notes,
            may_save=target.non_production,
            approved=approved,
            shots=scope_shots,
        )
    elif more:  # what the user specified: their number, list or limit
        limit = f"The user's limit: {request['only']}\n" if request.get("only") else ""
        planned += await _other_scenarios(
            user, limit, more, exact=isinstance(request.get("count"), int)
        )
    known = {s["name"] for s in screen_info}
    kept = 0
    with Session(engine) as session:
        for t in planned:
            kind = str(t.get("kind") or "")
            if kind not in (*TEST_KINDS, "journey") or not t.get("title") or not t.get("expected"):
                continue
            start = str(t.get("start_screen") or "")
            if start not in known and start != home and not t.get("signed_out"):
                # A screen the walk never named: start where the flow does, so
                # the scenario is still written (the count asked for holds).
                start = (home if kind == "journey" else flow_start) or start
            grounded = bool(start)
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
                            "coverage": str(t.get("coverage") or "X-Your request")[:100],
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
