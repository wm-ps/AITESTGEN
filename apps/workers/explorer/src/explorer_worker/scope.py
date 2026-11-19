"""The scope check, shared by Explore (tests_stage.plan_tests) and authoring
(authoring.plan): the planned scenarios are checked item by item against each
screen's scope checklist; what a screen has but no scenario checks is written
and checked again; and the outcome is said plainly — covered (by which
tests), left out (the page has nothing for it, and why), still missing."""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from explorer_core import ExplorerRun, ExplorerScreen, ExplorerShot
from sqlmodel import Session

from explorer_worker import brain, memory, samples
from explorer_worker.db import engine
from explorer_worker.field_checks import (
    CHANGES_PASSWORD,
    CODE_LIMITS,
    FIELD_CHECK,
    SKIP_KINDS,
    message_for,
    plain_label,
)
from explorer_worker.journal import Journal
from explorer_worker.llm import THINKING_MODEL, ask_json

# The scope every screen is checked against: Explorer's own checklist items,
# read from its planning prompt so the two never drift apart.
SCOPE_ITEMS: dict[str, str] = {
    # At a line's start: "(F-06 to F-08: skip …" is a note, not item F-06's name.
    **dict(re.findall(r"^([LFE]-\d\d) ([^:\n]+):", brain._PLAN_TESTS_SYSTEM, re.M)),
    "P-01": "Page loads (dashboards, details, wizard steps)",
}
# Check → write what is missing → check again, at most this many times.
SCOPE_ROUNDS = 3

# Per-field scope, listed by code from the fields each form really has (never
# by the model): an item per required field, per dropdown and per number,
# date, email, phone or web-address field. "Covered" then means every field
# has its own test, not "one test touched the checklist item".
_FIELD_ITEM = {
    "select": "F-03",
    "combobox": "F-03",
    "number": "F-09",
    "date": "F-06",
    "datetime-local": "F-06",
    "email": "F-06",
    "tel": "F-06",
    "url": "F-06",
}
_WHAT = {
    "F-03": "{label} offers its options",
    "F-09": "{label} refuses a number outside its range (e.g. a negative one)",
    "F-06": "{label} refuses a value in the wrong format",
}
# Which tests count for an item: their 'coverage' (or 'linked_to') starts so.
_COUNTS_FOR = {
    "F-05": ("F-05",),  # FIELD_CHECK is "F-05 Field rules"
    "F-03": ("F-03",),
    "F-06": ("F-06", "F-09", "F-05"),
    "F-09": ("F-09", "F-06", "F-05"),
}
_SEARCH_BOX = re.compile(r"\bsearch\b", re.I)  # the header's global search, not the form's


def field_units(screen_info: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each form's per-field scope items: {screen, id, field, what}. Only what
    the page has (its recorded fields): evidence, never assumptions."""
    units: list[dict[str, Any]] = []
    for screen in screen_info:
        fields = [
            {**f, "label": plain_label(f.get("label"))}
            for f in screen.get("fields") or []
            if plain_label(f.get("label")) and not _SEARCH_BOX.search(str(f.get("label")))
        ]
        if screen.get("kind") in SKIP_KINDS or any(
            CHANGES_PASSWORD.search(f["label"]) for f in fields
        ):
            continue
        name = str(screen["name"])
        required = [
            f["label"] for f in fields if f.get("required") is True or message_for(f, "required")
        ]
        if required:
            empty = "the empty form can't be saved"
            units.append({"screen": name, "id": "F-05", "field": None, "what": empty})
        if len(required) > 1:  # one required field: the empty form is its test
            units += [
                {"screen": name, "id": "F-05", "field": f, "what": f"{f} left empty is refused"}
                for f in required
            ]
        for f in fields:
            item = _FIELD_ITEM.get(str(f.get("type") or "").lower())
            if item:
                units.append(
                    {
                        "screen": name,
                        "id": item,
                        "field": f["label"],
                        "what": _WHAT[item].format(label=f["label"]),
                    }
                )
    return units


def _named(text: str, labels: list[str]) -> set[str]:
    """The field labels `text` names as whole words — the longest one where
    labels overlap ("Expected Reps" is not also "Reps")."""
    found = {
        label
        for label in labels
        if re.search(rf"(?<!\w){re.escape(label)}(?!\w)", text, re.I)
    }
    return {
        label
        for label in found
        if not any(other != label and label.lower() in other.lower() for other in found)
    }


def _covers(test: dict[str, Any], unit: dict[str, Any], labels: list[str]) -> bool:
    if str(test.get("start_screen") or "") != unit["screen"]:
        return False
    tags = f"{test.get('coverage') or ''} {test.get('linked_to') or ''}".upper()
    if not any(re.search(rf"\b{p}\b", tags) for p in _COUNTS_FOR[unit["id"]]):
        return False
    title = str(test.get("title") or "")
    if unit["field"] is None:  # the empty form
        return "empty" in title.lower()
    if "empty" in title.lower() and unit["id"] == "F-05":
        return False  # the empty-form test lists every required field in its rule
    # Field rules share one tag ("F-05 Field rules"): "Quota Target is required"
    # and "Quota Target refuses a value below 0" are told apart by their title.
    if ("required" in title.lower()) != (unit["id"] == "F-05"):
        return False
    return unit["field"] in _named(f"{title} {test.get('rule') or ''}", labels)


def uncovered(
    units: list[dict[str, Any]], tests: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The per-field items no test in `tests` covers."""
    labels = [str(u["field"]) for u in units if u["field"]]
    return [u for u in units if not any(_covers(t, u, labels) for t in tests)]


def keep_needed(
    tests: list[dict[str, Any]], leave_out: dict[str, str], units: list[dict[str, Any]]
) -> dict[str, str]:
    """`leave_out` minus what must stay: a recorded field rule (FIELD_CHECK,
    one per field and rule by construction, never a duplicate) and the only
    test left for a per-field item."""
    out = {
        title: why
        for title, why in leave_out.items()
        if not any(str(t.get("title")) == title and t.get("coverage") == FIELD_CHECK for t in tests)
    }
    labels = [str(u["field"]) for u in units if u["field"]]
    kept = [t for t in tests if str(t.get("title")) not in out]
    for unit in uncovered(units, kept):
        saver = next((t for t in tests if _covers(t, unit, labels)), None)
        if saver is not None:
            out.pop(str(saver.get("title")), None)
            kept.append(saver)
    return out


def unit_rows(units: list[dict[str, Any]], tests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The per-field items as scope-report rows (covered by which tests, or
    missing)."""
    labels = [str(u["field"]) for u in units if u["field"]]
    rows = []
    for unit in units:
        by = [str(t.get("title")) for t in tests if _covers(t, unit, labels)]
        rows.append(
            {
                "screen": unit["screen"],
                "id": unit["id"],
                "field": unit["field"],
                "status": "covered" if by else "missing",
                "tests": by,
                "why": unit["what"],
            }
        )
    return rows

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
the app-wide parts or about a screen not given here. Tests of DIFFERENT fields are never \
duplicates, nor are different rules on one field: "Type is required" and "Region is \
required" are two tests, and neither duplicates the empty-form test; "Director offers its \
options" does not duplicate "Type offers its options".
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
    cant: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    tests = [{k: t.get(k) for k in ("title", "start_screen", "coverage", "rule")} for t in planned]
    reply = await ask_json(
        _SCOPE_CHECK_SYSTEM,
        f"Scope items: {json.dumps(SCOPE_ITEMS, ensure_ascii=False)}\n"
        f"Screens: {json.dumps(screen_info, ensure_ascii=False)[:60000]}\n"
        f"Planned tests: {json.dumps(tests, ensure_ascii=False)[:40000]}"
        + (
            "\nTried to plan but the page lacks what they need — count their items as "
            f"not_applicable with this reason: {json.dumps(cant, ensure_ascii=False)[:6000]}"
            if cant
            else ""
        ),
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
    field = f" — {row['field']}" if row.get("field") else ""
    return f"{row['id']} {SCOPE_ITEMS[row['id']]}{field}"


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
    cant: list[dict[str, Any]] | None = None,
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
                [
                    f"{t.get('start_screen')}: {t.get('coverage') or ''} {t.get('title')} — "
                    f"{t.get('not_possible')}"
                    for t in cant or []
                    if str(t.get("start_screen") or "") in names
                ],
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
        "on that screen, with 'coverage' set to the item's ID and name. When an item names a "
        "field (after the —), write exactly one scenario for that field and put the field's "
        "exact name in its title. Write nothing else.\n"
        + "\n".join(f"- On {r['screen']}: {_item(r)} ({r.get('why', '')})" for r in missing)
    )


async def cover(
    journal: Journal,
    screen_info: list[dict[str, Any]],
    tests: list[dict[str, Any]],
    write_gaps: Callable[[str, list[str]], Awaitable[list[dict[str, Any]]]],
    shots: dict[str, bytes] | None = None,
    ceiling: int | None = None,
) -> list[dict[str, Any]]:
    """Ground the plan in the pages (`ground`), check it against the scope,
    write what is missing and check again (SCOPE_ROUNDS times), then say
    plainly what is covered, left out and why. `write_gaps(instruction,
    screens)` writes scenarios for those screens. `ceiling`: at most this
    many scenarios. Returns the scenarios to try, then the ones not tried,
    each with why (`set_aside_reason`): the pages can't support it, the scope
    check left it out, or it was over the limit."""
    cant: list[dict[str, Any]] = []
    over: dict[str, dict[str, Any]] = {}

    async def grounded(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ok, off = await ground_or_rewrite(journal, screen_info, batch, write_gaps)
        cant.extend(off)
        return ok

    tests = await grounded(tests)
    units = field_units(screen_info)
    report: list[dict[str, Any]] = []
    for attempt in range(SCOPE_ROUNDS + 1):
        if ceiling and len(tests) > ceiling:
            for t in tests[ceiling:]:
                over.setdefault(
                    str(t.get("title")),
                    left(t, f"Not tried: over the limit of {ceiling} scenarios per run"),
                )
            tests = tests[:ceiling]
        try:
            report, leave_out = await check_scope(screen_info, tests, shots, cant)
        except Exception:  # noqa: BLE001 — the check adds tests; never block planning
            journal.event("thought", "Couldn't check the scenarios against the scope")
            return tests + cant + _still_over(over, tests)
        # Field rules and each field's only test are never left out, and the
        # per-field items are counted by code, field by field: the model's
        # rows for those items on those screens give way to them.
        leave_out = keep_needed(tests, leave_out, units)
        fielded = {(u["screen"], u["id"]) for u in units}
        report = [r for r in report if (r["screen"], r["id"]) not in fielded]
        if leave_out:
            cant += [
                left(t, f"Left out before trying: {leave_out[str(t.get('title'))]}"[:400])
                for t in tests
                if str(t.get("title")) in leave_out
            ]
            tests = [t for t in tests if str(t.get("title")) not in leave_out]
            journal.event(
                "thought",
                f"Left out {len(leave_out)} scenario(s) before trying them",
                "; ".join(f"{title}: {why}" for title, why in leave_out.items()),
            )
        report += unit_rows(units, tests)
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
        screens = list(dict.fromkeys(str(r["screen"]) for r in missing))
        written = await write_gaps(gaps_text(missing), screens)
        tests += await grounded([t for t in written if t.get("title") not in titles])
    headline, detail = scope_report(report)
    if ceiling and len(tests) >= ceiling and any(r["status"] == "missing" for r in report):
        detail += f"\n(Stopped at the limit of {ceiling} scenarios per run.)"
    if cant:
        detail += "\nNot tried:\n" + "\n".join(
            f"  – {t.get('title')} ({t.get('start_screen')}): {set_aside_reason(t)}" for t in cant
        )
    journal.event("summary", headline, detail)
    return tests + cant + _still_over(over, tests)


def _still_over(
    over: dict[str, dict[str, Any]], tests: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The scenarios cut by the limit that didn't make it back in."""
    kept = {str(t.get("title")) for t in tests}
    return [t for title, t in over.items() if title not in kept]


def screen_shots(session: Session, screens: list[ExplorerScreen]) -> dict[str, bytes]:
    """Each screen's screenshot, by name, for the scope check."""
    out: dict[str, bytes] = {}
    for screen in screens:
        shot = session.get(ExplorerShot, screen.shot_id) if screen.shot_id else None
        if shot is not None:
            out.setdefault(screen.name, shot.data)
    return out


# Per screen, the element structure the planner reads: enough for every
# control and the first rows of a list, not a 500-row table.
ELEMENT_CHARS = 6000
ROWS_PER_LIST = 10


def _norm(line: str) -> str:
    return " ".join(line.strip().removeprefix("- ").split()).lower()


def trim_rows(aria: str, keep: int = ROWS_PER_LIST) -> str:
    """The snapshot with each list's rows cut to the first `keep` (their
    contents included)."""
    out: list[str] = []
    rows: dict[int, int] = {}  # indent -> rows kept at that depth under the current parent
    skip_deeper: int | None = None
    for line in aria.splitlines():
        depth = len(line) - len(line.lstrip())
        if skip_deeper is not None and depth > skip_deeper:
            continue
        skip_deeper = None
        rows = {d: n for d, n in rows.items() if d <= depth}
        if _norm(line).startswith(("row ", "row:", "listitem", "option ")):
            rows[depth] = rows.get(depth, 0) + 1
            if rows[depth] > keep:
                skip_deeper = depth
                continue
        else:
            rows.pop(depth, None)
        out.append(line)
    return "\n".join(out)


_LINK = re.compile(r"^(.*?) --(.*)--> (.*)$")


def screen_facts(
    screens: list[ExplorerScreen], links: Sequence[str] = ()
) -> list[dict[str, Any]]:
    """What scenarios are planned from, per screen: its fields (with the
    page code's limits and the form's own messages), buttons, its element
    structure — every control, option, column and the first rows of each
    list, as the page really has them — where its actions were seen to
    lead (`links`: "A --action--> B"), and which of its controls are the
    app's shared menu, header and footer (`app_wide`: not its scope)."""
    shared = app_wide_controls(screens)
    ways: dict[str, list[dict[str, str]]] = {}
    for link in links:
        m = _LINK.match(link)
        if m and m[1] != m[3]:
            ways.setdefault(m[1], []).append({"action": m[2], "to": m[3]})
    return [
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
                    # The page code's own limits (field_checks.with_code_limits).
                    **{k: f[k] for k in CODE_LIMITS if f.get(k)},
                    # The messages the form showed for wrong values (field_probe).
                    **({"messages": f["messages"]} if f.get("messages") else {}),
                }
                for f in s.fields
            ][:40],
            "buttons": [a.get("label") for a in s.actions][:20],
            **({"elements": trim_rows(s.aria)[:ELEMENT_CHARS]} if s.aria else {}),
            **({"leads_to": ways[s.name][:30]} if s.name in ways else {}),
            **({"app_wide": sorted(shared)[:60]} if shared and s.aria else {}),
        }
        for s in screens
    ]


_CONTROL = ("link ", "button ", "menuitem ", "searchbox", "combobox ", "textbox ", "tab ")


def app_wide_controls(screens: Sequence[ExplorerScreen]) -> set[str]:
    """The app's shared menu, header and footer: controls on (nearly) every
    screen, each once and alike (the main menu's links, the account menu,
    Terms). Needs 3 screens at least — on fewer, nothing is shared by
    chance alone."""
    pages = [s.aria for s in screens if s.aria]
    if len(pages) < 3:
        return set()
    counts: dict[str, int] = {}
    for aria in pages:
        lines = [_norm(line).rstrip(":") for line in aria.splitlines()]
        once = {line for line in lines if line.startswith(_CONTROL) and lines.count(line) == 1}
        for line in once:
            counts[line] = counts.get(line, 0) + 1
    return {line for line, n in counts.items() if n * 4 >= len(pages) * 3}


def _on_page(entry: str, lines: list[str], text: str) -> bool:
    want = _norm(entry)
    return bool(want) and (any(want in line for line in lines) or want in text)


def _depth(line: str) -> int:
    return len(line) - len(line.lstrip())


_SECTION_LABEL = ("heading", "paragraph", "group", "region")


def _in_section(element: str, near: str, aria: str) -> bool:
    """Is `element` inside the part of the page labelled `near`? Judged only
    when the element's name repeats on the page (several `button "Icon"`) and
    the label is found; otherwise True — the page-wide check stands. A
    section is a container's children, or the lines after a label up to the
    next label beside it."""
    raw = aria.splitlines()
    lines = [_norm(line) for line in raw]
    want, label = _norm(element), _norm(near)
    if not want or not label or sum(want in line for line in lines) < 2:
        return True
    starts = [i for i, line in enumerate(lines) if label in line]
    if not starts:
        return True
    for i in starts:
        top = _depth(raw[i])
        container = i + 1 < len(raw) and _depth(raw[i + 1]) > top
        for j in range(i + 1, len(raw)):
            d = _depth(raw[j])
            if d < top or (container and d == top):
                break
            if not container and d == top and lines[j].startswith(_SECTION_LABEL):
                break
            if want in lines[j]:
                return True
    return False


# A file a test names: Explorer can only attach its own samples (samples.FILES).
_FILE = re.compile(
    r"[\w{}\-]+(?:\.[\w{}\-]+)*\.(?:pdf|docx?|xlsx?|pptx?|png|jpe?g|gif|webp|csv|txt)\b", re.I
)


def _unknown_file(t: dict[str, Any], page_text: str) -> str | None:
    """A file `t` names that Explorer can't attach (not one of its samples,
    nor a file the pages already show), or None."""
    text = " ".join(
        str(x)
        for x in (
            t.get("title"),
            t.get("how_to_run"),
            t.get("expected"),
            *(t.get("steps") or []),
            *((t.get("data") or {}).get("types") or []),
        )
    )
    stems = tuple(name.rsplit(".", 1)[0] for name in samples.FILES)
    for name in _FILE.findall(text):
        if not name.lower().startswith(stems) and name.lower() not in page_text:
            return (
                f"it needs a file Explorer can't attach: “{name}” — it attaches its own "
                f"sample files ({', '.join(samples.FILES)}); name the kind of file, not a file"
            )
    return None


def _value_seen(
    value: str, path_text: str, by_screen: dict[str, str], records: Sequence[str]
) -> dict[str, str] | None:
    """Where `value` was seen: on the test's own pages, on another page
    Explorer saw, or in the test data the app showed while exploring (a
    record it created, a search result — memory.remember_record). None: not
    seen anywhere."""
    want = _norm(value)
    if want in path_text:
        return {"value": value, "source": "page"}
    for name, elements in by_screen.items():
        if want in _norm(elements):
            return {"value": value, "source": f"page: {name}"}
    for record in records:
        if want in _norm(record):
            return {"value": value, "source": f"record: {record[:200]}"}
    return None


def _flow_problem(
    t: dict[str, Any],
    by_screen: dict[str, str],
    leads: dict[str, list[tuple[str, str]]],
    records: Sequence[str] = (),
) -> tuple[str | None, list[dict[str, str]]]:
    """(why `t`'s steps can't happen as planned or None, where each value it
    finds was seen): every step on a screen Explorer saw, using an element
    that screen has (inside the section it names, when its name repeats), and
    every move to another screen made by the element of the step before it,
    the way Explorer saw that screen do it. Each value it finds is looked up
    on the pages and in the test data the app showed (`records`); one seen
    nowhere doesn't stop it — it is marked UNSEEN and checked in the app when
    the scenario is tried (a search can find what no saved page showed)."""
    start = str(t.get("start_screen") or "")
    path = [p for p in t.get("path") or [] if isinstance(p, dict)]
    if not path:
        return "doesn't say which page each step happens on and what it uses", []
    here, pressed = start, ""
    seen: list[str] = []
    for step in path:
        screen = str(step.get("screen") or "")
        element = str(step.get("element") or "").strip()
        if screen not in by_screen:
            return f"goes to a screen Explorer never saw: “{screen}”", []
        if screen != here:
            ways = [action for action, to in leads.get(here, []) if to == screen]
            if not ways:
                return f"no way was seen from “{here}” to “{screen}”", []
            if pressed and not any(_norm(a) and _norm(a) in _norm(pressed) for a in ways):
                return (
                    f"{pressed} on “{here}” was never seen to lead to “{screen}” "
                    f"(seen: {', '.join(ways)})"
                )[:300], []
        lines = [_norm(line) for line in by_screen[screen].splitlines()]
        if element and lines and not _on_page(element, lines, " ".join(lines)):
            return f"“{screen}” has no {element}", []
        near = str(step.get("near") or "").strip()
        if element and near and not _in_section(element, near, by_screen[screen]):
            return f"“{near}” on “{screen}” has no {element}", []
        here, pressed = screen, element
        seen.append(screen)
    lines = [_norm(line) for s in dict.fromkeys(seen) for line in by_screen[s].splitlines()]
    text = " ".join(lines)
    evidence: list[dict[str, str]] = []
    for value in (t.get("data") or {}).get("finds") or []:
        value = str(value).strip()
        if not value or not lines:
            continue
        evidence.append(
            _value_seen(value, text, by_screen, records) or {"value": value, "source": UNSEEN}
        )
    return None, evidence


# A value no saved page or test data showed: checked on the live page when
# the scenario is tried (tests_stage.repair is told which).
UNSEEN = "not seen while exploring — checked in the app"
# Why a planned scenario isn't tried (kept with it, `outcome`).
REJECTED = "rejected"


def set_aside_reason(t: dict[str, Any]) -> str | None:
    """Why a planned scenario is kept but not tried (shown with it), or None."""
    if t.get("left_out"):
        return str(t["left_out"])[:400]
    if t.get("not_possible"):
        return f"Can't be tested here — {t['not_possible']}"[:400]
    return None


def left(t: dict[str, Any], why: str) -> dict[str, Any]:
    """`t`, kept but not tried, with why."""
    return {**t, "left_out": why, "outcome": REJECTED}


def trace(t: dict[str, Any]) -> dict[str, Any]:
    """What a planned scenario was planned from, kept with it (script[0]): its
    flow, the values it needs and where each was seen, its category, and —
    when it isn't tried — its outcome."""
    return {k: t[k] for k in ("path", "data", "evidence", "category", "outcome") if t.get(k)}


def evidenced(
    items: Sequence[dict[str, Any]], facts: Sequence[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(kept, not kept with why): coverage-map items (brain.coverage_map)
    whose evidence is on their own screen — never a shared menu control, never
    F-05 (field rules are written per field)."""
    by_screen = {str(f["name"]): f for f in facts}
    kept: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    for item in items:
        fact = by_screen.get(str(item.get("screen") or ""))
        evidence = str(item.get("evidence") or "").strip()
        lines = [_norm(line) for line in str((fact or {}).get("elements") or "").splitlines()]
        shared = {str(c) for c in (fact or {}).get("app_wide") or []}
        why = (
            "a screen not in the flow"
            if fact is None
            else "required fields are written per field"
            if str(item.get("id") or "").startswith("F-05")
            else "no evidence named"
            if not evidence
            else f"“{evidence}” isn't on that screen"
            if lines and not _on_page(evidence, lines, " ".join(lines))
            else "the app's shared menu, header or footer"
            if _norm(evidence).rstrip(":") in shared
            else None
        )
        if why:
            out.append({**item, "why": why})
        else:
            kept.append(item)
    return kept, out


def not_needed(
    tests: Sequence[dict[str, Any]], facts: Sequence[dict[str, Any]]
) -> dict[int, str]:
    """{index: why} for planned ideas that aren't scenarios to try — said
    with them, never counted as planned: a copy of an earlier one
    (`duplicates`), a test that only uses the app's shared menu, header or
    footer (not any screen's scope — the scope check's own rule), or a
    required-field test, which the field rules already write per field."""
    shared = {str(c) for f in facts for c in f.get("app_wide") or []}
    out = duplicates(tests)
    for i, t in enumerate(tests):
        if i in out or t.get("kind") == "journey":
            continue
        coverage = str(t.get("coverage") or "")
        if coverage.startswith("F-05") and coverage != FIELD_CHECK:
            out[i] = (
                "Left out before trying: required fields are checked once per field, from "
                "the form's own fields"
            )
            continue
        used = [
            _norm(str(p.get("element") or "")).rstrip(":")
            for p in t.get("path") or []
            if isinstance(p, dict)
        ]
        if shared and used and all(u in shared for u in used):
            out[i] = (
                "Left out before trying: about the app's shared menu, header or footer — "
                "not part of this screen's scope"
            )
    return out


def duplicates(tests: Sequence[dict[str, Any]]) -> dict[int, str]:
    """{index: why} for a scenario doing exactly what an earlier one does —
    same kind, start, scope item, steps (screen and element, in order) and
    values. No model; only scenarios with a path and a scope item are
    compared (without one, what it checks can't be told); field rules and the
    user's own scenarios never."""
    first: dict[tuple[Any, ...], str] = {}
    out: dict[int, str] = {}
    for i, t in enumerate(tests):
        path = [p for p in t.get("path") or [] if isinstance(p, dict)]
        coverage = _norm(str(t.get("coverage") or ""))
        if not path or not coverage or coverage == _norm(FIELD_CHECK) or t.get("kind") == "journey":
            continue
        data = t.get("data") or {}
        values = [*(data.get("finds") or []), *(data.get("types") or [])]
        key = (
            str(t.get("kind") or ""),
            str(t.get("start_screen") or ""),
            coverage,
            tuple((str(p.get("screen") or ""), _norm(str(p.get("element") or ""))) for p in path),
            tuple(sorted(_norm(str(v)) for v in values)),
        )
        if key in first:
            out[i] = f"Left out before trying: the same check as “{first[key]}”"
        else:
            first[key] = str(t.get("title") or "")
    return out


def ground(
    tests: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    records: Sequence[str] = (),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(usable, not usable) — no model. A planned scenario is usable when its
    whole flow is there before it is ever tried: each step on a screen
    Explorer saw, using an element that screen has, each move to another
    screen one Explorer saw happen, and every file it names one Explorer can
    attach. Its values are looked up on the pages and in `records` (the test
    data the app showed while exploring). Field rules (written from the
    fields), the user's own request and sign-in tests pass as they are.
    Usable ones carry `evidence` (where each value was seen, or UNSEEN: to
    check in the app); not usable ones `not_possible` and `outcome`."""
    by_screen = {str(f["name"]): str(f.get("elements") or "") for f in facts}
    leads = {
        str(f["name"]): [(str(w["action"]), str(w["to"])) for w in f.get("leads_to") or []]
        for f in facts
    }
    ok: list[dict[str, Any]] = []
    off: list[dict[str, Any]] = []
    every_page = _norm(" ".join(by_screen.values()))
    for t in tests:
        if (
            str(t.get("start_screen") or "") not in by_screen
            or t.get("coverage") == FIELD_CHECK
            or t.get("kind") == "journey"
            or t.get("signed_out")
        ):
            ok.append(t)
            continue
        problem, evidence = _flow_problem(t, by_screen, leads, records)
        problem = problem or _unknown_file(t, every_page)
        if problem:
            off.append({**t, "not_possible": problem[:300], "outcome": REJECTED})
        else:
            ok.append({**t, **({"evidence": evidence} if evidence else {})})
    return ok, off


async def ground_or_rewrite(
    journal: Journal,
    screen_info: list[dict[str, Any]],
    batch: list[dict[str, Any]],
    write: Callable[[str, list[str]], Awaitable[list[dict[str, Any]]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(usable, set aside): every scenario using only what its pages have;
    those that don't are rewritten once (`write(instruction, screens)`),
    then set aside with why (`not_possible`)."""
    records = memory.records(journal.run_id)
    ok, off = ground(batch, screen_info, records)
    if not off:
        return ok, []
    journal.event(
        "thought",
        f"{len(off)} scenario(s) use something the page doesn't have — rewriting them",
        "; ".join(f"{t.get('title')}: {t['not_possible']}" for t in off),
    )
    screens = list(dict.fromkeys(str(t.get("start_screen") or "") for t in off))
    try:
        redone = await write(regrounding_text(off, records), screens)
    except Exception:  # noqa: BLE001 — never block planning on a rewrite
        redone = []
    fixed, still = ground(redone, screen_info, records)
    # Each set aside once, as last written (with why its rewrite failed too).
    latest = {t.get("title"): t for t in off} | {t.get("title"): t for t in still}
    done = {t.get("title") for t in fixed}
    return ok + fixed, [t for title, t in latest.items() if title not in done]


def regrounding_text(off: list[dict[str, Any]], records: Sequence[str] = ()) -> str:
    """The rewrite instruction for scenarios that use what the page lacks,
    with the test data the app showed (values a rewrite may use)."""
    return (
        "These planned scenarios can't happen as written. Rewrite each so every step in "
        "'path' is on a screen given, uses an element copied exactly from THAT screen's "
        "'elements' (with 'near' when its name repeats on the page), and moves to another "
        "screen only by a way in its 'leads_to'; values in 'data.finds' must be on those "
        "screens or in the test data the app showed below — keep the same purpose and "
        "'coverage'. If the app truly has no way to do it, leave it out. Write nothing else.\n"
        + (
            "Test data the app showed while exploring: "
            + json.dumps(list(records)[:20], ensure_ascii=False)
            + "\n"
            if records
            else ""
        )
        + "\n".join(
            f"- On {t.get('start_screen')}: “{t.get('title')}” ({t.get('coverage') or ''}) — "
            f"{t['not_possible']}"
            for t in off
        )
    )


def follow_map(coverage: list[dict[str, Any]], screens: list[str]) -> str:
    """The instruction that makes a test-writing call follow the coverage map
    for `screens`: one test per item, nothing else."""
    items = [i for i in coverage if i.get("screen") in screens]
    return (
        "Coverage map — decided from all the evidence; follow it exactly. Write exactly one "
        "test for each item below, in this order: its 'id' in 'coverage', its 'evidence' as "
        "the element of the step that uses it in 'path', what it checks as the test's "
        "purpose. Write nothing else.\n" + json.dumps(items, ensure_ascii=False)[:20000]
    )


def shots_of(shots: dict[str, bytes] | None, only: list[str]) -> list[bytes] | None:
    """The screenshots of `only`, in order — all of them or none."""
    images = [shots[n] for n in only if shots and n in shots]
    return images if only and len(images) == len(only) else None


async def coverage_map(
    journal: Journal,
    asked: str,
    brief: dict[str, Any],
    screen_info: list[dict[str, Any]],
    links: list[str],
    walked: list[dict[str, Any]],
    *,
    may_save: bool,
    shots: dict[str, bytes] | None = None,
    groups: list[list[str]] | None = None,
) -> list[dict[str, Any]]:
    """What to test, decided before any test is written (brain.coverage_map),
    from all the evidence, keeping only the items whose evidence is on their
    own screen (evidenced). One decision per group of screens (Explore's many
    screens; authoring's flow is one group), several at once. Kept on the run
    and said in the feed. [] when no map could be made: the checklist is
    planned from as before."""
    groups = groups or [[str(s["name"]) for s in screen_info]]
    gate = asyncio.Semaphore(4)

    async def decide(names: list[str]) -> dict[str, Any]:
        async with gate:
            return await brain.coverage_map(
                asked,
                brief,
                [s for s in screen_info if s["name"] in names],
                links,
                walked,
                SCOPE_ITEMS,
                may_save=may_save,
                shots=shots_of(shots, names),
            )

    replies = [
        r
        for r in await asyncio.gather(*(decide(g) for g in groups), return_exceptions=True)
        if isinstance(r, dict)
    ]
    if not replies:
        journal.event("thought", "Couldn't make the coverage map — planning from the checklist")
        return []
    items, unproven = evidenced([i for r in replies for i in r["items"]], screen_info)
    if not items:
        journal.event("thought", "No coverage map came back — planning from the checklist")
        return []
    aim = " ".join(dict.fromkeys(r["aim"] for r in replies if r["aim"]))
    not_applicable = [i for r in replies for i in r["not_applicable"]]
    with Session(engine) as session:
        run = session.get(ExplorerRun, journal.run_id)
        if run is not None:
            run.insights = {
                **(run.insights or {}),
                "coverage_map": {
                    "aim": aim,
                    "items": items,
                    "not_applicable": not_applicable,
                    "no_evidence": unproven,
                },
            }
            session.add(run)
            session.commit()
    screens = len({i.get("screen") for i in items})
    journal.event(
        "summary",
        f"Coverage map: {len(items)} check(s) to test on {screens} screen(s)",
        "\n".join(
            [f"Aim: {aim}"]
            + [f"  ✓ {i.get('screen')}: {i.get('id')} {i.get('what')}" for i in items]
            + [
                f"  – {i.get('screen')}: {i.get('id')} doesn't apply — {i.get('why')}"
                for i in not_applicable + unproven
            ]
        )[:6000],
    )
    return items
