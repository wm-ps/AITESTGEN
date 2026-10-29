"""Read the user's request: the flow it is about, the scenarios it asks for,
and what must be asked before starting. An authoring run has no first look
around the app: the request becomes the run's summary, its questions (if
any) are answered first, then Explorer walks exactly the request's steps."""

import uuid
from datetime import UTC, datetime
from typing import Any

from domain import Application
from explorer_core import ExplorerRun
from sqlmodel import Session

from explorer_worker import brain
from explorer_worker.db import engine
from explorer_worker.journal import Journal
from explorer_worker.llm import THINKING_MODEL, ask_json

_SYSTEM = (
    brain.STANCE
    + """

The user wants test cases for this application and described, in their own words, \
what to test (their request). Read it exactly; never add to it. Reply with ONLY:
{
  "title": "a short name for the request, at most 8 words, e.g. 'Report a claim'",
  "flow": "the business flow the request is about, plainly, from its start to its end",
  "scenarios": ["each scenario the user explicitly asked for, one per item, in their words"],
  "count": "how many scenarios the user asked for when they gave a number \
(\"a test case\" = 1); else null",
  "only": "any limit the user put on which scenarios (e.g. 'positive only'); else null",
  "questions": [
    {"question": "...", "changes": "what the answer changes", "options": ["short answers"]}
  ]
}
Rules:
- 'scenarios' lists ONLY scenarios the user wrote out. When they only described a flow, \
it is [] (Explorer then writes the flow and the other scenarios worth testing on it).
- 'count' and 'only' come from the user's own words; never guess them.
- Ask a question only when the request cannot be carried out without the answer \
(test data it needs but does not give, such as a policy or account number, or a choice \
it leaves open). At most 3; [] when the request is clear. Never ask what the app will show."""
)


async def read_request(prompt: str) -> dict[str, Any]:
    reply = await ask_json(_SYSTEM, f"The user's request:\n{prompt}", model=THINKING_MODEL)
    scenarios = reply.get("scenarios")
    questions = reply.get("questions")
    return {
        "title": str(reply.get("title") or prompt)[:120],
        "flow": str(reply.get("flow") or prompt)[:2000],
        "scenarios": [str(s)[:500] for s in scenarios if s] if isinstance(scenarios, list) else [],
        "count": _count(reply.get("count")),
        "only": str(reply["only"])[:200] if reply.get("only") else None,
        "questions": [
            {
                "screen": "Your request",
                "question": str(q["question"])[:300],
                "changes": str(q.get("changes") or "")[:300],
                "options": [str(o)[:120] for o in q.get("options") or []][:5],
            }
            for q in (questions if isinstance(questions, list) else [])
            if isinstance(q, dict) and q.get("question")
        ][:3],
    }


def _count(value: object) -> int | None:
    try:
        number = int(str(value))
    except TypeError, ValueError:
        return None
    return number if 0 < number <= 50 else None


async def read_and_keep(run_id: uuid.UUID) -> None:
    """Before the first look: read the request and keep the reading on the run."""
    journal = Journal(run_id)
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None or not run.prompt:
            return
        prompt, insights = run.prompt, dict(run.insights or {})
    journal.event("phase", "Reading your request", prompt[:1000])
    insights["request"] = await read_request(prompt)
    journal.update_run(insights=insights)


def first_summary(app_name: str, prompt: str, request: dict[str, Any]) -> dict[str, Any]:
    """The run's summary is the request itself — no first look around the app.
    Its questions are the only ones asked before walking. No Goal is set:
    the walk follows the request's own steps, nothing else is explored."""
    return {
        "app_name": app_name,
        "one_liner": f"Your request: {request.get('title') or prompt[:120]}",
        "request": {k: request.get(k) for k in ("title", "flow", "scenarios", "count", "only")},
        "questions_for_you": list(request.get("questions") or []),
    }


def start(run_id: uuid.UUID) -> str:
    """Instead of Explorer's first look: put the request on the run. With
    questions, wait for the user's answers ("awaiting_confirmation");
    without, go straight to walking it ("confirmed")."""
    journal = Journal(run_id)
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None or not run.prompt:
            return "failed"
        application = session.get(Application, run.application_id)
        request = (run.insights or {}).get("request") or {
            "title": run.prompt[:120],
            "flow": run.prompt,
            "scenarios": [],
            "questions": [],
        }
        run.brief = first_summary(application.name if application else "", run.prompt, request)
        asks = bool(run.brief["questions_for_you"])
        if not asks:
            run.brief_confirmed_at = datetime.now(UTC)
        session.add(run)
        session.commit()
    if asks:
        journal.update_run(
            status="awaiting_confirmation", headline="Please answer a few questions first"
        )
        journal.event(
            "summary",
            "A few questions about your request",
            "Answer them on the summary, then confirm — I start walking your steps right after.",
        )
        return "awaiting_confirmation"
    return "confirmed"
