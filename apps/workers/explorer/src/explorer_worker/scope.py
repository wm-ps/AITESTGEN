"""The scope check, shared by Explore (tests_stage.plan_tests) and authoring
(authoring.plan): the planned scenarios are checked item by item against each
screen's scope checklist; what a screen has but no scenario checks is written
and checked again; and the outcome is said plainly — covered (by which
tests), left out (the page has nothing for it, and why), still missing."""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from explorer_core import ExplorerScreen, ExplorerShot
from sqlmodel import Session

from explorer_worker import brain
from explorer_worker.journal import Journal
from explorer_worker.llm import THINKING_MODEL, ask_json

# The scope every screen is checked against: Explorer's own checklist items,
# read from its planning prompt so the two never drift apart.
SCOPE_ITEMS: dict[str, str] = {
    **dict(re.findall(r"\b([LFE]-\d\d) ([^:\n]+):", brain._PLAN_TESTS_SYSTEM)),
    "P-01": "Page loads (dashboards, details, wizard steps)",
}
# Check → write what is missing → check again, at most this many times.
SCOPE_ROUNDS = 2

_SCOPE_CHECK_SYSTEM = (
    brain.STANCE
    + """

You check a test plan against the testing scope, screen by screen. For EVERY screen given, \
go through EVERY scope item that fits its kind (L- items for a list, F- items for a form \
or wizard, P-01 for any other screen, E- items for every screen) and decide:
- "covered": a planned test that starts on that screen checks it (name the test titles);
- "missing": the screen HAS what the item needs (the field, button, column, paging, \
dropdown...), but no planned test checks it;
- "not_applicable": the screen has nothing for it — say what is absent, e.g. 'no paging \
controls', 'no Edit on the rows', 'no field depends on another'.
For per-field items (F-06 invalid format, F-09 range), "covered" means every field the \
item fits has a test; otherwise "missing", naming the fields still untested in 'why'. \
F-07 max length and F-08 min length are per FORM: one test on the form covers it (more \
than one is a duplicate — 'leave_out' the rest); a limit counts only when the field \
shows or states one, never an assumed default like 255. \
Judge from each screen's screenshot (in the order the screens are listed) as well as \
its kind, fields and buttons: icon buttons, clickable rows, filter and sort controls \
count even when unnamed. Never invent what a screen has.
The app-wide parts on every screen (the main menu, the header's global search, \
notifications, the account menu) are not any screen's scope.
Also list in 'leave_out' the planned tests not worth trying: a duplicate of another \
planned test (same thing checked on the same screen — keep the first), or a test about \
the app-wide parts or about a screen not given here.
Reply with ONLY:
{"screens": [{"screen": "exact screen name", "items": [{"id": "F-06", "status": \
"covered | missing | not_applicable", "tests": ["planned test title"], \
"why": "one short line"}]}],
 "leave_out": [{"title": "exact planned test title", "why": "duplicate of … / app-wide …"}]}"""
)


async def _check_part(
    screen_info: list[dict[str, Any]],
    planned: list[dict[str, Any]],
    shots: list[bytes],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    tests = [{k: t.get(k) for k in ("title", "start_screen", "coverage", "rule")} for t in planned]
    reply = await ask_json(
        _SCOPE_CHECK_SYSTEM,
        f"Scope items: {json.dumps(SCOPE_ITEMS, ensure_ascii=False)}\n"
        f"Screens: {json.dumps(screen_info, ensure_ascii=False)[:40000]}\n"
        f"Planned tests: {json.dumps(tests, ensure_ascii=False)[:40000]}",
        images=shots or None,
        model=THINKING_MODEL,
    )
    leave_out = {
        str(d["title"]): str(d.get("why") or "")
        for d in reply.get("leave_out") or []
        if isinstance(d, dict) and d.get("title")
    }
    return [
        {"screen": str(screen.get("screen") or ""), **item}
        for screen in reply.get("screens") or []
        if isinstance(screen, dict)
        for item in screen.get("items") or []
        if isinstance(item, dict)
        and item.get("id") in SCOPE_ITEMS
        and item.get("status") in ("covered", "missing", "not_applicable")
    ], leave_out


def _item(row: dict[str, Any]) -> str:
    return f"{row['id']} {SCOPE_ITEMS[row['id']]}"


def scope_report(report: list[dict[str, Any]]) -> tuple[str, str]:
    """The scope check in plain words: per screen, what is covered and by
    which tests, what was left out because the page has nothing for it, and
    anything still missing."""
    covered = [r for r in report if r["status"] == "covered"]
    missing = [r for r in report if r["status"] == "missing"]
    skipped = [r for r in report if r["status"] == "not_applicable"]
    headline = (
        f"Scope check: {len(covered)} of {len(covered) + len(missing)} items covered"
        + (f", {len(missing)} still missing" if missing else "")
        + f" ({len(skipped)} not on these pages)"
    )
    lines: list[str] = []
    for screen in dict.fromkeys(r["screen"] for r in report):
        rows = [r for r in report if r["screen"] == screen]
        lines.append(f"{screen}:")
        lines += [
            f"  ✓ {_item(r)} — {', '.join(map(str, r.get('tests') or [])) or r.get('why', '')}"
            for r in rows
            if r["status"] == "covered"
        ]
        lines += [
            f"  ✗ {_item(r)} — not covered: {r.get('why', '')}"
            for r in rows
            if r["status"] == "missing"
        ]
        lines += [
            f"  – {_item(r)} — left out: {r.get('why', '')}"
            for r in rows
            if r["status"] == "not_applicable"
        ]
    return headline, "\n".join(lines)


# Screens per check call (with their screenshots): a whole app is checked a
# few screens at a time, several calls at once.
SCREENS_PER_CHECK = 4


async def check_scope(
    screen_info: list[dict[str, Any]],
    planned: list[dict[str, Any]],
    shots: dict[str, bytes] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Each scope item on each screen: covered (by which tests), missing,
    or not applicable (and why) — judged from the screenshots too (by screen
    name); and the planned tests to leave out (duplicates, app-wide parts),
    title → why. A few screens per call, each with only its own tests."""
    shots = shots or {}
    gate = asyncio.Semaphore(4)

    async def part(chunk: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
        names = {str(s["name"]) for s in chunk}
        images = [shots[str(s["name"])] for s in chunk if str(s["name"]) in shots]
        async with gate:
            return await _check_part(
                chunk,
                [t for t in planned if str(t.get("start_screen") or "") in names],
                images if len(images) == len(chunk) else [],
            )

    chunks = [
        screen_info[i : i + SCREENS_PER_CHECK]
        for i in range(0, len(screen_info), SCREENS_PER_CHECK)
    ]
    parts = await asyncio.gather(*(part(c) for c in chunks))
    report = [row for rows, _ in parts for row in rows]
    leave_out = {title: why for _, out in parts for title, why in out.items()}
    return report, leave_out


def gaps_text(missing: list[dict[str, Any]]) -> str:
    """The missing scope items, as the instruction to write them."""
    return (
        "The plan does not yet cover these scope items. Write a scenario for each (one per "
        "field where the item names fields, except F-07 / F-08: ONE per form, on the field "
        "whose limit the form shows or states — never an assumed limit like 255), starting "
        "on that screen, with 'coverage' set to the item's ID and name. Write nothing else.\n"
        + "\n".join(f"- On {r['screen']}: {_item(r)} ({r.get('why', '')})" for r in missing)
    )


async def cover(
    journal: Journal,
    screen_info: list[dict[str, Any]],
    tests: list[dict[str, Any]],
    write_gaps: Callable[[list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]],
    shots: dict[str, bytes] | None = None,
    ceiling: int | None = None,
) -> list[dict[str, Any]]:
    """Check the plan against the scope, write what is missing and check
    again (SCOPE_ROUNDS times), then say plainly what is covered, left out
    and why. `ceiling`: at most this many scenarios."""
    report: list[dict[str, Any]] = []
    for attempt in range(SCOPE_ROUNDS + 1):
        tests = tests[:ceiling] if ceiling else tests
        try:
            report, leave_out = await check_scope(screen_info, tests, shots)
        except Exception:  # noqa: BLE001 — the check adds tests; never block planning
            journal.event("thought", "Couldn't check the scenarios against the scope")
            return tests
        if leave_out:
            tests = [t for t in tests if str(t.get("title")) not in leave_out]
            journal.event(
                "thought",
                f"Left out {len(leave_out)} scenario(s) before trying them",
                "; ".join(f"{title}: {why}" for title, why in leave_out.items()),
            )
        missing = [r for r in report if r["status"] == "missing"]
        full = bool(ceiling) and len(tests) >= (ceiling or 0)
        if not missing or attempt == SCOPE_ROUNDS or full:
            break
        journal.event(
            "thought",
            f"Scope not met yet: {len(missing)} item(s) missing — writing scenarios for them",
            "; ".join(f"{r['screen']}: {_item(r)}" for r in missing),
        )
        titles = {t.get("title") for t in tests}
        tests += [t for t in await write_gaps(missing) if t.get("title") not in titles]
    headline, detail = scope_report(report)
    if ceiling and len(tests) >= ceiling and any(r["status"] == "missing" for r in report):
        detail += f"\n(Stopped at the limit of {ceiling} scenarios per run.)"
    journal.event("summary", headline, detail)
    return tests


def screen_shots(session: Session, screens: list[ExplorerScreen]) -> dict[str, bytes]:
    """Each screen's screenshot, by name, for the scope check."""
    out: dict[str, bytes] = {}
    for screen in screens:
        shot = session.get(ExplorerShot, screen.shot_id) if screen.shot_id else None
        if shot is not None:
            out.setdefault(screen.name, shot.data)
    return out
