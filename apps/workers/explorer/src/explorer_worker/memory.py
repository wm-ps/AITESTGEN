"""Stage 4 — what Explorer knows about an application, and asking a person
when it doesn't (PLAN.md Step 6).

- Memory is per application and survives runs: your answers, documents
  you upload and facts you add. It is fed into every prompt as trusted
  knowledge ("confirmed", §4.1).
- Before asking, memory is checked so the same thing is never asked twice.
- Asking pauses only the mission that asked: it waits (heartbeating) with
  its browser open while everything else keeps going.
"""

import asyncio
import os
import re
import uuid
from collections.abc import Callable

from explorer_core import ExplorerKnowledge, ExplorerMission, ExplorerQuestion, ExplorerRun
from sqlmodel import Session, col, select

from explorer_worker.db import engine
from explorer_worker.journal import Journal

FACTS_IN_PROMPT = 60
# How long a mission pauses for your answer to a blocking question ("I need
# this to continue", "May I press Send?"). 0 = never wait. "Is this a bug?"
# questions never block; they are answered whenever you get to them.
# An answer is remembered per app, so the same question is only waited on once.
WAIT_MINUTES = int(os.environ.get("EXPLORER_WAIT_MINUTES", "10"))

_STOP = {"the", "a", "an", "is", "are", "to", "of", "for", "on", "in", "and", "or", "i",
         "this", "that", "it", "be", "can", "you", "me", "my", "should", "what", "which"}  # fmt: skip


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 1}


def similar(a: str, b: str, threshold: float = 0.6) -> bool:
    """Same question in different words? Share of meaningful words in common."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) >= threshold


def known_facts(application_id: uuid.UUID) -> list[str]:
    """Your answers and facts first (most direct), then document excerpts."""
    with Session(engine) as session:
        rows = session.exec(
            select(ExplorerKnowledge)
            .where(ExplorerKnowledge.application_id == application_id)
            .order_by(col(ExplorerKnowledge.created_at).desc())
        ).all()
    direct = [r.text for r in rows if r.kind != "doc"][:40]
    docs = [f"(from {r.source}) {r.text}" for r in rows if r.kind == "doc"][
        : FACTS_IN_PROMPT - len(direct)
    ]
    return direct + docs


def remember(application_id: uuid.UUID, kind: str, text: str, source: str | None) -> None:
    with Session(engine) as session:
        session.add(
            ExplorerKnowledge(
                application_id=application_id, kind=kind, text=text[:4000], source=source
            )
        )
        session.commit()


def _application_of(run_id: uuid.UUID) -> uuid.UUID | None:
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        return run.application_id if run else None


def remember_record(run_id: uuid.UUID, what: str, value: str, context: str) -> str | None:
    """A record the app itself created (a claim reference, an order
    number) becomes test data for every later mission and test. Returns the
    remembered sentence, or None when it was already known."""
    application_id = _application_of(run_id)
    if application_id is None or not value.strip():
        return None
    with Session(engine) as session:
        known = session.exec(
            select(ExplorerKnowledge.id).where(
                ExplorerKnowledge.application_id == application_id,
                ExplorerKnowledge.kind == "record",
                col(ExplorerKnowledge.text).contains(value.strip()),
            )
        ).first()
    if known is not None:
        return None
    text = (
        f"Test data the app showed: {what} {value.strip()} ({context}). "
        f"Use it whenever a screen asks for an existing {what.lower()}."
    )
    remember(application_id, "record", text, "Explorer saw it")
    return text


def already_answered(run_id: uuid.UUID, question: str) -> str | None:
    """An earlier answer to the same question, in this app's memory."""
    application_id = _application_of(run_id)
    if application_id is None:
        return None
    with Session(engine) as session:
        answered = session.exec(
            select(ExplorerQuestion)
            .join(ExplorerRun, col(ExplorerRun.id) == col(ExplorerQuestion.run_id))
            .where(
                ExplorerRun.application_id == application_id,
                ExplorerQuestion.status == "answered",
            )
        ).all()
    for q in answered:
        if q.answer and similar(q.question, question):
            return q.answer
    return None


async def ask(
    journal: Journal,
    kind: str,
    question: str,
    why: str | None,
    options: list[str],
    shot_id: uuid.UUID | None,
    heartbeat: Callable[[], None],
    *,
    wait: bool = True,
    issue_id: uuid.UUID | None = None,
) -> str | None:
    """Ask a person. With `wait`, the calling mission pauses until answered
    (or WAIT_MINUTES pass, then carries on without). Returns the answer."""
    earlier = already_answered(journal.run_id, question)
    if earlier is not None:
        journal.event("thought", "I already know this", f"{question} — you told me: {earlier}")
        return earlier
    with Session(engine) as session:
        duplicate = session.exec(
            select(ExplorerQuestion).where(
                ExplorerQuestion.run_id == journal.run_id, ExplorerQuestion.status == "open"
            )
        ).all()
        existing = next((q for q in duplicate if similar(q.question, question)), None)
        is_new = existing is None
        if existing is None:
            existing = ExplorerQuestion(
                run_id=journal.run_id,
                mission_id=journal.mission_id,
                kind=kind,
                question=question[:600],
                why=(why or "")[:600] or None,
                options=[str(o)[:200] for o in options][:6],
                shot_id=shot_id,
                issue_id=issue_id,
            )
            session.add(existing)
            session.commit()
            session.refresh(existing)
            journal.event("question", f"Question for you: {question}"[:300], why, shot_id)
        question_id = existing.id
    if not wait or WAIT_MINUTES <= 0:
        # Every new question is emailed — you may not be watching the run.
        # One that doesn't block (e.g. "is this a bug?") says so.
        if is_new:
            await asyncio.to_thread(
                journal.email_starter,
                "Explorer has a question for you",
                f"{question} Explorer is carrying on without it; your answer will be used "
                "from the next step on.",
            )
        return None
    if journal.mission_id is not None:
        # A mission you skipped stays skipped: "waiting" must never overwrite it.
        if journal.mission_status() == "skipped":
            return None
        journal.update_mission(status="waiting")
    if is_new:
        await asyncio.to_thread(
            journal.email_starter,
            "Explorer has a question for you",
            f"{question} Explorer will wait {WAIT_MINUTES} minutes for your answer, then "
            "carry on without it.",
        )
    try:
        for _ in range(WAIT_MINUTES * 12):
            heartbeat()
            await asyncio.sleep(5)
            with Session(engine) as session:
                q = session.get(ExplorerQuestion, question_id)
                if q is None or q.status == "dismissed":
                    return None
                if q.status == "answered":
                    journal.event(
                        "thought", "Got your answer — continuing", f"{question} → {q.answer}"
                    )
                    return q.answer
            if journal.status() == "stopped" or (
                journal.mission_id is not None and journal.mission_status() == "skipped"
            ):
                return None
        journal.event("thought", "No answer yet — carrying on without it", question)
        return None
    finally:
        if journal.mission_id is not None:
            with Session(engine) as session:
                mission = session.get(ExplorerMission, journal.mission_id)
                if mission is not None and mission.status == "waiting":
                    mission.status = "running"
                    session.add(mission)
                    session.commit()
