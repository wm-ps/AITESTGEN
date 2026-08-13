"""Data Resolver — structured input resolution with success feedback
(Story 2.13, spine box D — DECIDE).

Formalizes and extends Story 2.2's generic-value-filling behaviour
(`crawler._generic_value`) into a five-step order (AC 1): the Test Data Pool
(Story 2.20) first, then a page scan, then per-run reuse of values that
worked, then safe synthesis, then DEFER. **Step 2 (page scan) is
deliberately not built** — the story's own Dev Notes call it the weakest
step and a candidate to cut ("a value visible on screen is frequently *not*
valid input for that field: it may be already consumed, read-only,
computed, or belong to a different record"); steps 1/3/4 carry almost all
the practical value, so this ships without it rather than spend the budget
building something likely to be cut anyway.

Reuse and demotion (AC 2/3) are keyed on the field alone (route-family
wildcard), not per-route — "the same field key is resolved again later in
the *run*" (AC 3) is a run-wide statement, and partitioning reuse/demotion
by route would mean a value the application rejected on one page could
still be re-submitted, unchanged, on the next. The Test Data Pool (step 1)
is the only step that respects a real, seeded route family, falling back to
the wildcard when no route-specific entry exists — see
`apps/api/src/api/main.py`'s `_POOL_WILDCARD_ROUTE_FAMILY` for the other
half of that design.
"""

import re
from dataclasses import dataclass

from domain import aggregation_key

# Task 2: a tunable denylist of field-name patterns known to be business-
# specific — configuration, not literals in the resolution path (Dev
# Notes: this will not transfer across domains, and that's expected; the
# Test Data Pool is what actually solves this problem long-term).
_BUSINESS_SPECIFIC_RE = re.compile(
    r"policy|account|claim|invoice|ssn|social[\s_-]?security|member[\s_-]?id|"
    r"tax[\s_-]?id|routing[\s_-]?number|order[\s_-]?number",
    re.IGNORECASE,
)

_WILDCARD_ROUTE_FAMILY = "*"


@dataclass(frozen=True)
class PoolEntry:
    """A resolved (already Vault-decrypted, if sensitive) pool value, plus
    whether it must be masked wherever it's logged (Story 2.20 AC 6)."""

    value: str
    is_sensitive: bool = False


@dataclass(frozen=True)
class ResolvedValue:
    value: str
    source: str  # "pool" | "reused" | "synthetic" — never "page" (step 2 not built)
    is_sensitive: bool = False


class ResolutionLog:
    """Per-run bookkeeping for step 3 (reuse) and the success-feedback
    demotion set (AC 2/3) — one instance per Discovery Run, alongside the
    Test Data Pool loaded at activity start."""

    def __init__(self) -> None:
        self._successful: dict[str, str] = {}
        # AC 3: (field key, value) pairs the application has rejected.
        # Checked before *any* step accepts a value, not just step 3/4 —
        # a pool-sourced value the app turns out to reject shouldn't be
        # re-submitted unchanged either.
        self._demoted: set[tuple[str, str]] = set()

    def is_demoted(self, field_key: str, value: str) -> bool:
        return (field_key, value) in self._demoted

    def record_outcome(self, field_key: str, value: str, outcome: str) -> None:
        """AC 2/3. `outcome` is "success" | "rejected" | "unknown" — an
        "unknown" outcome (the common case: most actions don't produce an
        unambiguous signal either way) intentionally leaves prior state
        alone rather than guessing."""
        if outcome == "success":
            self._successful[field_key] = value
        elif outcome == "rejected":
            self._demoted.add((field_key, value))
            if self._successful.get(field_key) == value:
                del self._successful[field_key]

    def reused_value(self, field_key: str) -> str | None:
        value = self._successful.get(field_key)
        if value is not None and not self.is_demoted(field_key, value):
            return value
        return None


def field_key(field_name: str, input_type: str) -> str:
    """The run-wide key reuse/demotion operate on — always the wildcard
    route family (see module docstring)."""
    return aggregation_key(field_name, input_type, _WILDCARD_ROUTE_FAMILY)


def is_business_specific(field_name: str) -> bool:
    """AC 1/5 (Task 2): a field synthesis must never touch — the resolver
    returns unresolved (DEFER) for these when no pool/reused value covers
    them, rather than inventing a business-specific-looking value."""
    return bool(_BUSINESS_SPECIFIC_RE.search(field_name or ""))


def resolve(
    *,
    field_name: str,
    input_type: str,
    route_family: str,
    pool: dict[str, PoolEntry],
    log: ResolutionLog,
    generic_value: str,
) -> ResolvedValue | None:
    """AC 1: the five-step order. `generic_value` is step 4's synthesized
    candidate, computed by the caller via the existing
    `crawler._generic_value` (kept there — this module extends, not
    replaces, Story 2.2's heuristic, per Dev Notes). Returns `None` only
    when every step is exhausted (step 5: unresolved -> the Planner DEFERs).
    """
    key = field_key(field_name, input_type)

    # Step 1: the Test Data Pool — real route family first, then the
    # wildcard every seed-time-agnostic entry is stored under.
    for pool_key in (
        aggregation_key(field_name, input_type, route_family),
        aggregation_key(field_name, input_type, _WILDCARD_ROUTE_FAMILY),
    ):
        entry = pool.get(pool_key)
        if entry is not None and not log.is_demoted(key, entry.value):
            return ResolvedValue(value=entry.value, source="pool", is_sensitive=entry.is_sensitive)

    # Step 2 (scan the current page) — not built, see module docstring.

    # Step 3: reuse a value that worked earlier this run.
    reused = log.reused_value(key)
    if reused is not None:
        return ResolvedValue(value=reused, source="reused")

    # Step 4: safe synthesis — never for a business-specific-looking field.
    if is_business_specific(field_name):
        return None
    if log.is_demoted(key, generic_value):
        # The one synthetic value this heuristic would produce has already
        # been rejected — nothing left to try (Dev Notes: no per-field
        # bisection retry loop; this is deliberately as far as it goes).
        return None
    return ResolvedValue(value=generic_value, source="synthetic")
