"""Stage 3 — hunting hidden screens on purpose (PLAN.md §5, ways 1-3).

After the missions, Explorer revisits screens it knows and tries to make
parts appear that only show up sometimes:
1. choices on a form — pick each option of every dropdown / radio group and
   watch which fields appear ("Married" shows the spouse step);
2. amounts — try small to very large numbers and watch for new sections or
   messages (an approval panel above a threshold);
3. what the server sends back — inside its own browser only, pretend the
   server returned nothing, or an error, and see what the app shows.
   These are labelled Simulated; the real server is never touched.
Each discovery is a hidden screen on the App Map with its condition.
"""

import json
import re
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from explorer_core import ExplorerScreen
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Route

from explorer_worker.browser import Eyes
from explorer_worker.journal import Journal
from explorer_worker.sense import url_pattern
from explorer_worker.session import load_target, open_signed_in

HUNT_MINUTES = 25
MAX_FORM_SCREENS = 10
MAX_DATA_SCREENS = 10
MAX_GROUPS = 4
MAX_OPTIONS = 5
AMOUNTS = ["1", "999", "15000", "1000000"]

_CHOICE_GROUPS_JS = r"""
() => {
  const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const text = (el) => (el ? (el.innerText || el.textContent || '') : '').replace(/\s+/g, ' ').trim();
  const question = (el) => {
    const box = el.closest('fieldset, [role=radiogroup], [data-role=form-field], .form-group, .app-radioset');
    if (!box) return '';
    const legend = box.querySelector('legend, label, .control-label, .app-label');
    return text(legend).slice(0, 80);
  };
  const groups = [];
  const byName = {};
  for (const r of document.querySelectorAll('input[type=radio]')) {
    const label = text(r.closest('label')) || r.value;
    if (!label) continue;
    const name = r.name || question(r);
    if (!byName[name]) { byName[name] = { kind: 'radio', name, question: question(r), options: [] }; groups.push(byName[name]); }
    if (!byName[name].options.includes(label)) byName[name].options.push(label);
  }
  document.querySelectorAll('select').forEach((s, index) => {
    if (!visible(s)) return;
    const opts = [...s.options].map(o => o.text.trim()).filter(t => t && !/^(select|choose|--)/i.test(t));
    const label = s.id ? text(document.querySelector(`label[for="${CSS.escape(s.id)}"]`)) : '';
    groups.push({ kind: 'select', name: String(index), question: label || question(s), options: opts });
  });
  return groups.filter(g => g.options.length > 1);
}
"""

_FIELD_LABELS_JS = r"""
() => {
  const out = new Set();
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden'; };
  for (const f of document.querySelectorAll('input:not([type=hidden]), select, textarea')) {
    if (!visible(f)) continue;
    let label = '';
    if (f.id) { const l = document.querySelector(`label[for="${CSS.escape(f.id)}"]`); if (l) label = l.innerText; }
    if (!label) { const w = f.closest('label'); if (w) label = w.innerText; }
    label = label || f.getAttribute('aria-label') || f.getAttribute('placeholder') || f.name || '';
    label = label.replace(/\s+/g, ' ').trim().slice(0, 80);
    if (label) out.add(label);
  }
  for (const h of document.querySelectorAll('h1, h2, h3, h4, legend, [role=alert]')) {
    if (visible(h)) { const t = (h.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 80); if (t) out.add(t); }
  }
  return [...out];
}
"""

_NUMBER_FIELDS_JS = r"""
() => {
  const out = [];
  const words = /(amount|price|value|sum|cost|limit|total|age|quantity|qty|salary|income|premium|deductible|claim)/i;
  for (const f of document.querySelectorAll('input')) {
    const r = f.getBoundingClientRect(); if (!(r.width > 0 && r.height > 0) || f.readOnly || f.disabled) continue;
    let label = '';
    if (f.id) { const l = document.querySelector(`label[for="${CSS.escape(f.id)}"]`); if (l) label = l.innerText; }
    label = (label || f.getAttribute('aria-label') || f.getAttribute('placeholder') || f.name || '').replace(/\s+/g, ' ').trim();
    if (f.type === 'number' || words.test(label)) out.push(label.slice(0, 80));
  }
  return out.filter(Boolean).slice(0, 3);
}
"""


_SIMULATED = {
    "empty": ("the server returns no records", "no data"),
    "error": ("the server has a problem", "server error"),
    "flags": ("optional features are switched on", "features switched on"),
    "future": ("it is a year from now", "a year from now"),
}
_SWITCH = re.compile(r"(feature|flag|beta|enable|enabled|show|visible|allow)", re.IGNORECASE)


def switched_on(data: Any) -> tuple[Any, int]:
    """Turn every 'off' feature-looking switch in a server answer on.
    Returns the changed answer and how many switches were flipped."""
    if isinstance(data, list):
        flipped = 0
        out = []
        for item in data:
            changed, n = switched_on(item)
            out.append(changed)
            flipped += n
        return out, flipped
    if isinstance(data, dict):
        flipped = 0
        result: dict[str, Any] = {}
        for key, value in data.items():
            if value is False and _SWITCH.search(key):
                result[key] = True
                flipped += 1
            else:
                result[key], n = switched_on(value)
                flipped += n
        return result, flipped
    return data, 0


def emptied(data: Any) -> Any:
    """The same answer from the server, but with no records in it."""
    if isinstance(data, list):
        return []
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, list):
                out[key] = []
            elif isinstance(value, dict):
                out[key] = emptied(value)
            elif key.lower() in (
                "total",
                "totalelements",
                "count",
                "totalcount",
                "totalpages",
                "numberofelements",
                "size",
            ) and isinstance(value, int):
                out[key] = 0
            else:
                out[key] = value
        return out
    return data


async def hunt(run_id: uuid.UUID, heartbeat: Callable[[], None]) -> int:
    journal = Journal(run_id)
    if journal.status() == "stopped":
        return 0
    target = load_target(run_id)
    screens = journal.screen_rows()
    forms = [s for s in screens if s.view_kind in ("form", "wizard") and not s.condition][
        :MAX_FORM_SCREENS
    ]
    data = [
        s
        for s in screens
        if s.view_kind in ("list", "search", "dashboard", "detail") and not s.condition
    ][:MAX_DATA_SCREENS]
    journal.update_run(status="hunting", headline="Hunting for hidden screens")
    journal.event(
        "phase",
        "Hunting for hidden screens",
        f"Trying every choice on {len(forms)} forms and pretending the server sends back nothing or an error on {len(data)} screens.",
    )
    eyes = await open_signed_in(target, journal)
    if eyes is None:
        return 0
    found = 0
    deadline = time.monotonic() + HUNT_MINUTES * 60
    try:
        for screen in forms:
            if time.monotonic() > deadline or journal.status() == "stopped":
                break
            heartbeat()
            found += await _probe_choices(eyes, journal, screen, heartbeat)
            found += await _probe_amounts(eyes, journal, screen, heartbeat)
        for screen in data:
            if time.monotonic() > deadline or journal.status() == "stopped":
                break
            heartbeat()
            for mode in ("empty", "error", "flags", "future"):
                found += await _shaped_visit(eyes, journal, screen, mode)
    finally:
        await eyes.close()
    journal.event(
        "summary",
        f"Hidden-screen hunt: {found} found",
        "Each one is on the App Map with what makes it appear.",
    )
    return found


async def _labels(eyes: Eyes) -> set[str]:
    assert eyes.page is not None
    try:
        return set(await eyes.page.evaluate(_FIELD_LABELS_JS))
    except PlaywrightError:
        return set()


def _record(
    journal: Journal,
    base: ExplorerScreen,
    key: str,
    name: str,
    condition: str,
    action: str,
    new_parts: list[str],
    shot: bytes,
    url: str,
) -> bool:
    shot_id = journal.shot(shot)
    variant_id, is_new = journal.upsert_screen(
        f"{base.signature}|{key}",
        {
            "name": name[:120],
            "entity": base.entity,
            "view_kind": base.view_kind,
            "mode": base.mode,
            "purpose": f"Shows: {', '.join(new_parts[:8])}" if new_parts else base.purpose,
            "url": url,
            "url_pattern": f"{base.url_pattern}#{key}",
            "fields": [{"label": p} for p in new_parts[:20]],
            "actions": [],
            "hidden_hints": [],
            "reached_by": f"{base.name} → {action}",
            "shot_id": shot_id,
            "condition": condition,
        },
    )
    if is_new:
        journal.transition(base.id, variant_id, action)
        journal.event(
            "screen",
            f"Hidden screen found: {name}"[:300],
            f"Only appears when {condition}."
            + (f" It adds: {', '.join(new_parts[:6])}." if new_parts else ""),
            shot_id,
        )
    return is_new


async def _probe_choices(
    eyes: Eyes, journal: Journal, screen: ExplorerScreen, heartbeat: Callable[[], None]
) -> int:
    assert eyes.page is not None
    await eyes.goto(screen.url)
    base = await _labels(eyes)
    try:
        groups = (await eyes.page.evaluate(_CHOICE_GROUPS_JS))[:MAX_GROUPS]
    except PlaywrightError:
        return 0
    found = 0
    for group in groups:
        question = group.get("question") or "a choice"
        for option in group["options"][:MAX_OPTIONS]:
            heartbeat()
            await eyes.goto(screen.url)
            if group["kind"] == "select":
                try:
                    await (
                        eyes.page.locator("select")
                        .nth(int(group["name"]))
                        .select_option(label=option, timeout=4000)
                    )
                except PlaywrightError:
                    continue
            elif not await eyes.choose(question, option):
                continue
            await eyes.settle(3000)
            new_parts = sorted((await _labels(eyes)) - base)
            if new_parts:
                visit = await eyes.look(eyes.page.url, None, 0)
                found += _record(
                    journal,
                    screen,
                    f"{question}={option}",
                    f"{screen.name} — {option}",
                    f"“{question}” is “{option}”",
                    f"Choose {option}",
                    new_parts,
                    visit.shot,
                    eyes.page.url,
                )
    return found


async def _probe_amounts(
    eyes: Eyes, journal: Journal, screen: ExplorerScreen, heartbeat: Callable[[], None]
) -> int:
    assert eyes.page is not None
    await eyes.goto(screen.url)
    try:
        fields = await eyes.page.evaluate(_NUMBER_FIELDS_JS)
    except PlaywrightError:
        return 0
    found = 0
    for field in fields:
        seen: dict[str, frozenset[str]] = {}
        base = await _labels(eyes)
        for amount in AMOUNTS:
            heartbeat()
            await eyes.goto(screen.url)
            if not await eyes.fill_field(field, amount):
                break
            await eyes.page.keyboard.press("Tab")
            await eyes.settle(2500)
            new_parts = frozenset((await _labels(eyes)) - base)
            if new_parts and new_parts not in seen.values():
                seen[amount] = new_parts
                visit = await eyes.look(eyes.page.url, None, 0)
                found += _record(
                    journal,
                    screen,
                    f"{field}={amount}",
                    f"{screen.name} — {field} {amount}",
                    f"“{field}” is {int(amount):,}",
                    f"Enter {amount}",
                    sorted(new_parts),
                    visit.shot,
                    eyes.page.url,
                )
    return found


async def _shaped_visit(eyes: Eyes, journal: Journal, screen: ExplorerScreen, mode: str) -> int:
    """Revisit a screen while this browser pretends the server answered with
    no records / an error. Simulated — nothing real is changed."""
    page = eyes.page
    assert page is not None
    await eyes.goto(screen.url)
    normal = set((await page.evaluate("() => document.body.innerText")).split("\n"))

    async def handler(route: Route) -> None:
        if route.request.resource_type not in ("xhr", "fetch"):
            await route.continue_()
            return
        if mode == "future":
            await route.continue_()
            return
        if mode == "error":
            await route.fulfill(
                status=500, content_type="application/json", body=json.dumps({"error": "simulated"})
            )
            return
        try:
            response = await route.fetch()
            body = await response.json()
        except Exception:  # not JSON — leave it alone
            await route.continue_()
            return
        if mode == "flags":
            changed, flipped = switched_on(body)
            flips[0] += flipped
            await route.fulfill(response=response, json=changed)
            return
        await route.fulfill(response=response, json=emptied(body))

    flips = [0]
    if mode == "future":
        # A fresh tab whose clock is a year ahead (a clock can't be wound back).
        page = await page.context.new_page()
        await page.clock.install(time=datetime.now(UTC) + timedelta(days=400))
        eyes = Eyes(eyes.origin, page=page)
    await page.route("**/*", handler)
    try:
        await eyes.goto(screen.url)
        await eyes.settle(4000)
        visit = await eyes.look(page.url, None, 0)
        text = await page.evaluate("() => document.body.innerText")
    except PlaywrightError:
        return 0
    finally:
        await page.unroute("**/*", handler)
        if mode == "future":
            await page.close()
    if mode == "flags" and not flips[0]:
        return 0  # nothing that looked like a feature switch
    if url_pattern(visit.url) != url_pattern(screen.url):
        # The app left the screen (to home, a denied page, sign-in): this is
        # not a version of it. Seen on Catalog BO: 22 "hidden screens" that
        # were home or Access denied.
        return 0
    shaped = [line.strip() for line in text.split("\n") if line.strip()]
    new_lines = [line for line in shaped if line not in normal][:8]
    if not new_lines and len(shaped) > 3:
        return 0  # looked the same — nothing hidden here
    if mode == "error" and len(" ".join(shaped)) < 40:
        journal.health_issue(
            "looks_wrong",
            "medium",
            f"{screen.name} goes blank when the server has a problem",
            "Users should see a friendly message instead of an empty screen (simulated server error).",
            screen.url,
            journal.shot(visit.shot),
        )
        return 0  # a bug, not a hidden screen
    label, short = _SIMULATED[mode]
    return int(
        _record(
            journal,
            screen,
            f"sim:{mode}",
            f"{screen.name} — {short}",
            f"Simulated: {label}",
            f"Simulated: {short}",
            new_lines or ["(screen is blank)"],
            visit.shot,
            page.url,
        )
    )
