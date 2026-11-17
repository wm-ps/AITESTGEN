"""Reading a form's own validation messages, on every form Explorer understands.

Many apps check fields in their own code — no `required`, `maxlength` or
`pattern` on the field — and say so only once a value is wrong: "Last name
is required" or "Maximum 50 characters" appears under the field. So on each
new form (first look and missions alike), right where it is, Explorer touches
every text field the way a careless user would (leave it empty, one
character, far too long, symbols, a broken email, numbers out of range),
moves on with Tab, records the message that appeared next to that field, and
then puts back what the walk had typed. field_checks turns each message into
a scenario that expects it word for word. Search and lookup boxes (Owner,
Account) are skipped: what shows under them is suggestions, not messages.

Many apps only check on Save. On a test environment (and only there) Explorer
then also presses Save once per kind of wrong value — empty, too long, symbols,
… — and reads each field's message; if the form saves anyway it goes back.
"""

import re
import time
import uuid
from collections.abc import Callable
from typing import Any

from explorer_core import ExplorerScreen
from playwright.async_api import Error as PlaywrightError
from sqlmodel import Session

from explorer_worker.browser import LOOKUP_JS, SUGGESTIONS, Eyes, locate
from explorer_worker.db import engine
from explorer_worker.journal import Journal
from explorer_worker.sense import looks_final, may_commit

# The texts shown next to one field: everything visible inside its own
# wrapper (the largest ancestor holding no other form field), what it points
# to with aria-describedby, and alerts anywhere on the page.
# ponytail: a field whose wrapper also holds another field (two inputs in one
# row box) only gets its aria-describedby and alerts read.
_MESSAGES_JS = r"""
(e) => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const norm = (t) => (t || '').replace(/\s+/g, ' ').trim();
  const controls = 'input:not([type=hidden]), select, textarea';
  let box = e;
  for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) {
    if ([...p.querySelectorAll(controls)].filter(vis).length > 1) break;
    box = p;
  }
  const out = new Set();
  const add = (el) => { const t = norm(el.innerText); if (t && t.length <= 200) out.add(t); };
  for (const el of box.querySelectorAll('*')) {
    if (!vis(el) || el.closest('label')) continue;
    if (el.matches('input, select, textarea, option, button')) continue;
    if ([...el.children].some((c) => norm(c.innerText))) continue;  // leaf texts only
    add(el);
  }
  for (const id of (e.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean)) {
    const d = document.getElementById(id); if (d && vis(d)) add(d);
  }
  for (const a of document.querySelectorAll('[role=alert], [aria-live=assertive]')) {
    if (vis(a)) add(a);
  }
  return [...out];
}
"""

_LABEL_NOISE = re.compile(r"\s*(\*|\(required\))\s*$", re.I)
# A form's whole probe, at most (a 16-field form once took 7 minutes).
PROBE_SECONDS = 90
_COUNTER = re.compile(r"[\d\s/]+(characters?|chars?)?", re.I)
_TEXT_TYPES = {None, "", "text", "email", "number", "textarea", "tel", "url", "search", "other"}
_LONG = "a" * 300


def probes(field: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(kind, what is typed, how a person would describe it) for one field."""
    # The field's own kind first: "a" in an email box shows the email message,
    # which belongs to the email check, not to "too short".
    label = str(field.get("label") or "").lower()
    out = [("required", "", "left empty")]
    if field.get("type") == "email" or "mail" in label:
        out.append(("email", "not-an-email", "an address without an @ sign (not-an-email)"))
    if field.get("type") == "number" or field.get("min") or field.get("max"):
        out += [("below", "-1", "a negative number (-1)"), ("above", "99999999999", "99999999999")]
    return out + [
        ("short", "a", "a single character"),
        ("long", _LONG, "300 characters"),
        ("format", "abc!@#$", "letters and symbols (abc!@#$)"),
    ]


def probed_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        f
        for f in fields
        if f.get("label")
        and f.get("type") in _TEXT_TYPES
        and not re.search(r"password|search", str(f["label"]), re.I)
    ]


async def _texts(eyes: Eyes, spec: dict[str, Any]) -> list[str]:
    assert eyes.page is not None
    try:
        target = locate(eyes.page, spec).filter(visible=True).first
        return list(await target.evaluate(_MESSAGES_JS))
    except PlaywrightError:
        return []


async def _is_lookup(eyes: Eyes, spec: dict[str, Any]) -> bool:
    """A search or lookup box: its own markings, or suggestions showing up
    once something is typed."""
    assert eyes.page is not None
    target = locate(eyes.page, spec).filter(visible=True).first
    try:
        if await target.evaluate(LOOKUP_JS):
            return True
        await target.fill("x", timeout=4000)
        await eyes.page.wait_for_timeout(800)
        shown = await eyes.page.locator(SUGGESTIONS).filter(visible=True).count()
        await target.fill("", timeout=4000)
        if shown:
            await eyes.page.keyboard.press("Escape")
        return bool(shown)
    except PlaywrightError:
        return True


async def _after(eyes: Eyes, spec: dict[str, Any], value: str) -> list[str]:
    """Type `value` (an empty value: type, then clear), Tab away, and read."""
    assert eyes.page is not None
    target = locate(eyes.page, spec).filter(visible=True).first
    await target.fill(value or "x", timeout=4000)
    if not value:
        await target.fill("", timeout=4000)
    await eyes.page.keyboard.press("Tab")
    await eyes.settle(1500)
    return await _texts(eyes, spec)


async def read_messages(eyes: Eyes, label: str, field: dict[str, Any]) -> list[dict[str, str]]:
    """The message each wrong value made appear next to this field."""
    page = eyes.page
    assert page is not None
    if not await eyes.fill_field(label, ""):
        return []
    spec = eyes.last_locator
    if spec is None or await _is_lookup(eyes, spec):
        return []
    untouched = set(await _texts(eyes, spec))
    found: list[dict[str, str]] = []
    for kind, value, entered in probes(field):
        before = untouched if kind == "required" else set(await _texts(eyes, spec))
        try:
            after = await _after(eyes, spec, value)
        except PlaywrightError:  # e.g. a number box refuses letters
            continue
        # A character counter ("300 / 50") is not a message; one already
        # read for another wrong value belongs to that check.
        seen = {m["message"] for m in found}
        if new := _new_message(after, before, seen):
            found.append({"probe": kind, "entered": entered, "message": new})
        try:  # empty again, and Tab so the field's message settles back
            await locate(page, spec).filter(visible=True).first.fill("", timeout=4000)
            await page.keyboard.press("Shift+Tab")
            await page.keyboard.press("Tab")
            await eyes.settle(800)
        except PlaywrightError:
            break
    return found


def _new_message(after: list[str], before: set[str], seen: set[str]) -> str | None:
    """The first text that appeared, if it isn't a character counter ("300 /
    50") or a message already credited to another wrong value."""
    return next((t for t in after if t not in before | seen and not _COUNTER.fullmatch(t)), None)


async def _save_button(eyes: Eyes) -> Any:
    """The form's own Save/Submit/Create button (never Delete, Pay, …)."""
    assert eyes.page is not None
    buttons = eyes.page.get_by_role("button").filter(visible=True)
    try:
        for i in range(min(await buttons.count(), 40)):
            label = " ".join((await buttons.nth(i).inner_text(timeout=1000)).split())
            if label and looks_final(label) and may_commit(label, True):
                return buttons.nth(i)
    except PlaywrightError:
        pass
    return None


async def read_on_save(
    eyes: Eyes, fields: list[dict[str, Any]]
) -> tuple[dict[str, list[dict[str, str]]], bool]:
    """Messages the app shows only when Save is pressed: one press per kind
    of wrong value, typed into every field it applies to at once (empty
    first). Test environments only — a form that saves anyway made a record;
    Explorer then goes back and stops. The fields are left empty. Returns
    the messages, and whether the form saved (the browser went back)."""
    page = eyes.page
    assert page is not None
    save = await _save_button(eyes)
    if save is None:
        return {}, False
    boxes: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for field in probed_fields(fields):
        label = str(field["label"])
        if await eyes.fill_field(label, "") and eyes.last_locator:
            if not await _is_lookup(eyes, eyes.last_locator):
                boxes[label] = (field, eyes.last_locator)
    found: dict[str, list[dict[str, str]]] = {}
    for kind in ("required", "email", "below", "above", "short", "long", "format"):
        typed: list[tuple[str, dict[str, Any], str]] = []
        for label, (field, spec) in boxes.items():
            for k, value, entered in probes(field):
                if k != kind:
                    continue
                try:
                    await locate(page, spec).filter(visible=True).first.fill(value, timeout=4000)
                    typed.append((label, spec, entered))
                except PlaywrightError:  # a number box refuses letters
                    pass
        if not typed:
            continue
        before = {label: set(await _texts(eyes, spec)) for label, spec, _ in typed}
        url = page.url
        heard = len(eyes.messages)
        try:
            await save.click(timeout=4000)
            await eyes.settle(1500)
            saved = page.url != url or not await save.is_visible()
        except PlaywrightError:
            saved = True
        if saved:  # the app took it: nothing more to read on this form
            await page.go_back()
            await eyes.settle()
            return found, True
        # Shown at the top of the form, or as a toast: the app's messages
        # since the press (browser.Eyes.messages), credited to the field each names.
        said = eyes.messages[heard:] if len(eyes.messages) >= heard else list(eyes.messages)
        for label, spec, entered in typed:
            seen = {m["message"] for m in found.get(label, [])}
            name = _LABEL_NOISE.sub("", label).strip().lower()
            if new := _new_message(await _texts(eyes, spec), before[label], seen) or next(
                (m for m in said if name and name in m.lower() and m not in seen), None
            ):
                found.setdefault(label, []).append(
                    {"probe": kind, "entered": entered, "message": new}
                )
        for _, spec, _ in typed:  # empty again for the next kind
            try:
                await locate(page, spec).filter(visible=True).first.fill("", timeout=4000)
            except PlaywrightError:
                pass
    return found, False


# The values already in the form's text boxes (by position), so a probe on a
# form the walk is filling in leaves it as it found it.
_VALUES_JS = """() => [...document.querySelectorAll('input:not([type=hidden]), textarea')]
  .map((e, i) => [i, e.value, e.type]).filter(([, v, t]) => v && t !== 'password'
    && !['checkbox', 'radio', 'file', 'submit', 'button'].includes(t))"""
_BOXES = "input:not([type=hidden]), textarea"
# Screens whose fields are probed: forms and wizard steps (a list's search
# box, a sign-in page or a settings builder has no rules worth provoking).
PROBED_KINDS = ("form", "wizard")


async def probe_here(
    eyes: Eyes,
    journal: Journal,
    screen_id: uuid.UUID,
    name: str,
    fields: list[dict[str, Any]],
    heartbeat: Callable[[], None],
    may_save: bool = False,
) -> int:
    """On the form the browser shows now (just understood, mid-walk): read
    every text field's messages, keep them with the field
    (ExplorerScreen.fields[i]["messages"]), then put back what was typed.
    `may_save` (a test environment): also read what pressing Save says.
    Returns how many messages were read."""
    page = eyes.page
    assert page is not None
    try:
        typed = await page.evaluate(_VALUES_JS)
    except PlaywrightError:
        return 0
    found: dict[str, list[dict[str, str]]] = {}
    deadline = time.monotonic() + PROBE_SECONDS
    left = False
    if may_save:  # first: a few presses read what most forms say (and fast)
        heartbeat()
        found, left = await read_on_save(eyes, fields)
    for field in [] if left else probed_fields(fields):
        if time.monotonic() > deadline:
            break  # what was read so far is kept
        heartbeat()
        label = str(field["label"])
        have = {m["message"] for m in found.get(label, [])}
        messages = [m for m in await read_messages(eyes, label, field) if m["message"] not in have]
        if messages:
            found.setdefault(label, []).extend(messages)
    for index, value, _ in [] if left else typed:  # as it was before the probe
        try:
            await page.locator(_BOXES).nth(int(index)).fill(str(value), timeout=3000)
        except PlaywrightError:
            continue
    if found:
        _save_messages(screen_id, found)
        journal.event(
            "thought",
            f"Read {sum(map(len, found.values()))} field message(s) on {name}",
            "; ".join(f"{label}: “{m['message']}”" for label, ms in found.items() for m in ms)[
                :600
            ],
        )
    return sum(map(len, found.values()))


def _save_messages(screen_id: uuid.UUID, found: dict[str, list[dict[str, str]]]) -> None:
    with Session(engine) as session:
        row = session.get(ExplorerScreen, screen_id)
        if row is None:
            return
        row.fields = [
            {**f, "messages": found[str(f.get("label"))]} if str(f.get("label")) in found else f
            for f in row.fields or []
        ]
        session.add(row)
        session.commit()
