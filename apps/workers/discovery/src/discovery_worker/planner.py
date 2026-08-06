"""Exploration Planner — action tiering, the specialist decision chain, and
the State Return ladder (Story 2.11, spine boxes C/D/E/F).

The Planner has no intelligence of its own (Dev Notes): it asks each
specialist exactly one question, in a fixed order, and combines the answers
into one Execution Decision. Safety and data-resolution logic never lives
here, even as a placeholder — this module ships PASS-THROUGH specialists
that reproduce today's behaviour (everything executes), so this story is
independently shippable before Stories 2.12/2.13/2.19 exist; each later
story replaces one default with a real implementation, without touching
this module's control flow.
"""

import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from discovery_worker import state_identity

logger = logging.getLogger(__name__)

TIER_IN_PAGE = 1
TIER_NAVIGATION = 2


@dataclass(frozen=True)
class ActionCandidate:
    """Enough about one candidate to tier it (AC 1) and run it through the
    specialist chain (AC 3)."""

    label: str
    role: str | None
    in_landmark: bool  # inside a <nav>/sidebar/menu/breadcrumb landmark
    source_route_template: str
    target_route_template: str | None = None  # None when there's no href at all
    # Story 2.19 AC 2a: the specific state instance this candidate is being
    # evaluated from (e.g. a page fingerprint) — distinct from
    # `source_route_template`, which is the *family* (`/product/{id}`) that
    # AC 2c's route-normalization guard operates on. Optional and unused by
    # tiering; defaults to `source_route_template` when a caller doesn't set
    # it (every pre-Story-2.19 caller/test).
    state_key: str | None = None
    # Settings page's Interaction Level: what kind of action this is, so
    # `InteractionLevelGate` can decide whether the configured tier permits
    # it. Defaults to "click" — the only kind any real caller constructs
    # today (`_click_standalone_buttons`); "view"/"form_fill"/"modal"/
    # "drag_drop"/"multi_step" exist for future callers to tag once other
    # interaction types are threaded through the specialist chain too.
    action_kind: str = "click"


def classify_tier(candidate: ActionCandidate) -> int:
    """AC 1: deterministic rules, checked in this order —
    1. `role="tab"` is always Tier 1 (in-page), regardless of position.
    2. Inside a nav/sidebar/menu/breadcrumb landmark -> Tier 2.
    3. An `href` resolving to a different route template -> Tier 2.
    4. Otherwise -> Tier 1 (same-page anchor, no route-changing href,
       outside nav/menu landmarks).

    Genuinely ambiguous cases (AC 1's AI fallback) are the caller's problem:
    this function is the deterministic core and always returns an answer —
    there is nothing left to be ambiguous about once tag/landmark/href are
    known. A caller that can't determine `in_landmark`/route templates
    confidently should ask the AI *before* calling this, not after.
    """
    if candidate.role == "tab":
        return TIER_IN_PAGE
    if candidate.in_landmark:
        return TIER_NAVIGATION
    if (
        candidate.target_route_template is not None
        and candidate.target_route_template != candidate.source_route_template
    ):
        return TIER_NAVIGATION
    return TIER_IN_PAGE


@dataclass(frozen=True)
class SpecialistVerdict:
    """`decision=None` means "no opinion, defer to the next specialist (or
    the default)" — this is what every pass-through implementation returns."""

    decision: str | None  # None | "EXECUTE" | "DEFER" | "SKIP"
    reason: str


SpecialistFn = Callable[[ActionCandidate], SpecialistVerdict]


def default_loop_guard(candidate: ActionCandidate) -> SpecialistVerdict:
    """Pass-through — Story 2.19 replaces this with real loop/budget
    guards. Allows everything, exactly today's behaviour."""
    return SpecialistVerdict(None, "pass-through: loop guards not yet built (Story 2.19)")


# Story 2.19 AC 3: a final, configurable backstop only — not a return to
# Story 2.3's removed MAX_ITERATIONS. Set deliberately high so it never bites
# a real crawl; it exists purely to bound the genuinely pathological case
# none of the other guards catch. `ponytail:` this default has not had
# explicit PM sign-off per this story's own Dev Notes (it partially retires
# PRD §12 Risk item 7's accepted-risk statement) — revisit the number, not
# the mechanism, if that sign-off narrows it.
DEFAULT_ACTION_CEILING = 5000
# AC 2c: how many instances of the "same" action (same label, same route
# family) get sampled before the rest of that family is treated as a
# parameterized duplicate — deliberately small, matches the spirit of
# Representative-action sampling (AC 6 elsewhere) applied across pages
# instead of within one.
DEFAULT_ROUTE_FAMILY_CAP = 3
# AC 2b: how many recent transitions are kept to detect a short A->B->A->B
# cycle. Only the last 4 matter for the check itself; a little slack beyond
# that avoids discarding an edge on the exact boundary.
_CYCLE_WINDOW = 8


class LoopGuardState:
    """Story 2.19: the Planner's own bookkeeping — action history and
    transition-cycle detection are genuinely new; route normalization,
    scroll/pagination budget and the state-return budget delegate to
    Stories 2.10/2.9/2.11 rather than reimplementing them (AC 3, Dev Notes).
    One instance per crawl (`run_discovery_crawl`), threaded through every
    `decide()` call as the `loop_guard` specialist (always asked first,
    AC 1) via `guard()`; `record_executed`/`record_transition` are called by
    the crawl loop at the two points this class can't observe on its own —
    once a candidate is confirmed EXECUTE, and once a real transition lands.
    """

    def __init__(
        self,
        route_family_cap: int = DEFAULT_ROUTE_FAMILY_CAP,
        action_ceiling: int = DEFAULT_ACTION_CEILING,
    ) -> None:
        self.route_family_cap = route_family_cap
        self.action_ceiling = action_ceiling
        # AC 2a: keyed on (state, action identity) — the accessible name
        # (`label`), not DOM position, so a repeat is caught even after a
        # state return re-renders the DOM in a different order.
        self._executed: set[tuple[str, str]] = set()
        # AC 2c: keyed on (route family, action identity), independent of
        # the specific state instance — this is what actually bounds a
        # "same button on every one of 500 product pages" pattern that
        # AC 2a alone (keyed per exact page) would never catch.
        self._route_family_counts: dict[tuple[str, str], int] = {}
        # `label` is part of the edge identity (not just from/to) — see
        # `record_transition`'s docstring for why a hub page's distinct
        # sibling links must not be confused with a genuine repeated action.
        self._edges: deque[tuple[str, str, str]] = deque(maxlen=_CYCLE_WINDOW)
        self._action_count = 0

    def _state_key(self, candidate: ActionCandidate) -> str:
        return candidate.state_key or candidate.source_route_template

    def _is_cycling(self) -> bool:
        """AC 2b: a short A->B->A->B oscillation in the most recent
        transitions — the last edge repeats the one two before it, and the
        edge before that repeats the one two before *that*, and the two
        directions genuinely differ (rules out a same-edge repeat, which
        AC 2a's action-history already handles on its own terms)."""
        edges = self._edges
        if len(edges) < 4:
            return False
        return (
            edges[-1] == edges[-3] and edges[-2] == edges[-4] and edges[-1] != edges[-2]
        )

    def guard(self, candidate: ActionCandidate) -> SpecialistVerdict:
        """AC 1-4/2a-2f, in the fixed sub-order the story specifies. A fired
        guard returns SKIP with a reason naming which guard fired — Story
        2.11's call site already forwards `reason`/`deciding_specialist`
        into `on_diagnostic` (AC 4), so no separate diagnostics path is
        needed here."""
        self._action_count += 1
        if self._action_count > self.action_ceiling:
            return SpecialistVerdict(
                "SKIP", f"depth/action ceiling reached ({self.action_ceiling} actions this run)"
            )
        state_key = self._state_key(candidate)
        # `in_landmark` is part of both keys below — apps reuse the same
        # accessible name for controls that aren't duplicates of each other
        # at all (e.g. a header hamburger and every per-row grid "..." action
        # menu both reporting `aria-label="Menu"`; see `crawler.py`'s
        # `_click_standalone_buttons`, which makes the identical distinction
        # for its own, separate, in-page-visit dedup). Without it, whichever
        # one executes first permanently shadows the other for the rest of
        # this state/route family.
        action_key = (state_key, candidate.in_landmark, candidate.label)
        if action_key in self._executed:
            return SpecialistVerdict(
                "SKIP", f"action_history: {candidate.label!r} already executed from this state"
            )
        if self._is_cycling():
            return SpecialistVerdict(
                "SKIP", "transition_cycle: A->B->A->B pattern in recent transition history"
            )
        route_key = (candidate.source_route_template, candidate.in_landmark, candidate.label)
        route_count = self._route_family_counts.get(route_key, 0)
        if route_count >= self.route_family_cap:
            return SpecialistVerdict(
                "SKIP",
                f"route_normalization: {candidate.label!r} already sampled {route_count} "
                f"times across route family {candidate.source_route_template!r}",
            )
        # AC 2d/2e: the scroll/pagination budget (Story 2.9) and the
        # state-return budget (Story 2.11) are enforced where the actual
        # work happens — Story 2.9's own sampler state, and
        # `return_to_state`'s `DEFAULT_RETURN_BUDGET` — rather than
        # duplicated here against a copy this class would have to keep in
        # sync (Dev Notes: "these are backstops, not the primary mechanism").
        return SpecialistVerdict(None, "loop guards clear")

    def record_executed(self, candidate: ActionCandidate) -> None:
        """Called once a candidate's Execution Decision is confirmed
        EXECUTE — not from inside `guard()`, since `guard()` runs before
        safety/data-resolution and can't yet know the final decision."""
        state_key = self._state_key(candidate)
        self._executed.add((state_key, candidate.in_landmark, candidate.label))
        route_key = (candidate.source_route_template, candidate.in_landmark, candidate.label)
        self._route_family_counts[route_key] = self._route_family_counts.get(route_key, 0) + 1

    def record_transition(self, from_state: str, to_state: str, label: str) -> None:
        """Called for every real transition the crawl observes — both a
        candidate's own forward navigation and a successful State Return
        ladder rung (Story 2.11), which is what makes a genuine A->B->A->B
        round-trip visible to `_is_cycling()` at all; a forward-only edge
        log would only ever show repeats of the same direction, which
        AC 2a's action-history already catches on its own.

        `label` (the triggering action, e.g. "Master Characteristics") is
        part of the edge identity. Without it, a hub page with N distinct
        sibling links (explore sibling, state-return to hub, explore next
        sibling) necessarily produces round trips between the *same two
        URLs* over and over — every sibling shares the hub's URL on one end
        — which `_is_cycling()` couldn't tell apart from a genuine repeated
        action bouncing between the same two states. Two different actions
        that happen to connect the same two pages are not a cycle; the same
        action doing it twice is."""
        self._edges.append((from_state, to_state, label))


_INTERACTION_LEVEL_ALLOWED_KINDS = {
    "passive": frozenset({"view"}),
    "normal": frozenset({"view", "click", "form_fill"}),
    "aggressive": frozenset({"view", "click", "form_fill", "modal", "drag_drop", "multi_step"}),
}


class InteractionLevelGate:
    """Settings page's Interaction Level (Passive/Normal/Aggressive) — a
    specialist independent of `SafetyState` (orthogonal by design): this
    gates *which kinds* of action are attempted at all; safety gates
    *whether a specific label* is safe to run once a kind is already
    permitted. Only `_click_standalone_buttons` (action_kind="click")
    routes through the specialist chain today, so Passive is the only tier
    with an observable effect right now — Aggressive's extra kinds
    (modal/drag_drop/multi_step) take effect once those interactions are
    also tagged and threaded through `decide()`.
    """

    def __init__(self, level: str) -> None:
        self.level = level

    def __call__(self, candidate: ActionCandidate) -> SpecialistVerdict:
        allowed = _INTERACTION_LEVEL_ALLOWED_KINDS.get(
            self.level, _INTERACTION_LEVEL_ALLOWED_KINDS["normal"]
        )
        if candidate.action_kind not in allowed:
            return SpecialistVerdict(
                "SKIP",
                f"interaction_level={self.level!r} does not permit "
                f"action_kind={candidate.action_kind!r}",
            )
        return SpecialistVerdict(None, "interaction level clear")


def default_safety(candidate: ActionCandidate) -> SpecialistVerdict:
    """Pass-through — Story 2.12 replaces this with the real Safety
    Engine. Treats everything as Safe, exactly today's behaviour."""
    return SpecialistVerdict(None, "pass-through: safety engine not yet built (Story 2.12)")


def default_data_resolver(candidate: ActionCandidate) -> SpecialistVerdict:
    """Pass-through — Story 2.13 replaces this with the real Data Resolver.
    `crawler.py`'s existing generic-value filling already supplies inputs
    inline, so this never has a reason to block, exactly today's
    behaviour."""
    return SpecialistVerdict(None, "pass-through: data resolver not yet built (Story 2.13)")


@dataclass(frozen=True)
class ExecutionDecision:
    action: str  # "EXECUTE" | "DEFER" | "SKIP"
    deciding_specialist: str
    reason: str


def decide(
    candidate: ActionCandidate,
    loop_guard: SpecialistFn = default_loop_guard,
    safety: SpecialistFn = default_safety,
    data_resolver: SpecialistFn = default_data_resolver,
    interaction_level: SpecialistFn | None = None,
) -> ExecutionDecision:
    """AC 3/7: asks loop guards, then safety (before data resolution, per
    AD-19: resolving inputs for an action that will never run is wasted
    work), then the data resolver, and takes the first one with an
    opinion. `interaction_level` (Settings page) is optional and, when
    given, is asked right after loop guards — both are coarse "should this
    kind of action even be tried" gates, cheaper to check than safety's
    label-content matching. No opinion from any of them means EXECUTE (AC
    4's default, and today's actual behaviour via the pass-through
    defaults above)."""
    specialists = [("loop_guard", loop_guard)]
    if interaction_level is not None:
        specialists.append(("interaction_level", interaction_level))
    specialists.append(("safety", safety))
    specialists.append(("data_resolver", data_resolver))
    for name, specialist in specialists:
        verdict = specialist(candidate)
        if verdict.decision is not None:
            return ExecutionDecision(verdict.decision, name, verdict.reason)
    return ExecutionDecision("EXECUTE", "default", "no specialist objected")


# AC 5: the State Return ladder's per-state budget (Task 5) — a real
# attempt count, not the theoretical rung count, since rung 1 is free and
# rungs 2-4 each cost one real navigation.
DEFAULT_RETURN_BUDGET = 4
# AC 5: what "matches" means for ladder confirmation — reuses Story 2.10's
# own SAME threshold rather than inventing a second one.
_RETURN_MATCH_THRESHOLD = state_identity.DEFAULT_THRESHOLD_SAME


@dataclass(frozen=True)
class ReturnResult:
    succeeded: bool
    rung: str  # "no_op" | "browser_back" | "renavigate" | "path_replay" | "gave_up"
    attempts_used: int


async def return_to_state(
    page: Any,
    pre_action_fingerprint: state_identity.StateFingerprint,
    target_url: str,
    capture_state_signals: Callable[[Any], Awaitable[tuple[str, list[str]]]],
    settle: Callable[[], Awaitable[None]],
    entry_url: str | None = None,
    return_budget: int = DEFAULT_RETURN_BUDGET,
) -> ReturnResult:
    """AC 5/6: rung 1 (no-op) -> rung 2 (browser back) -> rung 3
    (re-navigate) -> rung 4 (bounded path replay) -> rung 5 (give up).
    Every rung except (i) is confirmed by re-fingerprinting via Story 2.10
    before being accepted — a plausible-looking landing (a redirect to a
    dashboard, an expired-session bounce) is not good enough (Dev Notes).

    `capture_state_signals`/`settle` are injected rather than imported from
    `crawler.py` directly — this module stays testable with a fake page and
    has no import-time dependency on Playwright's real settle machinery.

    `ponytail:` rung 4 here is a bounded, honest substitute for "replay the
    shortest known action path" — this story's own Dev Notes attribute real
    per-state path bookkeeping to Stories 2.15/2.19, which don't exist yet.
    Revisiting `entry_url` (always Safe — it's where the crawl started) then
    retrying the direct re-navigation is a real, bounded two-step replay,
    not the full shortest-path replay; upgrade once path bookkeeping lands.
    """
    attempts = 0

    async def _matches() -> bool:
        heading, tokens = await capture_state_signals(page)
        current = state_identity.compute_fingerprint(heading, [], [], tokens)
        result = state_identity.score(pre_action_fingerprint, current)
        return result.composite >= _RETURN_MATCH_THRESHOLD

    if await _matches():
        return ReturnResult(True, "no_op", attempts)

    if attempts < return_budget:
        attempts += 1
        try:
            await page.go_back()
            await settle()
        except Exception:
            logger.info("state return rung 2 (browser_back) raised, treating as a miss")
        if await _matches():
            return ReturnResult(True, "browser_back", attempts)

    if attempts < return_budget:
        attempts += 1
        try:
            await page.goto(target_url)
            await settle()
        except Exception:
            logger.info("state return rung 3 (renavigate) raised, treating as a miss")
        if await _matches():
            return ReturnResult(True, "renavigate", attempts)

    if attempts < return_budget and entry_url:
        attempts += 1
        try:
            await page.goto(entry_url)
            await settle()
            await page.goto(target_url)
            await settle()
        except Exception:
            logger.info("state return rung 4 (path_replay) raised, treating as a miss")
        if await _matches():
            return ReturnResult(True, "path_replay", attempts)

    return ReturnResult(False, "gave_up", attempts)
