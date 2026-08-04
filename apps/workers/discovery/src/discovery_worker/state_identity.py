"""State Identity Engine — SAME/VARIANT/NEW classification (Story 2.10).

Pure Python, no Playwright and no DB — `crawler.py` captures the raw
signals (heading, structural skeleton tokens), `activities.py` owns the
in-process cache's lifetime and persistence (AD-16: a plain dict scoped to
one `DiscoveryActivity` execution, no Redis). This module owns route
templating, fingerprint scoring, and the widened-mode decision.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from discovery_worker.crawler import _page_fingerprint

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD_SAME = 0.75
DEFAULT_THRESHOLD_NEW = 0.35

# AC 2 weights.
_WEIGHT_HEADING = 0.30
_WEIGHT_ACTIONS = 0.35
_WEIGHT_FORMS = 0.15
_WEIGHT_STRUCTURE = 0.20

# Task 3: below this many observed states, widening isn't evaluated at all —
# a handful of states sharing one template is completely normal early in a
# crawl, not evidence of a no-URL-change SPA.
_MIN_STATES_FOR_WIDENED_CHECK = 5
# Task 3: distinct_templates / distinct_states below this ratio means route
# templates aren't discriminating this run.
_WIDENED_TEMPLATE_RATIO = 0.2
# Task 3's O(n^2) guard: bound how many cached states a widened-mode
# candidate compares against, most-recent-first.
_WIDENED_COMPARISON_BOUND = 30

_ID_SEGMENT_RE = re.compile(
    r"^[0-9]+$"
    r"|^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    r"|^[0-9a-fA-F]{16,}$"
)


def _is_id_segment(segment: str) -> bool:
    return bool(segment) and bool(_ID_SEGMENT_RE.match(segment))


def _template_path(path: str) -> str:
    return "/".join("{id}" if _is_id_segment(seg) else seg for seg in path.split("/"))


def route_template(url: str) -> str:
    """AC 1: collapse numeric/UUID-shaped path segments to `{id}`
    (`/claims/1001` -> `/claims/{id}`). Extends Story 2.2's
    `_page_fingerprint` normalization (OAuth-param stripping, the
    empty-vs-real-fragment distinction) rather than re-deriving it — a
    second URL normalizer here would drift out of sync with the BFS's own
    dedup key. Hash-routed SPA fragments (`#/orders/1001`) are a route path
    too, so their segments are templated the same way."""
    normalized = _page_fingerprint(url)
    base, _, fragment = normalized.partition("#")
    split = urlsplit(base)
    result = urlunsplit(split._replace(path=_template_path(split.path), query=""))
    if fragment:
        result = f"{result}#{_template_path(fragment.lstrip('!'))}"
    return result


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class StateFingerprint:
    """The four AC 2 signals for one observed state. `structural_tokens`
    must include tokens contributed by open shadow roots (Story 2.14) —
    two states differing only inside shadow DOM must not score identical
    (AC 6)."""

    heading: str
    action_names: frozenset[str]
    form_field_names: frozenset[str]
    structural_tokens: frozenset[str]


def compute_fingerprint(
    heading: str | None,
    action_names: list[str],
    form_field_names: list[str],
    structural_tokens: list[str],
) -> StateFingerprint:
    return StateFingerprint(
        heading=(heading or "").strip().lower(),
        action_names=frozenset(a.strip().lower() for a in action_names if a),
        form_field_names=frozenset(f.strip().lower() for f in form_field_names if f),
        structural_tokens=frozenset(structural_tokens),
    )


@dataclass(frozen=True)
class ScoreResult:
    """AC 5: the composite plus every component — required diagnostic
    output, not debug extras."""

    composite: float
    heading_score: float
    action_score: float
    form_score: float
    structure_score: float


def score(a: StateFingerprint, b: StateFingerprint) -> ScoreResult:
    """AC 2/9: weighted 0.30/0.35/0.15/0.20 composite over heading exact-
    match, action-set Jaccard, form-field-set Jaccard, and structural-token
    Jaccard (which is what makes AC 6 hold: differing shadow content changes
    the token set, so the structural component can't score 1.0 on its own)."""
    heading_score = 1.0 if a.heading == b.heading else 0.0
    action_score = _jaccard(a.action_names, b.action_names)
    form_score = _jaccard(a.form_field_names, b.form_field_names)
    structure_score = _jaccard(a.structural_tokens, b.structural_tokens)
    composite = (
        _WEIGHT_HEADING * heading_score
        + _WEIGHT_ACTIONS * action_score
        + _WEIGHT_FORMS * form_score
        + _WEIGHT_STRUCTURE * structure_score
    )
    return ScoreResult(composite, heading_score, action_score, form_score, structure_score)


@dataclass
class CachedState:
    page_id: uuid.UUID
    url: str
    route_template: str
    fingerprint: StateFingerprint


@dataclass
class ClassificationResult:
    verdict: str  # "SAME" | "VARIANT" | "NEW"
    matched_page_id: uuid.UUID | None
    score_result: ScoreResult | None
    ambiguous: bool
    widened_mode: bool
    route_template: str
    # The matched candidate's own fingerprint — lets a caller build a
    # meaningful AI-tiebreaker prompt (AC 3) without this module knowing
    # anything about prompts itself.
    matched_fingerprint: StateFingerprint | None = None
    ai_opinion: str | None = None


class StateIdentityCache:
    """AC 7: in-process, per-`DiscoveryActivity`-execution cache (AD-16) —
    seeded from canonical `Page` rows at Activity start, grown in memory as
    this run classifies. No Redis, not even behind a flag."""

    def __init__(
        self,
        threshold_same: float = DEFAULT_THRESHOLD_SAME,
        threshold_new: float = DEFAULT_THRESHOLD_NEW,
    ) -> None:
        self.threshold_same = threshold_same
        self.threshold_new = threshold_new
        self._by_template: dict[str, list[CachedState]] = {}
        self._states: list[CachedState] = []
        self._widened_logged = False

    def seed(self, states: list[CachedState]) -> None:
        for state in states:
            self._index(state)

    def _index(self, state: CachedState) -> None:
        self._states.append(state)
        self._by_template.setdefault(state.route_template, []).append(state)

    def register(
        self,
        page_id: uuid.UUID,
        url: str,
        fingerprint: StateFingerprint,
        template: str | None = None,
    ) -> None:
        """Called by the caller (`activities.py`) once a NEW or VARIANT page
        has actually been persisted and has a real `page_id` — `classify()`
        itself never mutates the cache, since it's called before that id
        exists."""
        self._index(
            CachedState(
                page_id=page_id,
                url=url,
                route_template=template or route_template(url),
                fingerprint=fingerprint,
            )
        )

    @property
    def widened_mode(self) -> bool:
        """Task 3 AC 4: route templates provide no discrimination when a
        handful of distinct templates cover many distinct states — the
        classic no-URL-change SPA (older Angular, Ext JS, in-memory
        dashboards)."""
        if len(self._states) < _MIN_STATES_FOR_WIDENED_CHECK:
            return False
        return (len(self._by_template) / len(self._states)) < _WIDENED_TEMPLATE_RATIO

    def classify(self, url: str, fingerprint: StateFingerprint) -> ClassificationResult:
        template = route_template(url)
        widened = self.widened_mode
        if widened and not self._widened_logged:
            # AC 4: logged once per run, with the evidence — never silently.
            self._widened_logged = True
            logger.warning(
                "state_identity: route_discrimination=none — %d distinct template(s) covering "
                "%d distinct state(s); widening to content-derived signals for the rest of this "
                "run. Dominant template: %r",
                len(self._by_template),
                len(self._states),
                max(self._by_template, key=lambda t: len(self._by_template[t])),
            )

        if widened:
            # Task 3's O(n^2) guard — bound the comparison set rather than
            # compare a candidate against every cached state.
            candidates = self._states[-_WIDENED_COMPARISON_BOUND:]
        else:
            candidates = self._by_template.get(template, [])

        if not candidates:
            return ClassificationResult(
                verdict="NEW",
                matched_page_id=None,
                score_result=None,
                ambiguous=False,
                widened_mode=widened,
                route_template=template,
            )

        best_state = candidates[0]
        best_score = score(fingerprint, best_state.fingerprint)
        for candidate in candidates[1:]:
            result = score(fingerprint, candidate.fingerprint)
            if result.composite > best_score.composite:
                best_state, best_score = candidate, result

        if best_score.composite >= self.threshold_same:
            verdict, matched, ambiguous = "SAME", best_state.page_id, False
        elif best_score.composite <= self.threshold_new:
            verdict, matched, ambiguous = "NEW", None, False
        else:
            # AC 3: the ambiguous band's deterministic verdict is VARIANT —
            # favoring a new sibling row over a silent merge, since getting
            # this wrong deletes real behaviour (Dev Notes). The AI opinion
            # attached by the caller is evidence only; it never flips this.
            verdict, matched, ambiguous = "VARIANT", best_state.page_id, True

        return ClassificationResult(
            verdict=verdict,
            matched_page_id=matched,
            score_result=best_score,
            ambiguous=ambiguous,
            widened_mode=widened,
            route_template=template,
            matched_fingerprint=best_state.fingerprint if matched is not None else None,
        )
