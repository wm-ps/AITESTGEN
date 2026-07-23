"""EnsureTestSuiteActivity + PlaywrightGenerationActivity end-to-end (Story 4.2)
— Postgres only, a fake `AIProvider` injected via monkeypatch (no real
LLM/API key needed; that would only exercise `HostedAIProvider` itself).
"""

import asyncio
import uuid

import generation_worker.activities as activities_module
import pytest
from ai_provider.test_asset_code import TestAssetCode
from domain import (
    Application,
    DiscoveryRun,
    Journey,
    Organization,
    Scenario,
    TestAsset,
    TestSuite,
)
from generation_worker.db import engine, init_db
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import EnsureTestSuiteActivityInput, PlaywrightGenerationActivityInput


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
    def __init__(self, code: str = "def test_x():\n    pass\n") -> None:
        self._code = code
        self.calls: list[str] = []

    async def generate_playwright(self, scenario: Scenario) -> TestAssetCode:
        self.calls.append(str(scenario.external_id))
        return TestAssetCode(code=self._code)


def _seed_journey(name: str = "Checkout") -> Journey:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        application = Application(
            organization_id=org.id,
            name="Playwright Gen Test App",
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

        journey = Journey(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            name=name,
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.commit()
        session.refresh(journey)
        return journey


def _seed_scenario(journey: Journey, test_data: list[dict] | None = None) -> Scenario:
    with Session(engine) as session:
        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name="Guest checkout",
            steps=["Add item to cart", "Submit payment"],
            expected_result="Order confirmation is shown",
            test_data=test_data
            if test_data is not None
            else [{"name": "username", "mandatory": True, "value": None}],
            generation_run_id=journey.attempt,
        )
        session.add(scenario)
        session.commit()
        session.refresh(scenario)
        return scenario


def test_ensure_test_suite_activity_creates_a_suite_named_after_the_journey() -> None:
    init_db()
    journey = _seed_journey(name="Checkout")
    scenario = _seed_scenario(journey)

    result = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )

    assert result.scenario_ids == [str(scenario.external_id)]
    with Session(engine) as session:
        test_suite = session.exec(
            select(TestSuite).where(TestSuite.external_id == uuid.UUID(result.test_suite_id))
        ).one()
        assert test_suite.name == "Checkout Test Suite"
        assert test_suite.journey_id == journey.id
        assert test_suite.generation_run_id == journey.attempt
        assert test_suite.current is True


def test_ensure_test_suite_activity_is_idempotent_on_retry() -> None:
    init_db()
    journey = _seed_journey()
    _seed_scenario(journey)

    first = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    second = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )

    assert first.test_suite_id == second.test_suite_id
    with Session(engine) as session:
        count = len(
            session.exec(select(TestSuite).where(TestSuite.journey_id == journey.id)).all()
        )
        assert count == 1


def test_ensure_test_suite_activity_supersedes_prior_attempt_atomically() -> None:
    init_db()
    journey = _seed_journey()
    _seed_scenario(journey)

    first = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    with Session(engine) as session:
        old_suite = session.exec(
            select(TestSuite).where(TestSuite.external_id == uuid.UUID(first.test_suite_id))
        ).one()
        # A prior attempt's Scenario row is never deleted (soft-superseded,
        # Story 4.3 AC 2) — still current=True here, matching real
        # conditions right before Story 4.3's own ScenarioGenerationActivity
        # flips it False as part of writing the *next* attempt's Scenarios.
        old_scenario = session.exec(select(Scenario).where(Scenario.journey_id == journey.id)).one()
        old_asset = TestAsset(
            scenario_id=old_scenario.id,
            test_suite_id=old_suite.id,
            code="def test_old():\n    pass\n",
            current=True,
        )
        session.add(old_asset)
        session.commit()

        # Simulate Story 4.3 regeneration: Journey.attempt bumps. `journey`
        # is detached (its own seeding session already closed) — re-fetch
        # the live row in this session before mutating it.
        live_journey = session.get(Journey, journey.id)
        assert live_journey is not None
        live_journey.attempt += 1
        session.add(live_journey)
        session.commit()
        journey.attempt = live_journey.attempt

    second = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    assert second.test_suite_id != first.test_suite_id

    with Session(engine) as session:
        old_suite = session.exec(
            select(TestSuite).where(TestSuite.external_id == uuid.UUID(first.test_suite_id))
        ).one()
        assert old_suite.current is False
        old_asset = session.exec(
            select(TestAsset).where(TestAsset.test_suite_id == old_suite.id)
        ).one()
        assert old_asset.current is False

        new_suite = session.exec(
            select(TestSuite).where(TestSuite.external_id == uuid.UUID(second.test_suite_id))
        ).one()
        assert new_suite.current is True
        assert new_suite.generation_run_id == journey.attempt


def test_playwright_generation_activity_creates_a_test_asset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()
    scenario = _seed_scenario(
        journey,
        test_data=[
            {"name": "username", "mandatory": True, "value": "qa-user"},
            {"name": "promo_code", "mandatory": False, "value": None},
        ],
    )
    prep = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    fake_provider = _FakeAIProvider("def test_guest_checkout():\n    pass\n")
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    asset_id = asyncio.run(
        activities_module.playwright_generation_activity(
            PlaywrightGenerationActivityInput(
                scenario_id=str(scenario.external_id), test_suite_id=prep.test_suite_id
            )
        )
    )

    assert fake_provider.calls == [str(scenario.external_id)]
    with Session(engine) as session:
        test_asset = session.exec(
            select(TestAsset).where(TestAsset.external_id == uuid.UUID(asset_id))
        ).one()
        assert test_asset.code == "def test_guest_checkout():\n    pass\n"
        assert test_asset.scenario_id == scenario.id
        assert test_asset.current is True

        refreshed_scenario = session.get(Scenario, scenario.id)
        assert refreshed_scenario is not None
        promo_field = next(f for f in refreshed_scenario.test_data if f["name"] == "promo_code")
        # Blank optional field got a computed default, never touched by the AI.
        assert promo_field["value"] == "Test value"
        username_field = next(
            f for f in refreshed_scenario.test_data if f["name"] == "username"
        )
        # Reviewer-provided value is untouched.
        assert username_field["value"] == "qa-user"


def test_playwright_generation_activity_is_idempotent_and_skips_the_ai_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()
    scenario = _seed_scenario(journey)
    prep = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    fake_provider = _FakeAIProvider()
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    first_id = asyncio.run(
        activities_module.playwright_generation_activity(
            PlaywrightGenerationActivityInput(
                scenario_id=str(scenario.external_id), test_suite_id=prep.test_suite_id
            )
        )
    )
    second_id = asyncio.run(
        activities_module.playwright_generation_activity(
            PlaywrightGenerationActivityInput(
                scenario_id=str(scenario.external_id), test_suite_id=prep.test_suite_id
            )
        )
    )

    assert first_id == second_id
    # The second call never touched the AI provider at all — skipped before
    # the call, not just before the write.
    assert fake_provider.calls == [str(scenario.external_id)]
    with Session(engine) as session:
        count = len(
            session.exec(select(TestAsset).where(TestAsset.scenario_id == scenario.id)).all()
        )
        assert count == 1
