"""Stage 1 — "Get to know the app" (PLAN.md Step 1 + §4.4).

Not a crawl: Explorer reads each screen with vision, names it by meaning
(entity × kind × mode, so 1,000 customer pages are one screen), picks the
next place to look by business importance, and runs a health check along
the way. It ends by writing the App Summary for the user to confirm.
"""

import asyncio
import logging
import os
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

from explorer_core import ExplorerRun, ExplorerScreen, ExplorerTransition
from sqlmodel import Session, col, select

from explorer_worker import brain
from explorer_worker.browser import Eyes, Visit
from explorer_worker.db import engine
from explorer_worker.journal import Journal
from explorer_worker.llm import LLMError
from explorer_worker.mind import Mind
from explorer_worker.pursue import pursue
from explorer_worker.sense import (
    REQUIREMENTS_FIRST_BELOW,
    health_label,
    health_score,
    is_explorable_link,
    is_risky_label,
    is_risky_link,
    plain_label,
    url_pattern,
)
from explorer_worker.session import load_target, open_signed_in

logger = logging.getLogger(__name__)

# The first look maps the WHOLE app before the App Summary, so you can untick
# the parts to leave out (Catalog BO has ~84 screens; the old 24-screen budget
# left two thirds unseen). It stops when nothing new is left to open, or at
# these safety caps. ponytail: flat caps — a per-app estimate if very large
# apps hit them.
FIRST_LOOK_SCREENS = int(os.environ.get("EXPLORER_FIRST_LOOK_SCREENS", "150"))
# A run that starts from an earlier run's map only looks for what's new.
REVISIT_SCREENS = int(os.environ.get("EXPLORER_REVISIT_SCREENS", "40"))
LEAD_TIMEOUT_S = 180
FIRST_LOOK_MINUTES = float(os.environ.get("EXPLORER_FIRST_LOOK_MINUTES", "120"))
MENU_GROUPS = 40
# How many frontier options the "where next" call sees — the rest wait.
CHOICES_SHOWN = 20


@dataclass
class Lead:
    """A place worth looking at, seen on some screen."""

    label: str
    role: str | None
    href: str | None
    from_url: str
    from_screen: str
    why: str
    value: int
    # "visit" = go and read the screen; "flow" = start a task and walk it.
    kind: str = "visit"
    # In the app's menu/header (on every screen) rather than on this page.
    nav: bool = False
    # A collapsed menu group to open first: the item is hidden until it is.
    via: str | None = None


def done_key(label: str, from_url: str, nav: bool) -> str:
    """What "already tried" means for a label. A menu item is the same
    everywhere; a page button is only the same on that page — "Create" on
    Price points is not "Create" on Campaigns (seen on Catalog BO: one walk
    through Campaigns' Create hid every other screen's Create)."""
    return plain_label(label) if nav else f"{plain_label(label)}@{url_pattern(from_url)}"


class UnderstandStopped(Exception):
    pass


async def understand_app(run_id: uuid.UUID, heartbeat: Callable[[], None]) -> str:
    journal = Journal(run_id)
    target = load_target(run_id)
    journal.update_run(status="signing_in", headline="Signing in to the app")
    journal.event("phase", "Signing in", f"Opening {target.app_url} with the saved login")
    eyes = await open_signed_in(target, journal)
    if eyes is None:
        journal.update_run(status="failed", headline="Couldn't sign in", error="sign-in failed")
        return "failed"
    try:
        journal.event("action", "Signed in", "Got past the login screen")
        journal.update_run(status="understanding", headline="Looking around the app")
        seeded = seed_from_previous_run(run_id, journal)
        branches = await _first_look(
            eyes,
            journal,
            target.notes,
            heartbeat,
            target.app_url,
            budget=REVISIT_SCREENS if seeded else FIRST_LOOK_SCREENS,
        )
        journal.update_run(branch_points=branches)
        return await _write_summary(journal, target.notes, target.app_name, branches)
    except UnderstandStopped:
        return "stopped"  # the Stop/Pause action already logged why
    except LLMError as exc:
        journal.event("error", "The AI service didn't respond", str(exc)[:300])
        journal.update_run(
            status="failed", headline="The AI service didn't respond", error=str(exc)[:500]
        )
        return "failed"
    finally:
        await eyes.close()


async def _first_look(
    eyes: Eyes,
    journal: Journal,
    notes: str | None,
    heartbeat: Callable[[], None],
    home_url: str | None = None,
    budget: int = FIRST_LOOK_SCREENS,
) -> list[dict[str, Any]]:
    assert eyes.page is not None
    deadline = time.monotonic() + FIRST_LOOK_MINUTES * 60
    leads: list[Lead] = []
    tried: set[tuple[str, str]] = set()  # (label, from url pattern)
    seen_patterns: set[str] = set()
    walked: set[str] = set()
    branches: list[dict[str, Any]] = []

    mind = Mind(journal, notes, heartbeat, home_url=home_url)
    understood = mind.understood

    def on_screen(visit: Visit, name: str) -> None:
        # Every screen read — including during walk-throughs — feeds new leads.
        seen_patterns.add(url_pattern(visit.url))
        _collect_leads(eyes, visit, mind.last_reading, name, leads, tried, seen_patterns, walked)

    mind.on_screen = on_screen
    take_in = mind.take_in

    status, load_ms = await eyes.goto(eyes.page.url)  # re-settle wherever sign-in landed
    start = await eyes.look(eyes.page.url, status, load_ms)
    await take_in(start, reached_by="Start page")
    menu = await _menu_leads(eyes, start.url, seen_patterns, leads)
    if menu:
        leads += menu
        journal.event(
            "thought",
            f"The menu has {len(menu)} more places in it",
            "Some were folded away under menu groups. I'll look at each of them.",
        )

    already = len(understood)  # known from an earlier run: only new screens count
    while leads and len(understood) - already < budget and time.monotonic() < deadline:
        if journal.status() == "stopped":
            raise UnderstandStopped()
        leads.sort(key=lambda lead: -lead.value)
        # Map every place first; walking through forms (flows) is slow and
        # only comes once nothing else is left to open — missions do the rest.
        places = [lead for lead in leads if lead.kind != "flow"]
        options = (places or leads)[:CHOICES_SHOWN]
        choice = await brain.choose_next(
            [vars(o) for o in options], understood, budget - (len(understood) - already)
        )
        lead = options[choice["pick"]]
        leads.remove(lead)
        journal.event("thought", f"Next: {lead.label}", choice.get("thought") or lead.why)
        if lead.kind == "flow":
            if await _open(eyes, lead):
                walked.update((lead.why, done_key(lead.label, lead.from_url, lead.nav)))
                journal.event(
                    "phase",
                    f"Walking through: {lead.why}",
                    "Filling each step the way a real user would.",
                )
                walk = await pursue(
                    eyes,
                    mind,
                    journal,
                    lead.why,
                    notes,
                    heartbeat,
                    stop_requested=lambda: journal.status() == "stopped",
                )
                branches += walk.branches
            else:
                _give_up_on(lead, leads, walked)
                journal.event("thought", f"Couldn't start {lead.label}", "Moving on.")
            continue
        try:
            # A page that never finishes loading only costs this one link.
            visit = await asyncio.wait_for(_follow(eyes, lead), LEAD_TIMEOUT_S)
        except TimeoutError:
            visit = None
        if visit is None:
            _give_up_on(lead, leads, walked)
            journal.event(
                "thought",
                f"{lead.label} didn't open anything new",
                "It only expands a menu or isn't clickable from here — moving on.",
            )
            continue
        await take_in(visit, f"{lead.from_screen} → {lead.label}", action=lead.label)

    return branches


def _give_up_on(lead: Lead, leads: list[Lead], walked: set[str]) -> None:
    """A menu item that opened nothing was queued once per screen (the menu
    is on all of them): drop every copy. A page button only on its page."""
    key = done_key(lead.label, lead.from_url, lead.nav)
    walked.add(key)
    leads[:] = [o for o in leads if done_key(o.label, o.from_url, o.nav) != key]


async def _open(eyes: Eyes, lead: Lead) -> bool:
    """Get back to where the lead was seen and click it. False when the
    click didn't change anything (e.g. a menu heading that only expands)."""
    assert eyes.page is not None
    if eyes.page.url != lead.from_url:
        await eyes.goto(lead.from_url)
    before = await eyes.fingerprint()
    if not await eyes.click_text(lead.label, lead.role):
        # Folded away in a menu group: open the group, then click it.
        if not (lead.via and await eyes.click_text(lead.via)):
            return False
        before = await eyes.fingerprint()
        if not await eyes.click_text(lead.label, lead.role):
            return False
    return await eyes.wait_for_change(before, 5000)


def _readable(text: str) -> str:
    """ "User access Icon User access" (an icon's alt text read out with the
    words) is the button a person and its accessible name call "User access"."""
    match = re.fullmatch(r"(.+?)\s+\w*\s*icon\s+\1", text.strip(), re.IGNORECASE)
    return match[1] if match else text.strip()


def _is_link(item: dict[str, Any], here: str) -> bool:
    href = (item.get("href") or "").strip()
    return bool(href) and not href.lower().startswith("javascript") and url_pattern(href) != here


async def _menu_leads(
    eyes: Eyes, start_url: str, seen_patterns: set[str], leads: list[Lead]
) -> list[Lead]:
    """Menu items folded away under groups ("User access" → Users, Roles):
    invisible until the group opens, so the screen reading never offers them.
    Open each menu entry that isn't a link and keep what appears. No model."""
    assert eyes.page is not None
    here = url_pattern(start_url)
    first = await eyes.nav_items()
    seen = {plain_label(_readable(i.get("text") or "")) for i in first}
    seen |= {plain_label(lead.label) for lead in leads}
    groups = list(
        {
            plain_label(i["text"]): i
            for i in reversed(first)
            if i.get("text") and not _is_link(i, here) and not is_risky_label(i["text"])
        }.values()
    )[::-1][:MENU_GROUPS]
    found: list[Lead] = []
    for group in groups:
        group["text"] = _readable(group["text"])
        showing = len(await eyes.nav_items())
        if not await eyes.click_text(group["text"], group.get("role")):
            continue
        if url_pattern(eyes.page.url) != here:
            # A page, not a group. Its `javascript:void(0)` link is never
            # queued as a lead, so queue it here (Catalog BO's Brands, My locks).
            if url_pattern(eyes.page.url) not in seen_patterns and plain_label(
                group["text"]
            ) not in {plain_label(lead.label) for lead in leads}:
                found.append(
                    Lead(
                        group["text"],
                        group.get("role"),
                        None,
                        start_url,
                        "Menu",
                        "In the app's menu",
                        3,
                        nav=True,
                    )
                )
            await eyes.goto(start_url)
            continue
        now = await eyes.nav_items()
        if len(now) < showing:
            # A menu toggle (Catalog BO's unlabeled "Icon" button) folded the
            # whole menu away and every later click failed: unfold it again.
            await eyes.click_text(group["text"], group.get("role"))
            continue
        for item in now:
            text = _readable(item.get("text") or "")
            if not text or plain_label(text) in seen or is_risky_label(text):
                continue
            seen.add(plain_label(text))
            href = item.get("href") if _is_link(item, here) else None
            if href and (
                url_pattern(href) in seen_patterns
                or not is_explorable_link(href, eyes.origin, text)
            ):
                continue
            found.append(
                Lead(
                    text,
                    item.get("role"),
                    href,
                    start_url,
                    "Menu",
                    f"In the app's menu under {group['text']}",
                    3,
                    nav=True,
                    via=group["text"],
                )
            )
    if found and eyes.page.url != start_url:
        await eyes.goto(start_url)
    return found


async def _follow(eyes: Eyes, lead: Lead) -> Visit | None:
    assert eyes.page is not None
    if lead.href:
        status, load_ms = await eyes.goto(lead.href)
        return await eyes.look(lead.href, status, load_ms)
    # No address — it's a menu item/tab that only works by clicking.
    started = time.monotonic()
    if not await _open(eyes, lead):
        return None
    return await eyes.look(eyes.page.url, None, int((time.monotonic() - started) * 1000))


def _collect_leads(
    eyes: Eyes,
    visit: Visit,
    reading: dict[str, Any],
    screen_name: str,
    leads: list[Lead],
    tried: set[tuple[str, str]],
    seen_patterns: set[str],
    walked: set[str],
) -> None:
    inventory = visit.inventory
    by_text: dict[str, dict[str, Any]] = {}
    by_plain: dict[str, dict[str, Any]] = {}
    nav_texts = {plain_label(i.get("text") or "") for i in inventory.get("nav_items", [])}
    for item in inventory.get("links", []) + inventory.get("nav_items", []):
        text = (item.get("text") or "").strip()
        if text and text not in by_text:
            by_text[text] = item
            # The model names "💳 CARDS" as "Cards": match ignoring icons and case.
            by_plain.setdefault(plain_label(text), item)
    here = url_pattern(visit.url)
    queued = {(lead.label, url_pattern(lead.from_url)) for lead in leads}

    def add(label: str, why: str, value: int, kind: str = "visit") -> None:
        nav = plain_label(label) in nav_texts
        if (
            not label
            or done_key(label, visit.url, nav) in walked
            or (label, here) in tried
            or (label, here) in queued
        ):
            return
        item = by_text.get(label) or by_plain.get(plain_label(label), {})
        href = item.get("href")
        if href:
            href = urljoin(visit.url, href)
        if (
            href
            and "#" in href
            and urlsplit(href)._replace(fragment="") == urlsplit(visit.url)._replace(fragment="")
            and url_pattern(href) == here
        ):
            # `href="#"` / `#anchor` on this same page: a JS-driven button
            # (opens a dialog, a panel) — it only works by clicking.
            href = None
        if is_risky_link(label, href) if href else is_risky_label(label):
            return
        if href:
            if (
                not is_explorable_link(href, eyes.origin, label)
                or url_pattern(href) in seen_patterns
            ):
                return
            if any(lead.href and url_pattern(lead.href) == url_pattern(href) for lead in leads):
                return
        tried.add((label, here))
        leads.append(
            Lead(
                label,
                item.get("role"),
                None if kind == "flow" else href,
                visit.url,
                screen_name,
                why,
                max(1, min(5, value)),
                kind,
                nav,
            )
        )

    for suggestion in reading["worth_exploring"][:25]:
        if isinstance(suggestion, dict):
            value = suggestion.get("value")
            add(
                str(suggestion.get("label") or "").strip(),
                str(suggestion.get("why") or ""),
                value if isinstance(value, int) else 2,
            )
    for flow in reading["starts_flow"][:5]:
        if isinstance(flow, dict) and flow.get("goal") and flow["goal"] not in walked:
            value = flow.get("value")
            # Tasks are the heart of the app — rank them above plain navigation.
            add(
                str(flow.get("label") or "").strip(),
                str(flow["goal"]),
                (value if isinstance(value, int) else 4) + 1,
                kind="flow",
            )
    # Safety net: plain links the model didn't mention still get a low-priority slot.
    for text, item in list(by_text.items())[:60]:
        if item.get("href"):
            add(text, "A link on this screen", 1)


async def _write_summary(
    journal: Journal, notes: str | None, app_name: str, branches: list[dict[str, Any]]
) -> str:
    screens = journal.screen_rows()
    issues = journal.health_rows()
    # Health = how stable the app is technically. "Possible bugs" (things
    # that look wrong by common sense) and wording are findings, not instability.
    technical = [i for i in issues if i.kind not in ("looks_wrong", "wording")]
    possible_bugs = len(issues) - len(technical)
    score = health_score([(i.severity, i.occurrences) for i in technical], len(screens))
    requirements_first = score < REQUIREMENTS_FIRST_BELOW
    label = health_label(score)
    journal.update_run(
        health_score=score,
        requirements_first=requirements_first,
        status="summarizing",
        headline="Writing the App Summary",
    )
    journal.event(
        "health",
        f"Health check: {score}/100 — {label}",
        (
            f"{len(technical)} technical problem(s) across {len(screens)} screens, plus "
            f"{possible_bugs} possible bug(s). The app looks unstable, so I'll "
            "trust your documents and answers over what the app shows."
            if requirements_first
            else f"{len(technical)} technical problem(s) across {len(screens)} screens, plus "
            f"{possible_bugs} possible bug(s) to review."
        ),
    )
    # Nothing to click or fill anywhere: a summary now would be invented from
    # the app's name alone (seen on BM Catalog: a blank home page became a
    # full catalog-management summary). Say so instead.
    if len(screens) < 2 and not any(s.actions or s.fields for s in screens):
        problems = "; ".join(i.title for i in technical[:3])
        detail = (
            f"After signing in I only saw “{screens[0].name if screens else 'an empty page'}”, "
            "with nothing to click or fill in, so I can't learn how the app works."
            + (f" What went wrong there: {problems}." if problems else "")
            + " Please check the app opens normally in a browser, then start again."
        )
        journal.event("error", "I couldn't get into the app", detail)
        journal.update_run(
            status="failed", headline="Couldn't get into the app", error=detail[:500]
        )
        return "failed"
    journal.event(
        "phase", "Writing the App Summary", "Putting together what I learned about the business"
    )
    brief = await brain.summarize(
        [
            {
                "name": s.name,
                "business_thing": s.entity,
                "kind": s.view_kind,
                "mode": s.mode,
                "purpose": s.purpose,
                "fields": [f.get("label") for f in s.fields][:20],
                "actions": [a.get("label") for a in s.actions][:20],
                "maybe_hidden": s.hidden_hints,
            }
            for s in screens
        ],
        {
            "score": score,
            "label": label,
            "problems": [
                {"kind": i.kind, "severity": i.severity, "title": i.title, "times": i.occurrences}
                for i in issues
            ][:40],
        },
        notes,
        app_name,
        branches,
    )
    journal.update_run(
        brief=brief, status="awaiting_confirmation", headline="Please review the App Summary"
    )
    await asyncio.to_thread(
        journal.email_starter,
        "Please check what Explorer learned",
        "Explorer has finished its first look around the app and wrote a one-page summary. "
        "It is waiting for you to read it, correct anything wrong and confirm it before it "
        "carries on testing.",
    )
    journal.event(
        "summary", "App Summary is ready", brief.get("one_liner") or "Please review and confirm it."
    )
    return "awaiting_confirmation"


def seed_from_previous_run(run_id: uuid.UUID, journal: Journal) -> int:
    """Start from the latest earlier run's map of this app (Stage 6: re-runs
    check what changed instead of starting over). Returns screens copied."""
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None:
            return 0
        own = len(
            session.exec(select(ExplorerScreen.id).where(ExplorerScreen.run_id == run_id)).all()
        )
        if own:
            return own  # a resumed run already has its map: copying again would double it
        previous = session.exec(
            select(ExplorerRun)
            .where(
                ExplorerRun.application_id == run.application_id,
                ExplorerRun.id != run.id,
                col(ExplorerRun.created_at) < run.created_at,
                # An authoring run saw only its request's screens: never a map to start from.
                col(ExplorerRun.prompt).is_(None),
            )
            .order_by(col(ExplorerRun.created_at).desc())
        ).all()
        source = next(
            (
                p
                for p in previous
                if session.exec(
                    select(ExplorerScreen.id).where(ExplorerScreen.run_id == p.id)
                ).first()
            ),
            None,
        )
        if source is None:
            return 0
        old_screens = session.exec(
            select(ExplorerScreen).where(
                ExplorerScreen.run_id == source.id, col(ExplorerScreen.condition).is_(None)
            )
        ).all()
        mapping: dict[uuid.UUID, uuid.UUID] = {}
        for old in old_screens:
            copy = ExplorerScreen(
                **old.model_dump(exclude={"id", "run_id", "created_at", "visits", "reached_by"}),
                run_id=run_id,
                reached_by="Known from the previous run",
            )
            session.add(copy)
            mapping[old.id] = copy.id
        for edge in session.exec(
            select(ExplorerTransition).where(ExplorerTransition.run_id == source.id)
        ).all():
            if edge.from_screen_id in mapping and edge.to_screen_id in mapping:
                session.add(
                    ExplorerTransition(
                        run_id=run_id,
                        from_screen_id=mapping[edge.from_screen_id],
                        to_screen_id=mapping[edge.to_screen_id],
                        action=edge.action,
                    )
                )
        run.branch_points = list(source.branch_points or [])
        session.add(run)
        session.commit()
    journal.event(
        "phase",
        f"Starting from what I learned last time: {len(mapping)} screens",
        "I'll only look for what's new or changed, so this run is much faster.",
    )
    return len(mapping)
