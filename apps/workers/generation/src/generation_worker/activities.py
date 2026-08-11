"""ScenarioGenerationActivity — Story 4.1's first real Activity dispatch.

Fetches a Journey's attributed canonical rows (via its `JourneyStep`s),
attaches the same kind of transient capture context `InferenceActivity`
attaches to Pages before calling the AI provider, and persists the returned
`ScenarioCandidate`s as `Scenario` rows. Idempotent under Temporal's
at-least-once retry (AD-9): if `Scenario` rows already exist for this
Journey's current `(journey_id, generation_run_id)` pair, returns them
without re-generating.
"""

import asyncio
import logging
import re
import uuid

from ai_provider.hosted import HostedAIProvider
from domain import (
    ApiEndpoint,
    Component,
    ComponentLocator,
    DiscoverySettings,
    Form,
    Journey,
    JourneyStep,
    Page,
    Scenario,
    TestAsset,
    TestSuite,
)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from temporalio import activity
from workflows import (
    EnsureTestSuiteActivityInput,
    EnsureTestSuiteActivityResult,
    PlaywrightGenerationActivityInput,
    ScenarioGenerationActivityInput,
)

from generation_worker.db import engine
from generation_worker.typecheck import typecheck_playwright_code

logger = logging.getLogger(__name__)

# Non-AI, deterministic default-value generator (Story 4.2) — mirrors
# discovery_worker/crawler.py's `_generic_value` convention: a field's
# reviewer-provided value always wins; a still-blank field gets a sensible
# placeholder matching its own name, never a value the AI invents (Story 4.1
# AC 5's "the AI never fills in `value`" rule extends to this generator too,
# since it's separate, non-AI code).
_EMAIL_FIELD_RE = re.compile(r"user|email|login", re.IGNORECASE)
_PASSWORD_FIELD_RE = re.compile(r"pass(word)?", re.IGNORECASE)
_CARD_FIELD_RE = re.compile(r"card", re.IGNORECASE)


def _default_test_data_value(field_name: str, used_values: set[str]) -> str:
    if _PASSWORD_FIELD_RE.search(field_name):
        candidates = ("Password1$", "Password2$", "Password3$")
    elif _CARD_FIELD_RE.search(field_name):
        candidates = ("4111111111111111", "5555555555554444", "4000000000000002")
    elif _EMAIL_FIELD_RE.search(field_name):
        candidates = ("test@example.com", "test2@example.com", "test3@example.com")
    else:
        candidates = ("Test value", "Test value 2", "Test value 3")
    # Checklist rule 6: a scenario whose whole point is "X and Y differ"
    # (confirm-mismatch, before/after) needs genuinely distinct literals —
    # reusing the same pattern-matched placeholder for every same-shaped
    # field (e.g. "password" and "confirmPassword" both -> "Password1$")
    # silently destroys that scenario.
    return next((c for c in candidates if c not in used_values), candidates[-1])


@activity.defn(name="ScenarioGenerationActivity")
async def scenario_generation_activity(input: ScenarioGenerationActivityInput) -> list[str]:
    with Session(engine) as session:
        journey = session.exec(
            select(Journey).where(Journey.external_id == uuid.UUID(input.journey_id))
        ).one()

        existing = session.exec(
            select(Scenario).where(
                Scenario.journey_id == journey.id,
                Scenario.generation_run_id == journey.attempt,
            )
        ).all()
        if existing:
            return [str(s.external_id) for s in existing]

        steps = list(
            session.exec(
                select(JourneyStep)
                .where(JourneyStep.journey_id == journey.id)
                .order_by(JourneyStep.step_order)  # type: ignore[arg-type]
            ).all()
        )

        # Every real JourneyStep today only ever sets page_id (Story 2.6's
        # InferenceActivity) — resolve generically anyway, same reasoning as
        # the Story 3.1 read endpoint: the schema allows all four target
        # types via its CHECK constraint.
        component_ids = {s.component_id for s in steps if s.component_id}
        components_by_id = {
            c.id: c
            for c in (
                session.exec(
                    select(Component).where(Component.id.in_(component_ids))  # type: ignore[attr-defined]
                ).all()
                if component_ids
                else []
            )
        }
        page_ids = {s.page_id for s in steps if s.page_id} | {
            c.page_id for c in components_by_id.values()
        }
        pages_by_id = {
            p.id: p
            for p in (
                session.exec(select(Page).where(Page.id.in_(page_ids))).all()  # type: ignore[attr-defined]
                if page_ids
                else []
            )
        }
        forms = list(
            session.exec(select(Form).where(Form.page_id.in_(page_ids))).all()  # type: ignore[attr-defined]
        ) if page_ids else []
        api_endpoints = list(
            session.exec(
                select(ApiEndpoint).where(ApiEndpoint.page_id.in_(page_ids))  # type: ignore[attr-defined]
            ).all()
        ) if page_ids else []
        forms_by_page: dict[uuid.UUID, list[Form]] = {}
        for form in forms:
            forms_by_page.setdefault(form.page_id, []).append(form)
        api_by_page: dict[uuid.UUID, list[ApiEndpoint]] = {}
        for endpoint in api_endpoints:
            api_by_page.setdefault(endpoint.page_id, []).append(endpoint)

        ordered_pages: list[Page] = []
        for step in steps:
            page = pages_by_id.get(step.page_id) if step.page_id else None
            if page is None and step.component_id:
                component = components_by_id.get(step.component_id)
                page = pages_by_id.get(component.page_id) if component else None
            if page is None:
                continue
            # Transient attributes, same technique InferenceActivity uses —
            # SQLModel/Pydantic rejects direct attribute assignment for
            # undeclared fields.
            object.__setattr__(page, "forms", forms_by_page.get(page.id, []))
            object.__setattr__(page, "api_endpoints", api_by_page.get(page.id, []))
            object.__setattr__(page, "stage_label", step.stage_label)
            ordered_pages.append(page)

        settings = session.exec(select(DiscoverySettings)).one()
        candidates = await HostedAIProvider().generate_scenarios(
            journey, ordered_pages, limit=settings.max_scenarios_per_journey
        )

        scenario_external_ids: list[str] = []
        for candidate in candidates:
            scenario = Scenario(
                journey_id=journey.id,
                type=candidate.type,
                name=candidate.name,
                steps=candidate.steps,
                expected_result=candidate.expected_result,
                test_data=[
                    {"name": f.name, "mandatory": f.mandatory, "value": None}
                    for f in candidate.test_data
                ],
                generation_run_id=journey.attempt,
                current=True,
            )
            session.add(scenario)
            session.flush()
            scenario_external_ids.append(str(scenario.external_id))

        session.commit()
        return scenario_external_ids


@activity.defn(name="EnsureTestSuiteActivity")
async def ensure_test_suite_activity(
    input: EnsureTestSuiteActivityInput,
) -> EnsureTestSuiteActivityResult:
    """Idempotent insert-or-fetch of this Journey's current `TestSuite`, run
    once per `SuiteGenerationWorkflow` execution (before the per-Scenario
    fan-out) — so N concurrent `PlaywrightGenerationActivity` calls for the
    same Journey never race to create duplicate `TestSuite` rows. Also
    supersedes the prior attempt's `TestSuite`/`TestAsset` rows atomically
    with the new `TestSuite`'s creation, if `Journey.attempt` is ever bumped
    (no feature does this today — Story 4.3/FR-18 is cut in full, see
    sprint-change-proposal-2026-07-27.md).

    `[FIXED 2026-07-23]` The actual DB work runs in a thread
    (`asyncio.to_thread`) — a real Application's Generate Suite submission
    fans out one `SuiteGenerationWorkflow` per candidate Journey (a dozen or
    more isn't unusual) and each of those fans out one
    `PlaywrightGenerationActivity` per Scenario, so this worker process can
    have dozens of these Activities in flight at once, all sharing one
    event loop. A synchronous, blocking `Session`/`session.commit()` call
    made directly inside an `async def` (the original version of this
    function) freezes that *entire* event loop for its duration — with
    enough concurrent Activities doing this at once, observed live: every
    `TestSuite` got created (this function alone), but the fan-out froze
    solid before a single `TestAsset` was ever written, no crash, no
    timeout, just a silent stall. Exactly the same class of bug
    `discovery_worker`'s `_CaptureSink.add()` already fixed once for this
    codebase's other worker — reused here, not reinvented."""
    return await asyncio.to_thread(_ensure_test_suite_sync, input)


def _ensure_test_suite_sync(input: EnsureTestSuiteActivityInput) -> EnsureTestSuiteActivityResult:
    with Session(engine) as session:
        journey = session.exec(
            select(Journey).where(Journey.external_id == uuid.UUID(input.journey_id))
        ).one()

        existing = session.exec(
            select(TestSuite).where(
                TestSuite.journey_id == journey.id,
                TestSuite.generation_run_id == journey.attempt,
            )
        ).first()
        if existing is not None:
            test_suite = existing
        else:
            test_suite = TestSuite(
                journey_id=journey.id,
                name=f"{journey.name} Test Suite",
                generation_run_id=journey.attempt,
                current=True,
            )
            session.add(test_suite)
            try:
                session.flush()
            except IntegrityError:
                # Lost the race to a concurrent PlaywrightGenerationActivity
                # call for the same Journey/attempt — the unique constraint
                # (not just this select) is what actually prevents the
                # duplicate. Use the row the other call created.
                session.rollback()
                test_suite = session.exec(
                    select(TestSuite).where(
                        TestSuite.journey_id == journey.id,
                        TestSuite.generation_run_id == journey.attempt,
                    )
                ).one()
            else:
                # Atomic with the new TestSuite's creation: supersede the
                # immediately-prior current=true TestSuite (and its
                # TestAssets) for this Journey, in the same commit.
                prior = session.exec(
                    select(TestSuite).where(
                        TestSuite.journey_id == journey.id,
                        TestSuite.id != test_suite.id,
                        TestSuite.current.is_(True),  # type: ignore[attr-defined]
                    )
                ).first()
                if prior is not None:
                    prior.current = False
                    session.add(prior)
                    prior_assets = session.exec(
                        select(TestAsset).where(
                            TestAsset.test_suite_id == prior.id,
                            TestAsset.current.is_(True),  # type: ignore[attr-defined]
                        )
                    ).all()
                    for asset in prior_assets:
                        asset.current = False
                        session.add(asset)
                session.commit()
                session.refresh(test_suite)

        scenarios = session.exec(
            select(Scenario).where(
                Scenario.journey_id == journey.id,
                Scenario.current.is_(True),  # type: ignore[attr-defined]
            )
        ).all()

        return EnsureTestSuiteActivityResult(
            test_suite_id=str(test_suite.external_id),
            scenario_ids=[str(s.external_id) for s in scenarios],
        )


@activity.defn(name="PlaywrightGenerationActivity")
async def playwright_generation_activity(input: PlaywrightGenerationActivityInput) -> str:
    """Converts one Scenario into one TestAsset. Idempotent under Temporal's
    at-least-once retry (AD-9): skips generating — and skips the AI call —
    if a `current=true` TestAsset already exists for this `scenario_id`.

    `[FIXED 2026-07-23]` Every DB step runs in a thread (`asyncio.to_thread`)
    and no DB session is held open across the `await` of the AI call — see
    `ensure_test_suite_activity`'s matching note for why: dozens of these
    can be in flight at once sharing one event loop, and a real AI call can
    take many seconds, so holding a session (and its checked-out connection)
    open for that whole span, on top of blocking the loop synchronously,
    compounds into the exact silent stall observed live (every `TestSuite`
    created, zero `TestAsset`s ever written)."""
    existing_id = await asyncio.to_thread(_existing_test_asset_id_sync, input.scenario_id)
    if existing_id is not None:
        return existing_id

    if await asyncio.to_thread(_test_case_limit_reached_sync, input.scenario_id):
        logger.warning(
            "PlaywrightGenerationActivity: max_test_cases_per_application reached — "
            "skipping scenario_id=%s",
            input.scenario_id,
        )
        return ""

    # Default test-data values, part of this same single flow (Story 4.2
    # AC 1) — never a second trigger. Reviewer-provided values always take
    # precedence; a still-blank field (mandatory or optional) gets a
    # field-name-pattern default, persisted back onto Scenario.test_data
    # before the AI call reads it.
    scenario, known_pages, known_locators = await asyncio.to_thread(
        _resolve_scenario_defaults_sync, input.scenario_id
    )

    code = await HostedAIProvider().generate_playwright(scenario, known_pages, known_locators)

    # Checklist rule 3: a spec isn't "generated successfully" until it
    # compiles against real @playwright/test types — this catches
    # undefined-variable/hallucinated-matcher bugs at generation time
    # instead of at real-test-run time. Raising (rather than persisting
    # anyway) lets Temporal's activity retry re-run generation.
    typecheck_errors = await typecheck_playwright_code(code.code)
    if typecheck_errors:
        raise ValueError(
            "Generated Playwright spec failed typecheck:\n" + "\n".join(typecheck_errors)
        )

    return await asyncio.to_thread(
        _persist_test_asset_sync, input.scenario_id, input.test_suite_id, code.code
    )


def _existing_test_asset_id_sync(scenario_external_id: str) -> str | None:
    with Session(engine) as session:
        scenario = session.exec(
            select(Scenario).where(Scenario.external_id == uuid.UUID(scenario_external_id))
        ).one()
        existing = session.exec(
            select(TestAsset).where(
                TestAsset.scenario_id == scenario.id,
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).first()
        return str(existing.external_id) if existing is not None else None


def _test_case_limit_reached_sync(scenario_external_id: str) -> bool:
    with Session(engine) as session:
        settings = session.exec(select(DiscoverySettings)).one()
        if settings.max_test_cases_per_application is None:
            return False

        scenario = session.exec(
            select(Scenario).where(Scenario.external_id == uuid.UUID(scenario_external_id))
        ).one()
        journey = session.get(Journey, scenario.journey_id)
        assert journey is not None

        current_count = session.exec(
            select(func.count())
            .select_from(TestAsset)
            .join(Scenario, Scenario.id == TestAsset.scenario_id)  # type: ignore[arg-type]
            .join(Journey, Journey.id == Scenario.journey_id)  # type: ignore[arg-type]
            .where(
                Journey.application_id == journey.application_id,
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).one()
        return current_count >= settings.max_test_cases_per_application


def _resolve_known_application_model_sync(
    session: Session, journey_id: uuid.UUID
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Grounds Playwright generation in what Discovery actually captured for
    this Journey, mirroring `scenario_generation_activity`'s own
    steps->components->pages resolution above (duplicated rather than
    shared — that function serves a different Activity and touching it for
    marginal reuse isn't worth the regression risk here).

    Returns `(known_pages, known_locators)`, both plain dicts (never ORM
    objects, so the result stays valid once this function's caller's session
    closes):
    - `known_pages`: one entry per distinct Page actually visited by this
      Journey's steps, in step order, `{"stage_label", "url"}` — a page
      revisited by a later step keeps its first stage_label.
    - `known_locators`: every Component on those same Pages (not just
      step-referenced ones — a real JourneyStep today only ever sets
      `page_id`, never `component_id`, so restricting to step-referenced
      Components would starve this of almost everything) that has at least
      one `ComponentLocator`, picking its `kind="preferred"` row if one
      exists, else the `kind="fallback"` row with the lowest `priority`
      (`discovery_worker/model_builder.py` assigns `priority` in
      already-durability-ranked order, so the lowest-priority fallback is
      always the most durable survivor)."""
    steps = list(
        session.exec(
            select(JourneyStep)
            .where(JourneyStep.journey_id == journey_id)
            .order_by(JourneyStep.step_order)  # type: ignore[arg-type]
        ).all()
    )
    if not steps:
        return [], []

    component_ids = {s.component_id for s in steps if s.component_id}
    components_by_id = {
        c.id: c
        for c in (
            session.exec(
                select(Component).where(Component.id.in_(component_ids))  # type: ignore[attr-defined]
            ).all()
            if component_ids
            else []
        )
    }
    page_ids = {s.page_id for s in steps if s.page_id} | {
        c.page_id for c in components_by_id.values()
    }
    if not page_ids:
        return [], []

    pages_by_id = {
        p.id: p
        for p in session.exec(select(Page).where(Page.id.in_(page_ids))).all()  # type: ignore[attr-defined]
    }

    known_pages: list[dict[str, str]] = []
    stage_label_by_page_id: dict[uuid.UUID, str] = {}
    for step in steps:
        step_page_id = step.page_id
        if step_page_id is None and step.component_id:
            component = components_by_id.get(step.component_id)
            step_page_id = component.page_id if component else None
        if step_page_id is None or step_page_id not in pages_by_id:
            continue
        if step_page_id not in stage_label_by_page_id:
            stage_label_by_page_id[step_page_id] = step.stage_label
            known_pages.append(
                {"stage_label": step.stage_label, "url": pages_by_id[step_page_id].url}
            )

    all_components = list(
        session.exec(
            select(Component)
            .where(Component.page_id.in_(page_ids))  # type: ignore[attr-defined]
            .order_by(Component.name)  # deterministic prompt/test ordering
        ).all()
    )
    if not all_components:
        return known_pages, []

    locators = list(
        session.exec(
            select(ComponentLocator).where(
                ComponentLocator.component_id.in_(  # type: ignore[attr-defined]
                    [c.id for c in all_components]
                )
            )
        ).all()
    )
    locators_by_component: dict[uuid.UUID, list[ComponentLocator]] = {}
    for locator in locators:
        locators_by_component.setdefault(locator.component_id, []).append(locator)

    known_locators: list[dict[str, str]] = []
    for component in all_components:
        candidates = locators_by_component.get(component.id, [])
        preferred = next((loc for loc in candidates if loc.kind == "preferred"), None)
        fallbacks = [loc for loc in candidates if loc.kind == "fallback"]
        chosen = preferred or (min(fallbacks, key=lambda loc: loc.priority) if fallbacks else None)
        if chosen is None:
            continue
        known_locators.append(
            {
                "stage_label": stage_label_by_page_id.get(component.page_id, ""),
                "component_type": component.type,
                "component_name": component.name,
                "selector": chosen.value,
                "strategy": chosen.strategy,
            }
        )
    return known_pages, known_locators


def _resolve_scenario_defaults_sync(
    scenario_external_id: str,
) -> tuple[Scenario, list[dict[str, str]], list[dict[str, str]]]:
    with Session(engine) as session:
        scenario = session.exec(
            select(Scenario).where(Scenario.external_id == uuid.UUID(scenario_external_id))
        ).one()

        updated_fields = [dict(field) for field in scenario.test_data]
        changed = False
        used_values = {field["value"] for field in updated_fields if field.get("value")}
        for field in updated_fields:
            if not field.get("value"):
                value = _default_test_data_value(field["name"], used_values)
                field["value"] = value
                used_values.add(value)
                changed = True
        if changed:
            scenario.test_data = updated_fields
            session.add(scenario)
            session.commit()
            session.refresh(scenario)

        known_pages, known_locators = _resolve_known_application_model_sync(
            session, scenario.journey_id
        )

        # Detach so the caller can read its attributes (name/type/steps/
        # test_data/expected_result — everything generate_playwright needs)
        # after this session closes, without triggering a lazy DB reload.
        session.expunge(scenario)
        return scenario, known_pages, known_locators


def _persist_test_asset_sync(scenario_external_id: str, test_suite_external_id: str, code: str) -> str:
    with Session(engine) as session:
        scenario = session.exec(
            select(Scenario).where(Scenario.external_id == uuid.UUID(scenario_external_id))
        ).one()
        test_suite = session.exec(
            select(TestSuite).where(TestSuite.external_id == uuid.UUID(test_suite_external_id))
        ).one()

        test_asset = TestAsset(
            scenario_id=scenario.id,
            test_suite_id=test_suite.id,
            code=code,
            current=True,
        )
        session.add(test_asset)
        session.commit()
        session.refresh(test_asset)
        return str(test_asset.external_id)
