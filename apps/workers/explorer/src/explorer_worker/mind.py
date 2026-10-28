"""Explorer's understanding as one browser moves through the app: read the
screen, name it by meaning, remember it, note health problems and possible
bugs, and draw the App Map edge from the previous screen. Shared by the first
look (Stage 1) and missions (Stage 2)."""

import re
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

from explorer_worker import brain
from explorer_worker.browser import Visit
from explorer_worker.journal import Journal
from explorer_worker.memory import remember_record
from explorer_worker.sense import screen_signature, url_pattern


class Mind:
    def __init__(
        self,
        journal: Journal,
        notes: str | None,
        heartbeat: Callable[[], None],
        condition: str | None = None,
        home_url: str | None = None,
    ) -> None:
        self.journal = journal
        self.notes = notes
        self.heartbeat = heartbeat
        # A branch mission's situation: screens first found under it are hidden screens.
        self.condition = condition
        self.home_pattern = url_pattern(home_url) if home_url else None
        self.understood = [s.name for s in journal.screen_rows()]
        self.last_screen_id: uuid.UUID | None = None
        self.last_reading: dict[str, Any] = {}
        self.new_screens = 0
        # Records the app created during this pursuit, usable right away.
        self.noted: list[str] = []
        # Optional hook run after each screen is read (the first look uses it
        # to collect places worth visiting).
        self.on_screen: Callable[[Visit, str], None] | None = None

    async def take_in(self, visit: Visit, reached_by: str | None, action: str | None = None) -> str:
        self.heartbeat()
        journal = self.journal
        shot_id = journal.shot(visit.shot)
        key = _revisit_key(visit, self.home_pattern)
        known = _READINGS.get((journal.run_id, key)) if key else None
        if known is not None:
            # A screen it has already read in this run: reuse that reading
            # instead of asking the model again (half the model calls on a
            # walk that passes known screens). Still logged and mapped.
            reading = known
        else:
            already_noted = [i.title for i in journal.health_rows()]
            reading = await brain.perceive(
                visit.shot, visit.inventory, self.understood, self.notes, already_noted
            )
            if key:
                _READINGS[(journal.run_id, key)] = reading
        name = str(reading.get("screen_name") or "Untitled screen")[:120]
        if reading.get("is_blank") or reading.get("is_error_page"):
            # A blank or error page is a bug, not a screen: counting it would
            # only inflate the screen total (seen on Catalog BO's sign-in return).
            # The sign-in hand-back (`?code=…&state=…`) is blank by design.
            if reading.get("is_blank") and not _is_sign_in_return(visit.url):
                journal.health_issue(
                    "looks_wrong",
                    "medium",
                    f"Blank page at {url_pattern(visit.url)}",
                    f"Reached by {action or reached_by or 'opening it'}; nothing is shown.",
                    visit.url,
                    shot_id,
                )
            _record_health(journal, visit, {} if known is not None else reading, shot_id)
            journal.event("thought", f"Not a screen: {name}", "Logged as a possible bug.", shot_id)
            return name
        signature = screen_signature(
            reading.get("entity"), str(reading.get("view_kind")), reading.get("mode"), name
        )
        screen_id, is_new = journal.upsert_screen(
            signature,
            {
                "name": name,
                "entity": reading.get("entity"),
                "view_kind": str(reading.get("view_kind") or "other")[:30],
                "mode": reading.get("mode"),
                "purpose": reading.get("purpose"),
                "url": visit.url,
                "url_pattern": url_pattern(visit.url),
                "fields": reading["fields"][:40],
                "actions": reading["actions"][:40],
                "hidden_hints": [str(h) for h in reading["hidden_hints"]][:8],
                "reached_by": reached_by,
                "shot_id": shot_id,
                "condition": self.condition,
            },
            home_pattern=self.home_pattern,
        )
        if self.last_screen_id is not None and screen_id != self.last_screen_id:
            journal.transition(self.last_screen_id, screen_id, action or reached_by or "")
        self.last_screen_id = screen_id

        thought = reading.get("thought") or reading.get("purpose")
        if is_new:
            self.understood.append(name)
            self.new_screens += 1
            if self.condition:
                journal.event(
                    "screen",
                    f"Hidden screen found: {name}",
                    f"Only appears when {self.condition}. {thought or ''}".strip(),
                    shot_id,
                )
            else:
                journal.event("screen", f"Understood: {name}", thought, shot_id)
            for hint in reading["hidden_hints"][:3]:
                journal.event("thought", "Something may be hidden here", str(hint))
        else:
            journal.event("thought", f"On {name}", thought, shot_id)
        journal.update_run(headline=f"On: {name}")
        if known is not None:
            # Already judged on its first read; only fresh technical signals
            # (server errors, crashes) are worth recording again.
            _record_health(journal, visit, {}, shot_id)
        else:
            _record_health(journal, visit, reading, shot_id)
        for record in ([] if known is not None else (reading.get("created_records") or []))[:3]:
            if isinstance(record, dict) and record.get("value") and record.get("what"):
                fact = remember_record(
                    journal.run_id,
                    str(record["what"])[:80],
                    str(record["value"])[:80],
                    str(record.get("context") or f"seen on {name}")[:200],
                )
                if fact:
                    self.noted.append(fact)
                    journal.event(
                        "thought",
                        f"Noted for later: {record['what']} {record['value']}",
                        fact,
                        shot_id,
                    )
        self.last_reading = reading
        if self.on_screen is not None:
            self.on_screen(visit, name)
        return name


def _is_sign_in_return(url: str) -> bool:
    """An OAuth/OIDC sign-in hand-back: `code` and `state` in the query
    (or in a hash route's query)."""
    parts = urlsplit(url)
    keys = parse_qs(parts.query, keep_blank_values=True).keys() | parse_qs(
        parts.fragment.partition("?")[2], keep_blank_values=True
    ).keys()
    return {"code", "state"} <= keys


def _record_health(
    journal: Journal, visit: Visit, reading: dict[str, Any], shot_id: uuid.UUID
) -> None:
    signals = [(s.kind, s.severity, s.title, s.detail, s.url) for s in visit.signals]
    if reading.get("is_error_page"):
        signals.append(
            (
                "crash",
                "high",
                "Screen shows an error instead of content",
                str(reading.get("error_text") or ""),
                visit.url,
            )
        )
    for problem in (reading.get("wording_problems") or [])[:5]:
        if isinstance(problem, dict):
            signals.append(
                (
                    "wording",
                    "low",
                    f"Wording: “{str(problem.get('text'))[:80]}”",
                    str(problem.get("why") or ""),
                    visit.url,
                )
            )
    for wrong in (reading.get("looks_wrong") or [])[:5]:
        if isinstance(wrong, dict):
            signals.append(
                (
                    "looks_wrong",
                    "medium",
                    str(wrong.get("what"))[:200],
                    str(wrong.get("why") or ""),
                    visit.url,
                )
            )
    for kind, severity, title, detail, url in signals:
        if journal.health_issue(kind, severity, title, detail, url, shot_id) and severity != "low":
            journal.event("health", title, detail, shot_id)


# Readings of screens already seen in a run, so a revisit needs no model call.
# ponytail: in-memory per worker process (a restart just re-reads screens
# once); key is the screen's address pattern + main heading, never the home
# address (single-address apps show every screen there).
_READINGS: dict[tuple[uuid.UUID, str], dict[str, Any]] = {}
# Screens whose content is new on every visit (confirmations, results) must
# always be read: they carry fresh values like a new claim reference.
_ALWAYS_READ = re.compile(r"thank|submitted|confirm|success|received|reference|result", re.I)


def _revisit_key(visit: Visit, home_pattern: str | None) -> str | None:
    """Address + the screen's own headings. Apps that never change their
    address (state-only routing) still get distinct keys from the headings;
    those screens need two headings to count, since one generic title
    ("Dashboard") can sit over many different states."""
    pattern = url_pattern(visit.url)
    headings = [" ".join(str(h).split()).lower() for h in (visit.inventory.get("headings") or [])]
    if not headings or _ALWAYS_READ.search(headings[0]):
        return None
    if pattern == home_pattern:
        if len(headings) < 2:
            return None
        return f"{pattern}|{headings[0]}|{headings[1]}"
    return f"{pattern}|{headings[0]}"
