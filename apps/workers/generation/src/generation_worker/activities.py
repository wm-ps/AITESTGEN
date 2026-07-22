"""ScenarioGenerationActivity — Story 4.1's first real Activity dispatch.

Fetches a Journey's attributed canonical rows (via its `JourneyStep`s),
attaches the same kind of transient capture context `InferenceActivity`
attaches to Pages before calling the AI provider, and persists the returned
`ScenarioCandidate`s as `Scenario` rows. Idempotent under Temporal's
at-least-once retry (AD-9): if `Scenario` rows already exist for this
Journey's current `(journey_id, generation_run_id)` pair, returns them
without re-generating.
"""

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
)
from sqlmodel import Session, select
from temporalio import activity
from workflows import ScenarioGenerationActivityInput

from generation_worker.db import engine


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
