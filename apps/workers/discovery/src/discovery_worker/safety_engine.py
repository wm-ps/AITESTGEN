"""Safety Engine — action classification, environment posture, and the
Planner's `safety` specialist (Story 2.12, spine box D — DECIDE).

`[REVERSES PRD §12 Risk item 6's prior "accepted risk, no guardrail"
decision — see this story's Dev Notes for why the per-Application
`safety_posture` setting narrows that reversal enough to sign off on: the
platform refuses Clearly Destructive actions everywhere, and refuses
Ambiguous ones only where a user has asked for that caution.]`

Classification (AC 1) is three tunable verb/pattern lists matched against an
action's accessible name — configuration, not literals buried in the
matching code (Task 2). An action matching none of the three lists is never
Safe by default: it falls into the Ambiguous bucket alongside an explicit
Ambiguous-list match, and posture resolves it exactly the same way (AC 1/2).

AC 3's AI consultation (`consult_ai`) is real — tested against a failing/
timing-out provider to prove the guarantee holds — but not called from the
live crawl loop by default: it is supporting evidence only that never
changes the verdict (`evaluate()` has no parameter for it), so paying a
network round-trip per genuinely-unmatched action in the hot crawl loop
buys nothing but latency until the product actually wants that opinion
recorded. `ponytail:` wire `consult_ai` into `SafetyState.__call__` (with a
bounded timeout, off the sync call path) once that's wanted; `evaluate()`'s
posture-driven verdict does not need to change.
"""

import asyncio
import logging
import re
from dataclasses import dataclass

from discovery_worker.planner import ActionCandidate, SpecialistVerdict

logger = logging.getLogger(__name__)

# AC 1: seeded from the PRD's named examples. Destructive is checked first —
# an accessible name matching both a destructive and a safe pattern (a
# customized list could do this even though the seed lists don't overlap)
# must never come out Safe.
DESTRUCTIVE_PATTERNS = [
    re.compile(rf"\b{verb}\b", re.IGNORECASE)
    for verb in ("delete", "remove", "terminate", "transfer", "payment")
]
SAFE_PATTERNS = [
    re.compile(rf"\b{verb}\b", re.IGNORECASE)
    for verb in (
        "view",
        "open",
        "expand",
        "collapse",
        "navigate",
        "tab",
        "paginate",
        "next page",
        "previous page",
        "search",
        "filter",
    )
]
AMBIGUOUS_PATTERNS = [
    re.compile(rf"\b{verb}\b", re.IGNORECASE)
    for verb in ("submit", "approve", "reject", "save", "confirm", "proceed")
]


def classify(label: str) -> tuple[str, str | None]:
    """AC 1: returns (bucket, matched_list) where bucket is "safe" |
    "destructive" | "ambiguous". `matched_list` names whichever list fired,
    or `None` when the label matched nothing at all — still bucketed
    "ambiguous" (an unmatched action is never Safe by default), but
    distinguishable from a real Ambiguous-list match for diagnostics (AC 6)
    and for deciding whether AI consultation would even apply (AC 3)."""
    label = label or ""
    if any(p.search(label) for p in DESTRUCTIVE_PATTERNS):
        return "destructive", "destructive"
    if any(p.search(label) for p in SAFE_PATTERNS):
        return "safe", "safe"
    if any(p.search(label) for p in AMBIGUOUS_PATTERNS):
        return "ambiguous", "ambiguous"
    return "ambiguous", None


@dataclass(frozen=True)
class SafetyVerdict:
    """AC 4/6: `verdict` is exactly one of SAFE | DESTRUCTIVE | DEFER — the
    only three values the Planner (and diagnostics) ever see. `matched_list`
    is the `classify()` bucket that fired, or `None` for a fully unmatched
    label."""

    verdict: str
    matched_list: str | None
    posture: str
    ai_consulted: bool
    reason: str


def evaluate(label: str, posture: str, ai_consulted: bool = False) -> SafetyVerdict:
    """AC 2/4: classify, then resolve Ambiguous by posture. A Destructive
    classification is never executed under either posture (AC 2); a Safe
    classification is unaffected by posture. `ai_consulted` is recorded
    as-given (AC 6) but never changes the outcome below (AC 3)."""
    bucket, matched_list = classify(label)
    if bucket == "destructive":
        return SafetyVerdict(
            "DESTRUCTIVE",
            matched_list,
            posture,
            ai_consulted,
            f"matched destructive list: {label!r}",
        )
    if bucket == "safe":
        return SafetyVerdict(
            "SAFE", matched_list, posture, ai_consulted, f"matched safe list: {label!r}"
        )
    if posture == "production":
        return SafetyVerdict(
            "DEFER",
            matched_list,
            posture,
            ai_consulted,
            f"ambiguous action deferred under production posture: {label!r}",
        )
    return SafetyVerdict(
        "SAFE",
        matched_list,
        posture,
        ai_consulted,
        f"ambiguous action executed under non_production posture: {label!r}",
    )


async def consult_ai(
    ai_provider, label: str, page_context: str, timeout: float = 5.0
) -> str | None:
    """AC 3: best-effort supporting evidence only — a failure or timeout
    here never falls back to EXECUTE, because it was never in the decision
    path to begin with (`evaluate()` above is the only thing that decides).
    Same fire-and-forget shape as `state_identity`'s AI tiebreaker
    (`activities.py`'s `_get_ai_opinion`)."""
    try:
        return await asyncio.wait_for(
            ai_provider.classify_action_safety(label, page_context), timeout=timeout
        )
    except Exception:
        logger.warning("safety_engine: AI consult failed — verdict unaffected", exc_info=True)
        return None


_TO_SPECIALIST_DECISION = {"SAFE": None, "DESTRUCTIVE": "SKIP", "DEFER": "DEFER"}


class SafetyState:
    """One instance per crawl, injected as the Planner's `safety` specialist
    (Story 2.11's `decide()` calls it as `Callable[[ActionCandidate],
    SpecialistVerdict]`) — same one-per-crawl shape as
    `planner.LoopGuardState`/`data_resolver.ResolutionLog`. `last_verdict`
    is read by the caller immediately after `decide()` returns so every
    verdict reached (not just a non-EXECUTE one) gets a diagnostic (AC 6)
    and a genuinely Safe verdict can trigger post-action verification
    (Task 4) — `decide()`'s own `SpecialistVerdict` only carries a decision/
    reason, not the richer posture/matched_list/ai_consulted detail."""

    def __init__(self, posture: str) -> None:
        self.posture = posture
        self.last_verdict: SafetyVerdict | None = None

    def __call__(self, candidate: ActionCandidate) -> SpecialistVerdict:
        verdict = evaluate(candidate.label, self.posture)
        self.last_verdict = verdict
        return SpecialistVerdict(_TO_SPECIALIST_DECISION[verdict.verdict], verdict.reason)
