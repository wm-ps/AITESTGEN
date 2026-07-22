"""ScenarioGenerationActivity end-to-end (Story 4.1) — Postgres only, a fake
`AIProvider` injected via monkeypatch (no real LLM/API key needed; that would
only exercise `HostedAIProvider` itself).
"""

import asyncio
import uuid

import generation_worker.activities as activities_module
import pytest
from ai_provider.scenario_candidate import ScenarioCandidate, TestDataFieldCandidate
from domain import Application, DiscoveryRun, Journey, JourneyStep, Organization, Page, Scenario
from generation_worker.db import engine, init_db
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import ScenarioGenerationActivityInput


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)


class _FakeAIProvider:
    def __init__(self, candidates: list[ScenarioCandidate]) -> None:
        self._candidates = candidates

    async def generate_scenarios(
        self, journey: Journey, pages: list[Page]
    ) -> list[ScenarioCandidate]:
        return self._candidates


def _seed_journey() -> Journey:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        application = Application(
            organization_id=org.id,
            name="Scenario Gen Test App",
            url="https://app.example.com",
            environment="test",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.flush()

        discovery_run = DiscoveryRun(application_id=application.id, status="complete")
        session.add(discovery_run)
        session.flush()

        page = Page(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            url="https://app.example.com/checkout",
            title="Checkout",
        )
        session.add(page)
        session.flush()

        journey = Journey(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            name="Checkout",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()

        session.add(
            JourneyStep(
                journey_id=journey.id, page_id=page.id, step_order=1, stage_label="Checkout"
            )
        )
        session.commit()
        session.refresh(journey)
        return journey


def test_scenario_generation_activity_creates_scenarios_with_blank_test_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()

    candidates = [
        ScenarioCandidate(
            name="Guest checkout",
            type="happy",
            steps=["Add item to cart", "Submit payment"],
            expected_result="Order confirmation is shown",
            test_data=[
                TestDataFieldCandidate(name="username", mandatory=True),
                TestDataFieldCandidate(name="promo_code", mandatory=False),
            ],
        ),
        ScenarioCandidate(
            name="Checkout with expired card",
            type="negative",
            steps=["Add item to cart", "Submit expired card"],
            expected_result="A card-declined error is shown",
            test_data=[TestDataFieldCandidate(name="card_number", mandatory=True)],
        ),
    ]
    monkeypatch.setattr(
        activities_module, "HostedAIProvider", lambda: _FakeAIProvider(candidates)
    )

    scenario_external_ids = asyncio.run(
        activities_module.scenario_generation_activity(
            ScenarioGenerationActivityInput(journey_id=str(journey.external_id))
        )
    )

    assert len(scenario_external_ids) == 2

    with Session(engine) as session:
        scenarios = session.exec(
            select(Scenario).where(
                Scenario.external_id.in_([uuid.UUID(i) for i in scenario_external_ids])  # type: ignore[attr-defined]
            )
        ).all()
        assert len(scenarios) == 2
        assert all(s.journey_id == journey.id for s in scenarios)
        assert all(s.generation_run_id == journey.attempt for s in scenarios)
        assert all(s.current is True for s in scenarios)

        happy = next(s for s in scenarios if s.type == "happy")
        assert happy.name == "Guest checkout"
        assert happy.steps == ["Add item to cart", "Submit payment"]
        assert happy.expected_result == "Order confirmation is shown"
        assert happy.test_data == [
            {"name": "username", "mandatory": True, "value": None},
            {"name": "promo_code", "mandatory": False, "value": None},
        ]
        assert happy.test_data_complete() is False

        negative = next(s for s in scenarios if s.type == "negative")
        assert negative.name == "Checkout with expired card"


def test_scenario_generation_activity_is_idempotent_on_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()

    candidates = [
        ScenarioCandidate(
            name="Guest checkout",
            type="happy",
            steps=["Add item to cart"],
            expected_result="Order confirmation is shown",
            test_data=[TestDataFieldCandidate(name="username", mandatory=True)],
        )
    ]
    monkeypatch.setattr(
        activities_module, "HostedAIProvider", lambda: _FakeAIProvider(candidates)
    )

    first_ids = asyncio.run(
        activities_module.scenario_generation_activity(
            ScenarioGenerationActivityInput(journey_id=str(journey.external_id))
        )
    )
    second_ids = asyncio.run(
        activities_module.scenario_generation_activity(
            ScenarioGenerationActivityInput(journey_id=str(journey.external_id))
        )
    )

    assert first_ids == second_ids
    with Session(engine) as session:
        count = len(
            session.exec(select(Scenario).where(Scenario.journey_id == journey.id)).all()
        )
        assert count == 1
