"""Pursue a goal like a careful user: on each screen decide what to enter and
what to press (or which known screen to jump to), do it, and read where it
led. Used for Stage 1 walk-throughs and Stage 2 missions. Fills with the
user's test data or realistic made-up data, records choices that probably
change the path (hidden branches), and never presses a final
Submit/Send/Pay — that needs the human (PLAN.md §11)."""

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from explorer_core import ExplorerScreen
from sqlmodel import Session, col, select

from explorer_worker import brain
from explorer_worker.browser import Eyes
from explorer_worker.db import engine
from explorer_worker.goal import stops_walk
from explorer_worker.journal import Journal
from explorer_worker.mind import Mind
from explorer_worker.samples import sample_file
from explorer_worker.sense import (
    going_in_circles,
    is_risky_link,
    is_sign_out,
    looks_final,
    may_commit,
    needs_human_ok,
    page_link,
    route_starts_at_entry,
    same_place,
)

MAX_RETRIES_ON_SAME_STEP = 2
# Icon alt text read out with a label: "Logout Icon Logout" -> "Logout".
_ICON_TEXT = re.compile(r"\b\w+ Icon\b\s*", re.I)
_ASKS_FOR_FILE = re.compile(r"\b(files?|images?|photos?|pictures?|uploads?|attachments?)\b", re.I)

# The shortest recorded way from an entry point to each screen of a run,
# replayed (no model) to fast-forward a mission or scenario to where it
# starts. Kept on the screen's own row — keyed by the stored screen, never by
# the name a model gave it on one visit, and surviving worker restarts.


def path_to(run_id: uuid.UUID, screen: str | None) -> list[dict[str, str]] | None:
    """The shortest saved route to the screen called `screen`, if any."""
    if not screen:
        return None
    with Session(engine) as session:
        routes = session.exec(
            select(ExplorerScreen.route).where(
                ExplorerScreen.run_id == run_id,
                ExplorerScreen.name == screen,
                col(ExplorerScreen.route).is_not(None),
            )
        ).all()
    routes = [r for r in routes if r]
    return [dict(step) for step in min(routes, key=len)] if routes else None


def edge_reached(fit: str | None, obey_goal: bool) -> bool:
    """Does reaching a screen with this place against the run's Goal end the
    walk? A mission the user added themselves (obey_goal=False) goes on."""
    return obey_goal and stops_walk(fit)


def is_shorter(path: list[dict[str, Any]], known: list[dict[str, Any]] | None) -> bool:
    return known is None or len(path) < len(known)


def remember_route(screen_id: uuid.UUID, path: list[dict[str, Any]]) -> None:
    with Session(engine) as session:
        screen = session.get(ExplorerScreen, screen_id)
        if screen is not None and is_shorter(path, screen.route):
            screen.route = [dict(step) for step in path]
            session.add(screen)
            session.commit()


def forget_route(run_id: uuid.UUID, screen: str) -> None:
    """A saved route that no longer replays: the next walk in records a new one."""
    with Session(engine) as session:
        for row in session.exec(
            select(ExplorerScreen).where(
                ExplorerScreen.run_id == run_id, ExplorerScreen.name == screen
            )
        ).all():
            row.route = None
            session.add(row)
        session.commit()


# (kind, question, why, options, screenshot) -> the person's answer, or None.
Asker = Callable[[str, str, str | None, list[str], uuid.UUID | None], Awaitable[str | None]]


@dataclass
class Pursuit:
    # done | final | stuck | limit | stopped
    ended: str = "limit"
    outcome: str = ""
    steps: int = 0
    history: list[str] = field(default_factory=list)
    branches: list[dict[str, Any]] = field(default_factory=list)
    needs: list[str] = field(default_factory=list)
    # The exact actions that worked, replayable without the model (Stage 5):
    # {"do": "goto", "url"} | {"do": "fill", "field", "value"} |
    # {"do": "choose", "field", "option"} | {"do": "click", "label"} |
    # {"do": "upload", "field", "kind"} (a sample file, see samples.py) |
    # {"do": "back"} | {"do": "reload"} (the browser's own buttons)
    actions: list[dict[str, str]] = field(default_factory=list)


async def pursue(
    eyes: Eyes,
    mind: Mind,
    journal: Journal,
    goal: str,
    notes: str | None,
    heartbeat: Callable[[], None],
    *,
    instructions: str | None = None,
    known_screens: dict[str, str] | None = None,
    max_steps: int = 14,
    stop_requested: Callable[[], bool] = lambda: False,
    non_production: bool = False,
    ask: Asker | None = None,
    lead_in: list[dict[str, str]] | None = None,
    stay_signed_out: bool = False,
    obey_goal: bool = True,
    approved_presses: set[str] | None = None,
) -> Pursuit:
    """`non_production` lets a mission press final Save/Submit/Create so it
    can make its own test data (PLAN.md Step 5); actions that need a human's
    OK (delete, pay, approve...) are never pressed. `lead_in` is the replayed
    path that brought the browser here (see `path_to`), so the paths this
    walk remembers still start from the app's home."""
    assert eyes.page is not None
    known_screens = known_screens or {}
    result = Pursuit()
    stuck = 0
    asked: set[str] = set()
    sent: set[str] = set()  # final Send/Submit buttons already pressed
    learned: list[str] = []  # answers you gave during this pursuit
    signed_back_in = False
    visit = await eyes.look(eyes.page.url, None, 0)
    result.actions.append({"do": "goto", "url": eyes.page.url})
    step_name = await mind.take_in(visit, f"Start: {goal}")
    # Every screen it arrived on, for the loop guard. Keyed by the stored
    # screen, because the names the model gives can vary between visits.
    first_name: dict[object, str] = {}

    def arrived(name: str) -> str:
        screen_id = mind.last_screen_id
        name = first_name.setdefault(screen_id or name, name)
        if not sent and screen_id is not None:
            # How to get here from home, replayable without the model — only
            # before anything was sent for real (replaying a send would
            # create duplicate records).
            path = [*lead_in, *result.actions[1:]] if lead_in else list(result.actions)
            # Only a route from an entry point, by the user's own actions,
            # works in a clean browser; one that opened a page by its address
            # is never kept to fast-forward later tests through.
            if route_starts_at_entry(path, eyes.entry_urls):
                remember_route(screen_id, path)
        return name

    landed: list[str] = [arrived(step_name)]

    for _ in range(max_steps):
        heartbeat()
        if stop_requested():
            result.ended = "stopped"
            break
        if edge_reached(getattr(mind, "last_goal_fit", None), obey_goal):
            # Past the goal's stop point, or outside the goal: never act here.
            # "done", so a scenario that landed on the screen after its stop
            # point still uses that screen as its proof.
            result.ended = "done"
            result.outcome = f"Reached the edge of your goal: {step_name}"
            journal.event("phase", result.outcome, None, journal.shot(visit.shot))
            break
        if eyes.starts_fresh and await eyes.start_fresh_if_asked():
            # A "resume your saved progress?" prompt left by an earlier run:
            # answered with start over and not recorded (every replay and the
            # exported test answer it the same way whenever it shows).
            visit = await eyes.look(eyes.page.url, None, 0)
            step_name = await mind.take_in(visit, "Started over")
            landed.append(arrived(step_name))
            continue
        if not stay_signed_out and await eyes.on_sign_in_screen():
            # Signed out mid-walk. Never let the model type credentials (a
            # login page may show demo ones); sign back in with the saved
            # test login, once. A walk that keeps losing it stops.
            if signed_back_in or not await eyes.sign_in_again():
                result.ended = "stuck"
                result.outcome = "The app signed me out and I couldn't sign back in"
                journal.event("phase", "Signed out", result.outcome, journal.shot(visit.shot))
                break
            signed_back_in = True
            journal.event(
                "thought", "Signed back in", "The app signed me out; I used the saved login."
            )
            visit = await eyes.look(eyes.page.url, None, 0)
            step_name = await mind.take_in(visit, "Signed back in")
            landed.append(arrived(step_name))
            continue
        circling = going_in_circles(landed)
        if circling:
            # Never keep walking in circles: it learns nothing and burns the run.
            result.ended = "stuck"
            result.outcome = f"Stopped going in circles: {circling}"
            journal.event(
                "phase", "Stopped going in circles", circling[:600], journal.shot(visit.shot)
            )
            break
        plan = await brain.decide_step(
            visit.shot,
            visit.inventory,
            goal,
            "\n".join([notes or "", *learned, *mind.noted]).strip() or None,
            result.history,
            instructions=instructions,
            known_screens=list(known_screens),
        )
        result.steps += 1
        journal.event("thought", step_name, plan.get("thought"))

        for branch in plan["branch_points"][:3]:
            if isinstance(branch, dict) and branch.get("question"):
                result.branches.append({"step": step_name, **branch})
                others = ", ".join(
                    str(o) for o in (branch.get("options_worth_trying_later") or [])[:4]
                )
                journal.event(
                    "thought",
                    "A choice here may change the path",
                    f"{branch['question']}"
                    + (f" — worth trying later: {others}" if others else ""),
                )
        # Explorer has its own sample files, so a file is never asked for.
        new_needs = [
            str(n)
            for n in plan["needs_from_human"][:3]
            if str(n) not in asked and not _ASKS_FOR_FILE.search(str(n))
        ]
        if new_needs and ask is not None:
            need = new_needs[0]
            asked.add(need)
            answer = await ask(
                "data",
                need if need.rstrip().endswith("?") else f"I need this to continue: {need}. What should I use?",
                f"Needed on “{step_name}” to: {goal}",
                [],
                journal.shot(visit.shot),
            )
            if answer:
                learned.append(f"The user said, for “{need}”: {answer}")
                result.history.append(f"{step_name}: asked for {need}, got an answer")
                continue  # look at the same screen again, now knowing the answer
        for need in new_needs:
            result.needs.append(need)
            journal.event("thought", "I'll need this from you", need)

        # Jump straight to a screen we already know, when that's the way forward.
        jump = plan.get("go_to_screen")
        if jump and jump in known_screens and not plan.get("fills") and not plan.get("choices"):
            target_url = known_screens[jump]
            status, load_ms = await eyes.goto(target_url)
            result.actions.append({"do": "goto", "url": target_url})
            visit = await eyes.look(eyes.page.url, status, load_ms)
            if not same_place(eyes.page.url, target_url):
                # Wizard steps (FNOL) bounce a direct visit back to the start
                # because the app's in-memory state (chosen policy, vehicles)
                # is missing. Stop offering that jump; walk there instead.
                # Mutates the caller's dict on purpose so later passes skip it too.
                del known_screens[jump]
                result.history.append(
                    f"{step_name}: jumping to {jump} sent me back to the start — "
                    "it can only be reached by clicking through the earlier steps"
                )
            else:
                result.history.append(f"{step_name}: went to {jump}")
            mind.last_screen_id = None  # a jump isn't a way through the app: no map edge
            step_name = await mind.take_in(visit, f"Went to {jump}", action=f"Go to {jump}")
            landed.append(arrived(step_name))
            continue

        entered: list[str] = []
        for fill in plan["fills"][:25]:
            if isinstance(fill, dict) and fill.get("field") and fill.get("value") is not None:
                if await eyes.fill_field(str(fill["field"]), str(fill["value"])):
                    picked = eyes.last_suggestion
                    entered.append(
                        f"{fill['field']} = {fill['value']}" + (f" (picked “{picked}”)" if picked else "")
                    )
                    action = {"do": "fill", "field": str(fill["field"]), "value": str(fill["value"])}
                    if eyes.last_locator:
                        action["locator"] = dict(eyes.last_locator)  # exactly what worked
                    if picked:
                        action["suggest"] = picked  # the exported test picks it too
                    result.actions.append(action)
        for choice in plan["choices"][:25]:
            if isinstance(choice, dict) and choice.get("option"):
                if await eyes.choose(str(choice.get("field") or ""), str(choice["option"])):
                    entered.append(f"{choice.get('field') or 'Choice'}: {choice['option']}")
                    chose = {
                        "do": "choose",
                        "field": str(choice.get("field") or ""),
                        "option": str(choice["option"]),
                    }
                    if eyes.last_locator:
                        chose["locator"] = dict(eyes.last_locator)
                    result.actions.append(chose)
        for upload in plan["uploads"][:3]:
            if isinstance(upload, dict):
                field, kind = str(upload.get("field") or ""), str(upload.get("kind") or "image")
                path = sample_file(kind)
                if await eyes.upload_file(field, str(path)):
                    entered.append(f"Attached {path.name}" + (f" to “{field}”" if field else ""))
                    result.actions.append({"do": "upload", "field": field, "kind": kind})
                else:
                    result.history.append(f"{step_name}: could not attach a file to “{field}”")
        if entered:
            journal.event(
                "action",
                (entered[0] if entered[0].startswith("Attached") else f"Entered {entered[0]}")
                if len(entered) == 1
                else f"Filled {len(entered)} fields on {step_name}",
                "; ".join(entered)[:900],
            )

        browser = str(plan.get("browser") or "").lower()
        if browser in ("back", "reload") and not plan.get("done"):
            await eyes.browser(browser)
            result.actions.append({"do": browser})
            result.history.append(f"{step_name}: pressed the browser's {browser}")
            visit = await eyes.look(eyes.page.url, None, 0)
            step_name = await mind.take_in(visit, f"Browser {browser}", action=f"Browser {browser}")
            landed.append(arrived(step_name))
            continue

        advance = plan.get("advance")
        if entered and not advance and not plan.get("done"):
            # What it entered may have revealed more of the form (a "Create
            # login" switch adds fields): look again instead of stopping.
            # The visits-per-screen guard ends it if nothing new appears.
            visit = await eyes.look(eyes.page.url, None, 0)
            step_name = await mind.take_in(visit, None)
            landed.append(arrived(step_name))
            continue
        if plan.get("done") or not advance:
            result.ended = "done"
            result.outcome = str(plan.get("thought") or f"Finished on {step_name}")
            journal.event("phase", "Reached the end of this task", f"Last screen: {step_name}")
            break
        # A link to another page only navigates ("💰 Send Money" opens the
        # transfer form); it is never the final, committing press.
        link = page_link(visit.inventory, str(advance))
        is_final = not link and (bool(plan.get("advance_is_final")) or looks_final(str(advance)))
        needs_ok = is_risky_link(str(advance), link) if link else needs_human_ok(str(advance), goal)
        if stay_signed_out and is_sign_out(str(advance)):
            needs_ok = False  # a sign-in test's own session, nobody else's
        if is_final and _same_button(str(advance), sent):
            # Pressing Send again when the screen seemed not to change risks a
            # duplicate record (seen on FNOL: two claims per attempt).
            result.ended = "done"
            result.outcome = f"Already pressed “{advance}” once; not pressing it again"
            journal.event("thought", "Not sending twice", result.outcome)
            break
        # A button you already said "Yes, press it" to while Explorer explored.
        approved = pre_approved(str(advance), approved_presses or set())
        if not approved and ask is not None and (
            needs_ok or (is_final and not may_commit(f"{advance} ({goal})", non_production))
        ):
            answer = await ask(
                "risk",
                f"May I press “{_ICON_TEXT.sub('', str(advance)).strip()}” on {step_name}?",
                f"It is the next step to: {goal.rstrip('. ')}. It may change real data, so I wait for your OK.",
                ["Yes, press it", "No, stop here"],
                journal.shot(visit.shot),
            )
            approved = bool(answer) and answer.lower().startswith("yes")
        if not approved and (
            needs_ok or (is_final and not may_commit(f"{advance} ({goal})", non_production))
        ):
            result.ended = "final"
            result.outcome = f"Ready to press “{advance}” on {step_name}"
            shot_id = journal.shot((await eyes.look(eyes.page.url, None, 0)).shot)
            journal.event(
                "phase",
                f"Stopped before “{advance}”",
                "This needs your OK before I ever press it.",
                shot_id,
            )
            break
        if is_final:
            journal.event(
                "action",
                f"Pressing “{advance}”",
                "This is a test environment, so I'm saving for real to create my own test data.",
            )

        before = await eyes.fingerprint()
        clicked = await eyes.click_text(str(advance), "button")
        if clicked and is_final:
            sent.add(str(advance))
        moved = clicked and await eyes.wait_for_change(before)
        if clicked:
            pressed = {"do": "click", "label": str(advance)}
            if eyes.last_locator:
                pressed["locator"] = dict(eyes.last_locator)
            result.actions.append(pressed)
        visit = await eyes.look(eyes.page.url, None, 0)
        if not moved:
            stuck += 1
            said = "; ".join(visit.inventory.get("alerts") or [])
            journal.event(
                "thought",
                f"The app didn't move past {step_name}",
                (
                    f"It said: {said}"
                    if said
                    else "No message shown — I'll adjust my answers and try again."
                )[:600],
                journal.shot(visit.shot),
            )
            if stuck > MAX_RETRIES_ON_SAME_STEP:
                result.ended = "stuck"
                result.outcome = f"Couldn't get past {step_name}" + (f": {said}" if said else "")
                break
            result.history.append(f"{step_name}: attempt rejected ({said or 'no message'})")
            continue
        stuck = 0
        result.history.append(f"{step_name}: {'; '.join(entered) or 'no input'} -> {advance}")
        step_name = await mind.take_in(visit, f"{step_name} → {advance}", action=str(advance))
        landed.append(arrived(step_name))
    if not result.outcome:
        result.outcome = f"Stopped after {result.steps} steps on {step_name}"
    return result


def pre_approved(label: str, approved: set[str]) -> bool:
    """Did the user already approve pressing this button (a risk question
    answered "Yes, press it")? Nothing approved: never."""
    return bool(approved) and _same_button(label, approved)


def _same_button(label: str, pressed: set[str]) -> bool:
    """'Send my report Icon Send my report' is the same button as 'Send my report'."""
    norm = " ".join(label.lower().split())
    return any(p.lower() in norm or norm in p.lower() for p in pressed)
