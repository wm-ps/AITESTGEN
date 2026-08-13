"""ApplicationModelBuilderActivity's merge/derivation logic (Story 2.5, AD-1/AD-8/AD-14).

Sibling to `crawler.py`/`identity_key.py` — keeps this logic out of the
already-large `activities.py`, which just calls into it.

Two jobs, in order:
1. **Merge (AC 1):** resolve `Page`/`Form`/`ApiEndpoint` rows that represent
   the same logical page/form/API — within this run and across every prior
   Discovery Run against the same Application — into one canonical row per
   group, via the self-referencing `merged_into_id` (null = canonical).
   Always re-resolved by querying current state (never assumed to be the
   first run), so this is idempotent under Temporal's at-least-once retry
   (AD-9): re-running never flips an already-resolved row back and forth.
2. **Derive (AC 2, 3):** `Component`/`ComponentLocator` for every automatable
   element (buttons/links grouped from canonical `Action` rows, one per
   canonical `FormField`), and `Assertion` from canonical
   `PageTransition`/`ApiEndpoint` outcomes. Find-or-create by a stable
   identity so re-running never duplicates a `Component`/`Assertion` row.
"""

import json
import re
import uuid
from urllib.parse import urlparse

from domain import (
    Action,
    ApiEndpoint,
    Assertion,
    Component,
    ComponentLocator,
    Form,
    FormField,
    Page,
    PageTransition,
)
from sqlmodel import Session, select

_SEGMENT_RE = re.compile(r"^[0-9a-fA-F-]{8,36}$|^\d+$")


def _url_template(url: str) -> str:
    """Normalizes a captured URL into a template for grouping — a segment
    that's purely numeric or a UUID becomes `{id}` (e.g. `/customers/123`
    and `/customers/456` both become `/customers/{id}`). A sound,
    non-binding default, same framing as the crawler's own traversal
    algorithm."""
    parsed = urlparse(url)
    segments = ["{id}" if _SEGMENT_RE.match(seg) else seg for seg in parsed.path.split("/")]
    return "/".join(segments)


def _resolve_merge(session: Session, rows: list, group_key) -> dict[uuid.UUID, uuid.UUID]:
    """Groups `rows` by `group_key(row)`, picks the lowest `id` (UUIDv7's
    time-ordering — the oldest) per group as canonical, and sets every other
    row's `merged_into_id` to point at it. Returns {row.id: canonical_id}
    for every row, including canonical ones (mapped to themselves).
    Idempotent: re-running with the same rows always resolves to the same
    canonical id and only writes when the value actually changes."""
    groups: dict[object, list] = {}
    for row in rows:
        groups.setdefault(group_key(row), []).append(row)

    resolution: dict[uuid.UUID, uuid.UUID] = {}
    for group_rows in groups.values():
        canonical = min(group_rows, key=lambda r: r.id)
        for row in group_rows:
            resolution[row.id] = canonical.id
            desired = None if row.id == canonical.id else canonical.id
            if row.merged_into_id != desired:
                row.merged_into_id = desired
                session.add(row)
    session.commit()
    return resolution


def merge_pages(session: Session, application_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
    pages = list(session.exec(select(Page).where(Page.application_id == application_id)).all())
    return _resolve_merge(session, pages, lambda p: _url_template(p.url))


def merge_forms(
    session: Session, application_id: uuid.UUID, page_resolution: dict[uuid.UUID, uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    forms = list(session.exec(select(Form).where(Form.application_id == application_id)).all())
    return _resolve_merge(
        session,
        forms,
        lambda f: (page_resolution.get(f.page_id, f.page_id), f.action_url, f.method),
    )


def merge_api_endpoints(
    session: Session, application_id: uuid.UUID
) -> dict[uuid.UUID, uuid.UUID]:
    endpoints = list(
        session.exec(select(ApiEndpoint).where(ApiEndpoint.application_id == application_id)).all()
    )
    return _resolve_merge(session, endpoints, lambda e: (e.method, _url_template(e.path)))


def dedupe_page_transitions(
    session: Session, application_id: uuid.UUID, page_resolution: dict[uuid.UUID, uuid.UUID]
) -> None:
    """`PageTransition` has no `merged_into_id` of its own — two edges
    between the same canonical page pair collapse to one row by simple
    find-or-create, once both ends resolve to canonical pages."""
    transitions = list(
        session.exec(
            select(PageTransition).where(PageTransition.application_id == application_id)
        ).all()
    )
    seen: dict[tuple, PageTransition] = {}
    for transition in sorted(transitions, key=lambda t: t.id):
        key = (
            page_resolution.get(transition.from_page_id, transition.from_page_id),
            page_resolution.get(transition.to_page_id, transition.to_page_id),
        )
        if key in seen:
            session.delete(transition)
        else:
            seen[key] = transition
    session.commit()


def _selector_strategy(value: str) -> str:
    if value.startswith("[data-testid"):
        return "testid"
    if value.startswith("text="):
        return "label"
    return "css"


# Story 2.21 AC 1/2/4: tier order for the ranked-candidate shape crawler.py's
# `_build_locator_candidates` produces (`{"strategy", "value", "fragile"}`,
# now also optionally carrying `"live_match_count"` — see `_is_live_invalid`
# below). Lower is more durable; a fragile match is penalized regardless of
# tier so it always sorts below every non-fragile candidate.
#
# `[FIXED — locator reliability hardening]` Must stay identical to crawler.py's
# `_LOCATOR_TIER_ORDER` — duplicated across both files by existing convention
# (see the note there) rather than extracted to a shared constant.
_CANDIDATE_TIER_ORDER = {
    "testid": 0,
    "data_attr": 1,
    "id": 2,
    "name": 3,
    "type_name": 4,
    "aria": 5,
    "label": 5,
    "css_scoped": 6,
    "css_absolute": 7,
    "text": 8,
}
_FRAGILE_SCORE_PENALTY = 10


def _is_live_invalid(candidate: dict) -> bool:
    """Mirrors crawler.py's `_is_live_invalid` — a candidate whose live
    `.count()` was checked during capture and resolved to 0 or >1 elements.
    `None` (never checked, or the check was inconclusive) is not invalid."""
    count = candidate.get("live_match_count")
    return count is not None and count != 1


def _rank_locator_candidates(candidate_lists: list[list[dict] | None]) -> list[dict]:
    """Flattens every raw capture's candidate list (one per Action/FormField
    in the group), dedupes by (strategy, value), and sorts non-fragile
    before fragile, then by tier — AC 2's down-rank, never discard. A
    live-invalid candidate (matched 0 or >1 elements when captured) sorts
    below everything else, same down-rank-never-discard treatment."""
    seen: set[tuple[str, str]] = set()
    flattened: list[dict] = []
    for candidates in candidate_lists:
        if not candidates:
            continue
        for candidate in candidates:
            key = (candidate.get("strategy", ""), candidate.get("value", ""))
            if key in seen or not candidate.get("value"):
                continue
            seen.add(key)
            flattened.append(candidate)
    flattened.sort(
        key=lambda c: (
            _is_live_invalid(c),
            bool(c.get("fragile")),
            _CANDIDATE_TIER_ORDER.get(c.get("strategy", ""), 9),
        )
    )
    return flattened


def _durability_score(candidate: dict) -> int:
    score = _CANDIDATE_TIER_ORDER.get(candidate.get("strategy", ""), 9)
    return score + _FRAGILE_SCORE_PENALTY if candidate.get("fragile") else score


def _get_or_create_component(
    session: Session,
    application_id: uuid.UUID,
    *,
    page_id: uuid.UUID,
    form_id: uuid.UUID | None,
    name: str,
    type_: str,
    action: str,
    target_page_id: uuid.UUID | None,
) -> Component:
    existing = session.exec(
        select(Component).where(
            Component.page_id == page_id,
            Component.form_id == form_id,
            Component.name == name,
        )
    ).first()
    if existing is not None:
        if existing.target_page_id != target_page_id and target_page_id is not None:
            existing.target_page_id = target_page_id
            session.add(existing)
            session.commit()
        return existing
    component = Component(
        application_id=application_id,
        page_id=page_id,
        form_id=form_id,
        name=name,
        type=type_,
        action=action,
        target_page_id=target_page_id,
    )
    session.add(component)
    session.commit()
    session.refresh(component)
    return component


def _derive_locators(
    session: Session,
    component: Component,
    raw_captures: list[tuple[str | None, list[dict] | None]],
) -> None:
    """Story 2.21: consumes each raw capture's ranked candidate list
    (`locator_candidates`) when present, falling back to a single candidate
    built from the legacy `captured_selector` string for rows captured
    before this story landed — existing `ComponentLocator` consumers keep
    working either way (AC 5)."""
    candidate_lists: list[list[dict] | None] = []
    for captured_selector, locator_candidates in raw_captures:
        if locator_candidates:
            candidate_lists.append(locator_candidates)
        elif captured_selector:
            candidate_lists.append(
                [
                    {
                        "strategy": _selector_strategy(captured_selector),
                        "value": captured_selector,
                        "fragile": False,
                    }
                ]
            )
    ranked = _rank_locator_candidates(candidate_lists)

    existing_values = {
        loc.value
        for loc in session.exec(
            select(ComponentLocator).where(ComponentLocator.component_id == component.id)
        ).all()
    }
    priority = 0
    for candidate in ranked:
        value = candidate["value"]
        if value in existing_values:
            priority += 1
            continue
        # `[FIXED — locator reliability hardening]` Fold live-invalidity
        # (matched 0 or >1 elements when captured, per crawler.py's new
        # `.count()` check) into the persisted `fragile` flag — no new column
        # needed; `_durability_score` above already penalizes `fragile=True`,
        # so a live-invalid candidate's score reflects that automatically.
        session.add(
            ComponentLocator(
                component_id=component.id,
                kind="preferred" if priority == 0 else "fallback",
                strategy=candidate.get("strategy", _selector_strategy(value)),
                value=value,
                priority=priority,
                fragile=bool(candidate.get("fragile")) or _is_live_invalid(candidate),
                durability_score=_durability_score(candidate),
            )
        )
        priority += 1
    session.commit()


def fragile_locator_proportion(session: Session, application_id: uuid.UUID) -> float | None:
    """Story 2.21 AC 4/Task 4: the aggregate Story 2.22's report surfaces —
    "N% of captured elements have no durable locator." Scoped to each
    Component's single best (`priority == 0`) locator, since a Component
    with *any* durable candidate is fine even if its fallbacks are fragile.
    Returns `None` when the Application has no locators yet, rather than a
    misleading 0%."""
    preferred = list(
        session.exec(
            select(ComponentLocator)
            .join(Component, ComponentLocator.component_id == Component.id)  # type: ignore[arg-type]
            .where(Component.application_id == application_id, ComponentLocator.priority == 0)
        ).all()
    )
    if not preferred:
        return None
    fragile_count = sum(1 for loc in preferred if loc.fragile)
    return fragile_count / len(preferred)


def derive_components_and_assertions(
    session: Session,
    application_id: uuid.UUID,
    page_resolution: dict[uuid.UUID, uuid.UUID],
    form_resolution: dict[uuid.UUID, uuid.UUID],
) -> int:
    component_count = 0

    # --- button/link Components, grouped from canonical Action rows ---
    actions = list(
        session.exec(select(Action).where(Action.application_id == application_id)).all()
    )
    action_groups: dict[tuple, list[Action]] = {}
    for action in actions:
        canonical_page_id = page_resolution.get(action.page_id, action.page_id)
        action_groups.setdefault((canonical_page_id, action.description), []).append(action)

    action_component_by_id: dict[uuid.UUID, Component] = {}
    for (canonical_page_id, description), group_actions in action_groups.items():
        component = _get_or_create_component(
            session,
            application_id,
            page_id=canonical_page_id,
            form_id=None,
            name=description,
            type_="button",
            action="click",
            target_page_id=None,
        )
        component_count += 1
        _derive_locators(
            session,
            component,
            [(a.captured_selector, a.locator_candidates) for a in group_actions],
        )
        for a in group_actions:
            action_component_by_id[a.id] = component

    # target_page_id: resolve via any PageTransition triggered by an Action
    # in this component's group.
    transitions = list(
        session.exec(
            select(PageTransition).where(PageTransition.application_id == application_id)
        ).all()
    )
    for transition in transitions:
        if transition.triggered_by_action_id is None:
            continue
        component = action_component_by_id.get(transition.triggered_by_action_id)
        if component is None or component.target_page_id is not None:
            continue
        component.target_page_id = page_resolution.get(
            transition.to_page_id, transition.to_page_id
        )
        session.add(component)
    session.commit()

    # --- form-field Components, one per canonical FormField ---
    forms = list(session.exec(select(Form).where(Form.application_id == application_id)).all())
    canonical_form_ids = {form_resolution.get(f.id, f.id) for f in forms}
    form_field_groups: dict[tuple, list[FormField]] = {}
    fields = list(
        session.exec(select(FormField).join(Form, FormField.form_id == Form.id)).all()  # type: ignore[arg-type]
    )
    for field_row in fields:
        canonical_form_id = form_resolution.get(field_row.form_id, field_row.form_id)
        if canonical_form_id not in canonical_form_ids:
            continue
        form_field_groups.setdefault((canonical_form_id, field_row.name), []).append(field_row)

    forms_by_id = {form.id: form for form in forms}
    for (canonical_form_id, field_name), group_fields in form_field_groups.items():
        canonical_form = forms_by_id.get(canonical_form_id)
        if canonical_form is None:
            continue
        canonical_page_id = page_resolution.get(canonical_form.page_id, canonical_form.page_id)
        sample_field = group_fields[0]
        component = _get_or_create_component(
            session,
            application_id,
            page_id=canonical_page_id,
            form_id=canonical_form_id,
            name=field_name or "field",
            type_=sample_field.input_type,
            action="fill",
            target_page_id=None,
        )
        component_count += 1
        _derive_locators(
            session,
            component,
            [(f.captured_selector, f.locator_candidates) for f in group_fields],
        )
        for field_row in group_fields:
            if field_row.component_id != component.id:
                field_row.component_id = component.id
                session.add(field_row)
    session.commit()

    # --- Assertions, derived from canonical PageTransition/ApiEndpoint outcomes ---
    for transition in transitions:
        canonical_from = page_resolution.get(transition.from_page_id, transition.from_page_id)
        canonical_to = page_resolution.get(transition.to_page_id, transition.to_page_id)
        component = (
            action_component_by_id.get(transition.triggered_by_action_id)
            if transition.triggered_by_action_id
            else None
        )
        expected = {"to_page_id": str(canonical_to)}
        _get_or_create_assertion(
            session,
            application_id,
            page_id=canonical_from,
            component_id=component.id if component else None,
            kind="state_transition",
            expected_value=expected,
        )

    endpoints = list(
        session.exec(select(ApiEndpoint).where(ApiEndpoint.application_id == application_id)).all()
    )
    for endpoint in endpoints:
        if endpoint.merged_into_id is not None:
            continue
        canonical_page_id = page_resolution.get(endpoint.page_id, endpoint.page_id)
        _get_or_create_assertion(
            session,
            application_id,
            page_id=canonical_page_id,
            component_id=None,
            kind="api_call",
            expected_value={"method": endpoint.method, "path": endpoint.path},
        )

    return component_count


def _get_or_create_assertion(
    session: Session,
    application_id: uuid.UUID,
    *,
    page_id: uuid.UUID,
    component_id: uuid.UUID | None,
    kind: str,
    expected_value: dict,
) -> Assertion:
    serialized = json.dumps(expected_value, sort_keys=True)
    existing = list(
        session.exec(
            select(Assertion).where(
                Assertion.page_id == page_id,
                Assertion.component_id == component_id,
                Assertion.kind == kind,
            )
        ).all()
    )
    for candidate in existing:
        if json.dumps(candidate.expected_value, sort_keys=True) == serialized:
            return candidate

    assertion = Assertion(
        application_id=application_id,
        page_id=page_id,
        component_id=component_id,
        kind=kind,
        expected_value=expected_value,
    )
    session.add(assertion)
    session.commit()
    session.refresh(assertion)
    return assertion


def build_application_model(session: Session, application_id: uuid.UUID) -> int:
    """Runs the full merge -> derive pipeline for one Application. Returns
    the number of Component rows that exist after this run (for the
    Activity's output)."""
    page_resolution = merge_pages(session, application_id)
    form_resolution = merge_forms(session, application_id, page_resolution)
    merge_api_endpoints(session, application_id)
    dedupe_page_transitions(session, application_id, page_resolution)
    return derive_components_and_assertions(
        session, application_id, page_resolution, form_resolution
    )
