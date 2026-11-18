"""Runtime self-repair: when a step didn't take effect — a value the field
didn't keep, a press that found nothing or changed nothing — Explorer works
out why from the page itself and fixes it, on any app, with any widget.

Nothing here knows a widget. The AI reads the evidence (what was meant, what
the page shows now: element structure, screenshot, messages, what was tried)
and answers with generic actions on elements the page really has (click,
type, type key by key, a key, clear, wait). Each repair is checked against the
page; what fixed it is recorded as ordinary steps (so the replay and the
exported test do the same) and kept as a one-line lesson for the rest of the
run on this app, so the next walk gets it right first time."""

import re
from collections.abc import Awaitable, Callable
from typing import Any

from explorer_worker import brain
from explorer_worker.browser import Eyes
from explorer_worker.journal import Journal

# A numbered control on the marked screenshot: "#7".
_MARK = re.compile(r"^\s*#\s*(\d+)\s*$")


def numbered(marks: list[dict[str, Any]]) -> str:
    """The controls drawn on the marked screenshot, one line each:
    `#7 textbox “Search field” after “Territory”`."""
    lines = []
    for m in marks:
        names = " / ".join(f"“{x}”" for x in m.get("names") or []) or "(no name)"
        after = f" after “{m['caption']}”" if m.get("caption") else ""
        seen = "" if m.get("in_view") else " (scrolled out of view)"
        lines.append(f"#{m['n']} {m.get('role')} {names}{after}{seen}")
    return "\n".join(lines)


# Tries per broken step (each one AI call, then a check), and repairs per
# walk: a walk that keeps breaking is stuck for another reason.
TRIES = 2
PER_WALK = 8
# ponytail: per worker process; persist with the run if workers scale out.
_LESSONS: dict[str, list[str]] = {}

# (the steps the repair carried out) -> (worked, what the page shows now)
Check = Callable[[list[dict[str, Any]]], Awaitable[tuple[bool, str]]]


def lessons(origin: str) -> list[str]:
    """What earlier repairs taught about this app (newest last)."""
    return list(_LESSONS.get(origin, []))


def learn(origin: str, lesson: str) -> None:
    kept = _LESSONS.setdefault(origin, [])
    lesson = " ".join(str(lesson).split())[:200]
    if lesson and lesson not in kept:
        kept.append(lesson)
        del kept[:-20]


async def fix(
    eyes: Eyes, journal: Journal, goal: str, intent: str, problem: str, check: Check
) -> tuple[bool, list[dict[str, Any]]]:
    """(fixed, the steps carried out — record them even when not fixed: they
    happened on the page). `check` reads the page: (worked, what it shows)."""
    assert eyes.page is not None
    done: list[dict[str, Any]] = []
    tried: list[dict[str, Any]] = []
    for _ in range(TRIES):
        visit = await eyes.look(eyes.page.url, None, 0)
        # Every control numbered on the screenshot, so the AI can point at
        # the one it means when names don't tell them apart.
        shot, marks = await eyes.marked_shot()
        try:
            plan = await brain.repair_step(
                goal,
                intent,
                problem,
                str(visit.inventory.get("aria") or ""),
                shot,
                tried,
                eyes.messages,
                lessons(eyes.origin),
                numbered(marks),
            )
        except Exception:  # noqa: BLE001 — no repair: the walk goes on as before
            return False, done
        # "#7" → a locator for that control, found now, before any action
        # changes the page (a replay and the exported test use it as-is).
        by_number = {str(m["n"]): m for m in marks}
        specs: list[dict[str, Any] | None] = []
        for action in plan["actions"]:
            hit = _MARK.match(str(action.get("target") or ""))
            mark = by_number.get(hit[1]) if hit else None
            if mark is not None:
                action["label"] = mark.get("name") or mark.get("caption") or ""
            specs.append(await eyes.stable_spec(mark) if mark is not None else None)
        give_up = str(plan.get("give_up") or "").strip()
        if give_up:
            if give_up.lower() != "intended":
                journal.event("thought", f"Left as it is: {intent}", give_up[:400])
            return False, done
        failed = ""
        for action, spec in zip(plan["actions"], specs, strict=True):
            if _MARK.match(str(action.get("target") or "")) and spec is None:
                failed = f"couldn't find {action.get('target')} again"
                break
            step = await eyes.do_repair(action, spec)
            if step is None:
                failed = f"couldn't {action.get('do')} {action.get('target') or ''}".strip()
                break
            if step:
                done.append(step)
        worked, shows = (False, failed) if failed else await check(done)
        if worked:
            if plan.get("lesson"):
                learn(eyes.origin, str(plan["lesson"]))
            journal.event(
                "thought",
                f"Fixed it: {intent}",
                str(plan.get("diagnosis") or "")[:400] or None,
            )
            return True, done
        tried.append({"actions": plan["actions"], "result": shows[:300]})
        problem = shows or problem
    journal.event("thought", f"Couldn't fix: {intent}", problem[:400])
    return False, done


def fill_check(eyes: Eyes, spec: dict[str, Any] | None, value: str) -> Check:
    """Did the field keep a value the app accepts? (Typed something, not
    flagged.) A field left empty on purpose only needs to be empty."""

    async def check(_steps: list[dict[str, Any]]) -> tuple[bool, str]:
        state = await eyes.field_state(spec)
        if state is None:
            return False, "the field can't be found any more"
        held, flagged = state
        if not value.strip():
            return (not held.strip(), f"the field still holds “{held}”")
        if not held.strip():
            return False, "the field is empty: the app did not keep the value"
        if flagged:
            return False, f"the field holds “{held}” but the app flags it as not valid"
        return True, f"the field holds “{held}”"

    return check


def typed_check() -> Check:
    """For a field that couldn't be found at all: fixed once the repair typed
    into one (it found the field the step meant)."""

    async def check(steps: list[dict[str, Any]]) -> tuple[bool, str]:
        typed = any(s.get("do") == "fill" for s in steps)
        return typed, "typed into the field" if typed else "no field was typed into"

    return check


def press_check(eyes: Eyes, before: str) -> Check:
    """Did the press happen and change the screen?"""

    async def check(steps: list[dict[str, Any]]) -> tuple[bool, str]:
        if not any(s.get("do") in ("click", "key") for s in steps):
            return False, "nothing was pressed"
        if await eyes.fingerprint() != before:
            return True, "the screen changed"
        return False, "it was pressed but the screen did not change"

    return check
