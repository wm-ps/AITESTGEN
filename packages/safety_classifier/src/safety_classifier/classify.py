"""Action classification (Story 2.12 AC 1) — extracted verbatim from
`discovery_worker.safety_engine` (Run All Tests feature) so the same
classifier serves two callers: `safety_engine.evaluate()` still resolves
Ambiguous by live-crawl posture exactly as before (this extraction changes
nothing about that behavior — only `classify()` and its three pattern
lists moved; `evaluate()`/`SafetyState`/`consult_ai` stay in
`safety_engine.py`), and `generation_worker.scenario_generation_activity`
calls this fresh, at generation time, to persist `Scenario.safety_classification`.

Three tunable verb/pattern lists matched against an action's accessible
name (or, for a generated Scenario, one of its plain-language steps) —
configuration, not literals buried elsewhere. An action matching none of
the three lists is never Safe by default: it falls into the Ambiguous
bucket alongside an explicit Ambiguous-list match.
"""

import re

# Destructive is checked first — an accessible name matching both a
# destructive and a safe pattern (a customized list could do this even
# though the seed lists don't overlap) must never come out Safe.
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
    """Returns `(bucket, matched_list)` where `bucket` is `"safe"` |
    `"destructive"` | `"ambiguous"`. `matched_list` names whichever list
    fired, or `None` when the label matched nothing at all — still
    bucketed "ambiguous" (an unmatched action is never Safe by default),
    but distinguishable from a real Ambiguous-list match for diagnostics."""
    label = label or ""
    if any(p.search(label) for p in DESTRUCTIVE_PATTERNS):
        return "destructive", "destructive"
    if any(p.search(label) for p in SAFE_PATTERNS):
        return "safe", "safe"
    if any(p.search(label) for p in AMBIGUOUS_PATTERNS):
        return "ambiguous", "ambiguous"
    return "ambiguous", None


def classify_scenario_steps(steps: list[str]) -> tuple[str, str]:
    """Aggregates `classify()` across every one of a Scenario's
    plain-language steps into a single `SAFE`/`DESTRUCTIVE`/`UNKNOWN`
    verdict for the whole Scenario (Run All Tests feature) —
    most-severe-step-wins, since executing the Scenario runs every step.
    `UNKNOWN` (not `SAFE`) is the fail-closed default for "no steps" and
    for any step `classify()` couldn't match at all, consistent with this
    feature's "deny by default" execution-gating decision. Shared by
    `generation_worker.scenario_generation_activity` (classifies at
    generation time) and the one-off backfill script for `Scenario` rows
    created before this column existed — one implementation, not two."""
    if not steps:
        return "UNKNOWN", "scenario has no steps to classify"

    verdicts = [classify(step) for step in steps]
    if any(bucket == "destructive" for bucket, _ in verdicts):
        return "DESTRUCTIVE", "at least one step matched a destructive pattern"
    if any(matched_list is None for _, matched_list in verdicts):
        return "UNKNOWN", "at least one step matched no known pattern"
    if any(bucket == "ambiguous" for bucket, _ in verdicts):
        return "UNKNOWN", "at least one step matched an ambiguous pattern (submit/approve/save/...)"
    return "SAFE", "every step matched a safe pattern"
