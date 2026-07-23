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
import re
import uuid

from ai_provider.hosted import HostedAIProvider
from domain import (
    ApiEndpoint,
    Component,
    Form,
    Journey,
    JourneyStep,
    Page,
    Scenario,
    TestAsset,
    TestSuite,
)
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

# Non-AI, deterministic default-value generator (Story 4.2) — mirrors
# discovery_worker/crawler.py's `_generic_value` convention: a field's
# reviewer-provided value always wins; a still-blank field gets a sensible
# placeholder matching its own name, never a value the AI invents (Story 4.1
# AC 5's "the AI never fills in `value`" rule extends to this generator too,
# since it's separate, non-AI code).
_EMAIL_FIELD_RE = re.compile(r"user|email|login", re.IGNORECASE)
_PASSWORD_FIELD_RE = re.compile(r"pass(word)?", re.IGNORECASE)
_CARD_FIELD_RE = re.compile(r"card", re.IGNORECASE)


def _default_test_data_value(field_name: str) -> str:
    if _PASSWORD_FIELD_RE.search(field_name):
        return "Password1$"
    if _CARD_FIELD_RE.search(field_name):
        return "4111111111111111"
    if _EMAIL_FIELD_RE.search(field_name):
        return "test@example.com"
    return "Test value"


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

        candidates = await HostedAIProvider().generate_scenarios(journey, ordered_pages)

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
    with the new `TestSuite`'s creation (Story 4.3 AC 2).

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

    # Default test-data values, part of this same single flow (Story 4.2
    # AC 1) — never a second trigger. Reviewer-provided values always take
    # precedence; a still-blank field (mandatory or optional) gets a
    # field-name-pattern default, persisted back onto Scenario.test_data
    # before the AI call reads it.
    scenario = await asyncio.to_thread(_resolve_scenario_defaults_sync, input.scenario_id)

    code = await HostedAIProvider().generate_playwright(scenario)

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


def _resolve_scenario_defaults_sync(scenario_external_id: str) -> Scenario:
    with Session(engine) as session:
        scenario = session.exec(
            select(Scenario).where(Scenario.external_id == uuid.UUID(scenario_external_id))
        ).one()

        updated_fields = [dict(field) for field in scenario.test_data]
        changed = False
        for field in updated_fields:
            if not field.get("value"):
                field["value"] = _default_test_data_value(field["name"])
                changed = True
        if changed:
            scenario.test_data = updated_fields
            session.add(scenario)
            session.commit()
            session.refresh(scenario)
        # Detach so the caller can read its attributes (name/type/steps/
        # test_data/expected_result — everything generate_playwright needs)
        # after this session closes, without triggering a lazy DB reload.
        session.expunge(scenario)
        return scenario


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
