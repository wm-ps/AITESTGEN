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
what to test (their request). It may be a paragraph, one sentence, numbered steps, or a \
request such as "write test cases for X" — no fixed pattern. First understand what they \
mean, then read it exactly; never add to it. Reply with ONLY:
{
  "title": "a short name for the request, at most 8 words, e.g. 'Report a claim'",
  "flow": "the business flow the request is about, plainly, from its start to its end",
  "steps": ["each action a person takes in the app to carry out the flow, in order — the \
user's own steps in their words when they gave them, else plain steps for the flow they \
named (e.g. 'Open Leads', 'Press New Lead', 'Fill in the lead's details', 'Press Save \
Lead'). Never a sentence about writing tests."],
  "checks": ["each outcome the user wants verified, e.g. 'The new lead appears in the \
Leads list'; when they named none, the flow's natural end result"],
  "scenarios": ["each scenario the user explicitly asked for, one per item, in their words"],
  "count": "how many test cases the user asked for, as a number, when they gave one in \
digits or words (\"five\" = 5, \"a dozen\" = 12, \"a test case\" = 1); else null",
  "only": "any limit the user put on which scenarios (e.g. 'positive only'); else null",
  "questions": [
    {"question": "...", "changes": "what the answer changes", "options": ["short answers"]}
  ]
}
Rules:
- 'scenarios' lists ONLY scenarios the user wrote out. When they only described a flow, \
it is [] (Explorer then writes the flow and the other scenarios worth testing on it).
- 'count' and 'only' come from the user's own words; never guess them.
- Ask a question only when the request cannot be carried out without the answer: \
test data it needs but does not give (such as a policy or account number), a choice it \
leaves open, or a request that is ambiguous, contradicts itself or can't be understood \
(say what is unclear). At most 3; [] when the request is clear — a flow named plainly \
("write test cases for creating a lead") is clear. Never ask what the app will show."""
)


async def read_request(prompt: str) -> dict[str, Any]:
    reply = await ask_json(_SYSTEM, f"The user's request:\n{prompt}", model=THINKING_MODEL)
    questions = reply.get("questions")
    return {
        "title": str(reply.get("title") or prompt)[:120],
        "flow": str(reply.get("flow") or prompt)[:2000],
        "steps": _texts(reply.get("steps"))[:30],
        "checks": _texts(reply.get("checks"))[:10],
        "scenarios": _texts(reply.get("scenarios")),
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


def _texts(value: object) -> list[str]:
    return [str(s)[:500] for s in value if s] if isinstance(value, list) else []


_UNITS = "zero one two three four five six seven eight nine ten eleven twelve thirteen \
fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}
_WORDS = {
    **{w: n for n, w in enumerate(_UNITS)},
    **_TENS,
    **{
        f"{t}{sep}{u}": n + i
        for t, n in _TENS.items()
        for i, u in enumerate(_UNITS[1:10], 1)
        for sep in ("-", " ")
    },
    "a": 1,
    "an": 1,
    "single": 1,
    "a single": 1,
    "dozen": 12,
    "a dozen": 12,
}


def _count(value: object) -> int | None:
    """The number of test cases asked for, in digits or words ("five",
    "twenty-one", "a dozen"). ponytail: a word table up to fifty (the cap),
    not a general number parser."""
    text = str(value).strip().lower()
    number = int(text) if text.isdigit() else _WORDS.get(text)
    return number if number is not None and 0 < number <= 50 else None


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
        "request": {
            k: request.get(k)
            for k in ("title", "flow", "steps", "checks", "scenarios", "count", "only")
        },
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
