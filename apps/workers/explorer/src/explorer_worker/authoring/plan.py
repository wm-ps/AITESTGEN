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
from explorer_worker.field_checks import field_checks
from explorer_worker.goal import ensure_scope, screens_in_goal
from explorer_worker.journal import Journal
from explorer_worker.llm import THINKING_MODEL, ask_json
from explorer_worker.memory import ask
from explorer_worker.session import load_target
from explorer_worker.tests_stage import (
    SCREENS_PER_PLAN,
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
        ready, bugs = statuses.count("proven"), statuses.count("known_bug")
        Journal(run_id).event(
            "summary",
            f"{ready} test case(s) ready"
            + (f", {bugs} possible bug(s) waiting for your answer" if bugs else ""),
            (
                f"{ready} worked when tried in the app: find them under Test cases → Author "
                "test cases. "
                if ready
                else ""
            )
            + (
                f"{bugs} showed a possible bug: answer each on Scenarios — “Not a bug” adds it "
                "to the test cases, “Ignore” removes it."
                if bugs
                else ""
            ),
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
    shots: dict[str, bytes] | None = None,
) -> list[dict[str, Any]]:
    """Explorer's own scope for the flow's screens (tests_stage.plan_tests):
    a test per field rule, the checklist a few screens per model call (each
    with its screenshots), and one review that drops duplicates."""
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
                shots=shots_of(shots, chunk),
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


def shots_of(shots: dict[str, bytes] | None, only: list[str]) -> list[bytes] | None:
    """The screenshots of `only`, in order — all of them or none."""
    images = [shots[n] for n in only if shots and n in shots]
    return images if only and len(images) == len(only) else None


async def cover_scope(
    journal: Journal,
    asked: str,
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
    (scope.cover) — what is missing or not on the page is written again (by
    the same planner, from the same page facts) and checked again. `asked`:
    the user's request, as context for everything written."""
    tests = await _scope_scenarios(
        brief,
        screen_info,
        links,
        walked,
        notes,
        may_save=may_save,
        approved=approved,
        shots=shots,
    )

    async def write(instruction: str, only: list[str]) -> list[dict[str, Any]]:
        return await brain.plan_tests(
            brief,
            screen_info,
            links,
            walked,
            [],
            f"{notes or ''}\n{asked}\n{instruction}",
            may_save=may_save,
            approved=approved,
            only=only,
            sign_in=False,
            shots=shots_of(shots, only),
        )

    return await scope.cover(journal, screen_info, tests, write, shots, CEILING)


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
    return [s for s in screens if s.name != home or names_screen(s.name, prompt, brief)] or list(
        screens
    )


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


def _writer(ctx: dict[str, Any], target: Any, approved: list[str], request: dict[str, Any]) -> Any:
    """The same planner Explore's scope uses, from the same page facts and
    screenshots, with the user's request as context: `write(instruction,
    screens)`."""

    async def write(instruction: str, only: list[str]) -> list[dict[str, Any]]:
        return await brain.plan_tests(
            ctx["brief"],
            ctx["scope_info"],
            ctx["links"],
            ctx["walked"],
            [],
            f"{target.notes or ''}\nThe user's request: {ctx['prompt']}\n"
            f"The request read as: {json.dumps(request, ensure_ascii=False)}\n{instruction}",
            may_save=target.non_production,
            approved=approved,
            only=only,
            sign_in=False,
            shots=shots_of(ctx["scope_shots"], only),
        )

    return write


async def requested_scenarios(
    journal: Journal,
    write: Any,
    scope_info: list[dict[str, Any]],
    wanted: int,
    request: dict[str, Any],
    *,
    exact: bool,
    avoid: Sequence[str] = (),
    why: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(to try, set aside): with a number asked for, exactly that many
    scenarios the pages can support — written from the page facts, grounded
    (scope.ground_or_rewrite), and asked again for the rest (3 rounds) until
    the number is met. Without a number (only a limit): what the requirement
    calls for, at most `wanted`."""
    names = [str(i["name"]) for i in scope_info]
    found: list[dict[str, Any]] = []
    cant: list[dict[str, Any]] = []
    for _ in range(3 if exact else 1):
        need = wanted - len(found)
        if need <= 0:
            break
        seen = [*avoid, *(str(t.get("title")) for t in found + cant)]
        instruction = (
            why
            + (
                f"Write exactly {need} scenario(s) for the user's request — no more, no fewer"
                if exact
                else f"Write every scenario the user's request calls for (at most {need})"
            )
            + (f", within the user's limit: {request['only']}" if request.get("only") else "")
            + ". Each must be doable with what its page really has. Write nothing else."
            + (f"\nNever repeat: {json.dumps(seen, ensure_ascii=False)}" if seen else "")
        )
        try:
            written = await write(instruction, names)
        except Exception:  # noqa: BLE001 — another round, or fewer said plainly
            continue
        taken = set(seen)
        fresh = []
        for t in written:  # no repeat of earlier ones, nor within this reply
            title = str(t.get("title"))
            if t.get("kind") != "journey" and title not in taken:
                taken.add(title)
                fresh.append(t)
        written = fresh[:need]
        ok, off = await scope.ground_or_rewrite(journal, scope_info, written, write)
        found += ok
        cant += off
    return found[:wanted], cant


# Rounds of replacements for scenarios that couldn't be carried out, when the
# user asked for a number: enough to meet it, never a run that loops forever.
REFILL_ROUNDS = 2


async def refill(run_id: uuid.UUID) -> int:
    """The user asked for N test cases: each one that couldn't be carried out
    is replaced — written from the page facts, grounded, then tried — until N
    are delivered (REFILL_ROUNDS at most). Returns how many were added to
    try; 0 when the number is met, none was asked for, or rounds ran out (and
    then says plainly how many of N were delivered and why)."""
    journal = Journal(run_id)
    ctx = _load(run_id)
    if not ctx or not ctx["screens"]:
        return 0
    request = _request(ctx["brief"], ctx["prompt"])
    count = request.get("count")
    if not isinstance(count, int) or request.get("scenarios"):
        return 0  # no number asked for; listed scenarios stay word for word
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        tests = session.exec(
            select(ExplorerTestCase).where(ExplorerTestCase.run_id == run_id)
        ).all()
        if run is None or any(t.status in ("planned", "building") for t in tests):
            return 0
        rounds = int((run.insights or {}).get("refills") or 0)
        delivered = sum(t.status in ADDED for t in tests)
        short = count - delivered
        if short > 0 and rounds < REFILL_ROUNDS:
            run.insights = {**(run.insights or {}), "refills": rounds + 1}
            session.add(run)
            session.commit()
        dropped = [(t.title, t.drop_reason or "") for t in tests if t.status == "dropped"]
        titles = [t.title for t in tests]
    if short <= 0:
        return 0
    if rounds >= REFILL_ROUNDS:
        journal.event(
            "summary",
            f"{delivered} of the {count} test cases you asked for",
            "The pages had nothing more that could be tested: "
            + "; ".join(f"{title} — {why}" for title, why in dropped)[:2500],
        )
        return 0
    journal.event(
        "thought",
        f"Replacing {short} scenario(s) that couldn't be carried out",
        "; ".join(f"{title} — {why}" for title, why in dropped)[:2000],
    )
    target = load_target(run_id)
    approved = sorted(approved_presses(run_id)) if target.non_production else []
    found, cant = await requested_scenarios(
        journal,
        _writer(ctx, target, approved, request),
        ctx["scope_info"],
        short,
        request,
        exact=True,
        avoid=titles,
        why=(
            "These planned scenarios couldn't be carried out in the app: "
            + json.dumps([f"{t} — {w}" for t, w in dropped], ensure_ascii=False)[:3000]
            + ". Replace them: the same purpose where the page supports it, otherwise "
            "another useful check for the request.\n"
        ),
    )
    known = {str(i["name"]) for i in ctx["screen_info"]}
    return _save(run_id, found + cant, known, ctx["home"], ctx["flow_start"])


def _load(run_id: uuid.UUID) -> dict[str, Any] | None:
    """What a request's scenarios are planned from: the pages as they really
    are (facts and screenshots), the ways between them and what the walk
    found. None: the run is stopped or gone."""
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None or run.status in ("stopped", "paused"):
            return None
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
        if not screens:
            return {"screens": []}
        # Each page as it really is (fields, buttons, its elements; the
        # screenshots below): what the scenarios are planned from.
        screen_info = scope.screen_facts(list(screens), links)
        # The scope is the request's own screens: where the walk ended (the
        # flow, e.g. the New account form) and what came after. The screens it
        # only passed through to get there (a dashboard, the list holding the
        # New button) are the route, not what was asked to be tested.
        in_scope = flow_screens(screens, walk_end(all_screens), home, prompt, brief)
        scope_info = [i for i, s in zip(screen_info, screens, strict=True) if s in in_scope]
        scope_shots = scope.screen_shots(session, in_scope)
        request = _request(brief, prompt)
        return {
            "brief": brief,
            "prompt": prompt,
            "all_screens": all_screens,
            "home": home,
            "screens": screens,
            "links": links,
            "walked": walked,
            "screen_info": screen_info,
            "scope_info": scope_info,
            "scope_shots": scope_shots,
            # A flow starts where the walk ended (the build replays its clicks).
            "flow_start": home if request.get("scenarios") else (walk_end(all_screens) or home),
        }


async def plan_tests(run_id: uuid.UUID) -> int:
    journal = Journal(run_id)
    await ensure_scope(run_id)
    ctx = _load(run_id)
    if ctx is None:
        return 0
    if not ctx["screens"]:  # nothing to write scenarios about: say why, never "0 ready"
        journal.event("error", "Couldn't follow your request", NOTHING_SEEN)
        journal.update_run(
            status="failed", headline="Couldn't follow your request", error=NOTHING_SEEN
        )
        return 0
    brief, prompt, home = ctx["brief"], ctx["prompt"], ctx["home"]
    links, walked = ctx["links"], ctx["walked"]
    screen_info, scope_info, scope_shots = ctx["screen_info"], ctx["scope_info"], ctx["scope_shots"]
    journal.update_run(status="testing", headline="Writing your scenarios")
    journal.event("phase", "Writing your scenarios", "Turning your request into scenarios to try.")
    target = load_target(run_id)
    approved = sorted(approved_presses(run_id)) if target.non_production else []
    request = _request(brief, prompt)
    # A flow starts where the walk ended: the build replays the walk's
    # recorded clicks to get there (no model guessing a menu label again).
    if request.get("scenarios"):  # the user's own scenarios: anything unclear is asked
        clarified = await clarify_scenarios(journal, request, screen_info)
        if clarified is None:
            return 0
        request = clarified
    flow_start = home if request.get("scenarios") else ctx["flow_start"]
    planned = request_scenarios(prompt, request, flow_start, home)
    more = more_wanted(request)
    if wants_full_scope(request):  # a flow alone: its whole scope
        planned += await cover_scope(
            journal,
            f"The user's request: {prompt}\n"
            f"The request read as: {json.dumps(request, ensure_ascii=False)}",
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
        write = _writer(ctx, target, approved, request)
        found, cant = await requested_scenarios(
            journal, write, scope_info, more, request, exact=isinstance(request.get("count"), int)
        )
        planned += found + cant
    kept = _save(run_id, planned, {s["name"] for s in screen_info}, home, flow_start)
    journal.event(
        "phase",
        f"{kept} scenarios to try",
        "Trying each one in the app now, and proving it works the same way every time.",
    )
    return kept


def _save(
    run_id: uuid.UUID,
    planned: list[dict[str, Any]],
    known: set[str],
    home: str | None,
    flow_start: str | None,
) -> int:
    """The planned scenarios as test cases to try (the ones the pages can't
    support kept with why, never tried). Returns how many will be tried."""
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
                    # What the pages can't support is kept with its reason, never tried.
                    status="planned" if grounded and not t.get("not_possible") else "dropped",
                    drop_reason=(
                        f"Can't be tested here — {t['not_possible']}"[:400]
                        if t.get("not_possible")
                        else None
                        if grounded
                        else "Refers to a screen Explorer never saw"
                    ),
                )
            )
            kept += grounded and not t.get("not_possible")
        session.commit()
    return kept
