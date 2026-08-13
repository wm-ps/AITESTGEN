"""Deterministic (non-LLM) grounding check for LLM-generated Playwright locators.

The Playwright-generation prompt (`ai_provider.hosted`) grounds the LLM in real,
discovery-captured `known_locators`/`known_pages`, but explicitly still permits it
to "invent your own locator... for an element with no match here." Nothing
previously checked whether an invented locator was actually real or a
hallucination — the only existing gate (`typecheck.typecheck_playwright_code`) is a
`tsc --noEmit` syntax/types check, which happily compiles a locator string that can
never resolve to anything on the real target application. That's a generic
contributor to `toBeVisible()`/`element(s) not found` failures across different
applications, not something a longer timeout can fix.

This module is the missing check: given the code the LLM wrote and a
`GroundingContext` built from what Discovery actually captured for the Journey's
pages, find every locator argument that isn't backed by real captured data — either
verbatim, or as a safe CSS-attribute derivation from a real captured form field's
`name`/`type` — so the caller (`generation_worker.activities`) can reject it and
retry generation with the specific offending locator and a real alternative named,
instead of silently persisting a test that was never going to resolve.

Deliberately regex-based, not a full TypeScript/AST parser — same "shell out only
when strictly necessary" precedent `typecheck.py` already sets by invoking `tsc`
rather than embedding a JS parser. Scope is intentionally narrower than every
locator-producing Playwright call: only `page.locator(...)` / `resolveUnique(...)` /
`clickWhenReady(...)` (including combined, comma-separated CSS-attribute
selectors — the exact pattern the prompt asks for, and the exact pair of
deterministic helpers the prompt now routes every element interaction through),
`getByLabel(...)`, and `getByRole(...)` are checked, because those are the call
shapes the prompt actually grounds in captured DOM data (`known_locators`/labels/
accessible names). `getByText`/`getByPlaceholder`/`getByTestId`/`getByTitle`/
`getByAltText` are left unchecked here — the prompt legitimately allows those for
assertion text taken verbatim from Test data/Expected result (never discoverable
from crawl DOM at all), and flagging them without any corresponding captured-data
set to ground against would only produce false-positive violations that a
regeneration retry could never actually resolve.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FIELD_NAME_SENTINEL = "field"  # model_builder._get_or_create_component's null-sentinel


@dataclass(frozen=True)
class FillFieldMeta:
    """A real captured form field's HTML `name`/`type` attributes — what
    `input[name="..."]`/`input[type="..."]` locators are allowed to be derived
    from, in place of the LLM guessing."""

    name: str
    input_type: str


@dataclass(frozen=True)
class GroundingContext:
    """Everything Discovery actually captured for one Journey's pages, in the
    shape this module needs to check a locator string against — built once per
    `PlaywrightGenerationActivity` call from data the caller already fetched for
    `known_pages`/`known_locators` (no extra DB queries)."""

    locator_values: frozenset[str]
    label_values: frozenset[str]
    role_name_pairs: frozenset[tuple[str, str]]  # (role, accessible_name.lower())
    fill_field_metadata: tuple[FillFieldMeta, ...]

    @property
    def is_empty(self) -> bool:
        return not (
            self.locator_values or self.label_values or self.role_name_pairs
            or self.fill_field_metadata
        )


@dataclass(frozen=True)
class GroundingViolation:
    call_snippet: str
    locator_text: str
    suggested_alternative: str | None


def build_grounding_context(
    known_locators: list[dict[str, str]] | None,
) -> GroundingContext:
    """Derives a `GroundingContext` from the same `known_locators` list already
    built for the AI prompt (`generation_worker.activities._resolve_known_
    application_model_sync`) — no new query, no new shape the prompt-facing
    code needs to change."""
    locator_values: set[str] = set()
    label_values: set[str] = set()
    role_name_pairs: set[tuple[str, str]] = set()
    fill_field_metadata: list[FillFieldMeta] = []

    for loc in known_locators or []:
        selector = loc.get("selector", "")
        strategy = loc.get("strategy", "")
        if not selector:
            continue
        if strategy == "label":
            label_values.add(selector)
            continue
        locator_values.add(selector)
        role_match = _ARIA_LOCATOR_RE.match(selector)
        if role_match:
            role_name_pairs.add((role_match.group("role"), role_match.group("name").lower()))
        component_type = loc.get("component_type", "")
        component_name = loc.get("component_name", "")
        if component_type and component_name and component_name != _FIELD_NAME_SENTINEL:
            # A "fill" Component's `name` is the real captured `FormField.name`
            # (model_builder.derive_components_and_assertions sets it exactly
            # that way) and its `type` is the real captured `FormField.input_type`
            # — safe to offer as a derivation target regardless of which
            # strategy happened to be `known_locators`' chosen best for it.
            fill_field_metadata.append(FillFieldMeta(name=component_name, input_type=component_type))

    return GroundingContext(
        locator_values=frozenset(locator_values),
        label_values=frozenset(label_values),
        role_name_pairs=frozenset(role_name_pairs),
        fill_field_metadata=tuple(fill_field_metadata),
    )


_ARIA_LOCATOR_RE = re.compile(r'^role=(?P<role>\w+)\[name="(?P<name>.*)"\]$')

# `page.locator('...')` / `somePriorExpression.locator("...")` — the base
# call shape every derived Locator (`.first()`, `.filter()`, etc chained after)
# still starts from. Deliberately not anchored to `page.` specifically — a
# sub-query off an already-resolved Locator should be grounded the same way.
_LOCATOR_CALL_RE = re.compile(r'\.locator\(\s*([\'"])((?:(?!\1).)*)\1')
# `resolveUnique(page, '<selector>', description)` / `clickWhenReady(...)` —
# the deterministic helpers the prompt (`ai_provider.hosted`) now instructs
# the model to route every element interaction through instead of a bare
# `.locator(...).first()`. The selector is a plain function argument here,
# not a `.locator(` method call, so it needs its own extraction pattern.
_HELPER_CALL_RE = re.compile(
    r"\b(?:resolveUnique|clickWhenReady)\(\s*\w+\s*,\s*([\'\"])((?:(?!\1).)*)\1"
)
_GET_BY_LABEL_RE = re.compile(r'\.getByLabel\(\s*([\'"])((?:(?!\1).)*)\1')
_GET_BY_ROLE_RE = re.compile(
    r"\.getByRole\(\s*([\'\"])(\w+)\1\s*,\s*\{[^}]*?name:\s*"
    r'(?:([\'"])((?:(?!\3).)*)\3|/((?:[^/\\]|\\.)*)/(i?))'
)
_HAS_TEMPLATE_INTERPOLATION_RE = re.compile(r"\$\{")


def _split_top_level(selector: str) -> list[str]:
    """Splits a combined CSS-attribute selector on top-level commas (the exact
    `'input[name="x"], input[type="y"]'` pattern the prompt asks for) — bracket
    -aware so a comma that could theoretically appear inside `[...]` never
    causes a false split."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in selector:
        if char == "[":
            depth += 1
        elif char == "]":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return [p for p in parts if p]


def _is_safe_derived_css_attribute(branch: str, context: GroundingContext) -> bool:
    """Rule 4 — allow exactly `input[name="X"]`, `input[type="Y"]`, or
    `input[type="Y"][name="X"]` (either attribute order) when `(X, Y)` matches a
    real captured `FillFieldMeta` — i.e. what the prompt's own Locator rules
    already instruct the model to build, backed by real captured metadata
    instead of the model's guess."""
    match = re.fullmatch(
        r'input(\[name="(?P<name>[^"]*)"\]|\[type="(?P<type>[^"]*)"\])+', branch
    )
    if not match:
        return False
    names = set(re.findall(r'\[name="([^"]*)"\]', branch))
    types = set(re.findall(r'\[type="([^"]*)"\]', branch))
    if len(names) > 1 or len(types) > 1:
        return False
    name = next(iter(names), None)
    input_type = next(iter(types), None)
    if not name and not input_type:
        return False
    for field in context.fill_field_metadata:
        if name is not None and name != field.name:
            continue
        if input_type is not None and input_type != field.input_type:
            continue
        return True
    return False


def _check_locator_branch(branch: str, context: GroundingContext) -> bool:
    if branch in context.locator_values:
        return True
    return _is_safe_derived_css_attribute(branch, context)


def _suggest_alternative(context: GroundingContext) -> str | None:
    if context.fill_field_metadata:
        field = context.fill_field_metadata[0]
        return f'input[name="{field.name}"]'
    if context.locator_values:
        return next(iter(context.locator_values))
    return None


def find_ungrounded_locators(code: str, context: GroundingContext) -> list[GroundingViolation]:
    """Returns every locator argument in `code` that isn't backed by real
    captured DOM data in `context` — empty means every checked locator is
    grounded. An empty `context` (a Journey with no captured pages/components
    at all) short-circuits to no violations — nothing to ground against means
    nothing to reject; the LLM had no known data to work from either."""
    if context.is_empty:
        return []

    violations: list[GroundingViolation] = []

    for pattern in (_LOCATOR_CALL_RE, _HELPER_CALL_RE):
        for match in pattern.finditer(code):
            value = match.group(2)
            if _HAS_TEMPLATE_INTERPOLATION_RE.search(value):
                continue  # computed at runtime — unresolvable statically, accepted gap
            branches = _split_top_level(value)
            if not branches or not all(_check_locator_branch(b, context) for b in branches):
                violations.append(
                    GroundingViolation(
                        call_snippet=match.group(0),
                        locator_text=value,
                        suggested_alternative=_suggest_alternative(context),
                    )
                )

    for match in _GET_BY_LABEL_RE.finditer(code):
        value = match.group(2)
        if _HAS_TEMPLATE_INTERPOLATION_RE.search(value):
            continue
        if value not in context.label_values:
            violations.append(
                GroundingViolation(
                    call_snippet=match.group(0),
                    locator_text=value,
                    suggested_alternative=next(iter(context.label_values), None)
                    or _suggest_alternative(context),
                )
            )

    for match in _GET_BY_ROLE_RE.finditer(code):
        role = match.group(2)
        name_text = match.group(4) if match.group(4) is not None else match.group(5)
        if name_text is None or _HAS_TEMPLATE_INTERPOLATION_RE.search(name_text):
            continue
        name_lower = name_text.lower()
        grounded = any(
            role == pair_role and (name_lower == pair_name or name_lower in pair_name)
            for pair_role, pair_name in context.role_name_pairs
        )
        if not grounded:
            violations.append(
                GroundingViolation(
                    call_snippet=match.group(0),
                    locator_text=f'getByRole("{role}", {{ name: "{name_text}" }})',
                    suggested_alternative=_suggest_alternative(context),
                )
            )

    return violations


def format_feedback(violations: list[GroundingViolation]) -> str:
    """Renders violations as prompt-ready feedback text — see
    `ai_provider.hosted._describe_grounding_feedback`, which wraps this in the
    section header/framing the model sees."""
    lines = []
    for v in violations:
        alt = f' A real captured alternative is: {v.suggested_alternative!r}.' if (
            v.suggested_alternative
        ) else ""
        lines.append(
            f"- {v.call_snippet} — {v.locator_text!r} does not match any locator actually "
            f"discovered on this application during crawling, and is not a safe CSS-attribute "
            f"derivation from a real captured form field.{alt}"
        )
    return "\n".join(lines)


__all__ = [
    "FillFieldMeta",
    "GroundingContext",
    "GroundingViolation",
    "build_grounding_context",
    "find_ungrounded_locators",
    "format_feedback",
]
