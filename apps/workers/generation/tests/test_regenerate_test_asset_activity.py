"""RegenerateTestAssetActivity (Edit Test Data, Test Suite page) —
Postgres only, a fake AIProvider injected via monkeypatch (no real LLM/API
key needed).
"""

import asyncio
import uuid

import generation_worker.activities as activities_module
import pytest
from ai_provider.test_asset_code import TestAssetCode
from domain import Application, DiscoveryRun, Journey, Organization, Scenario, TestAsset, TestSuite
from generation_worker.db import engine, init_db
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import RegenerateTestAssetActivityInput

_FAKE_CODE = "import { test, expect } from '@playwright/test'\n\ntest('test_x', async ({ page }) => {})\n"


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
    def __init__(self, code: str = _FAKE_CODE) -> None:
        self._code = code
        self.previous_code_calls: list[str | None] = []
        self.changed_test_data_calls: list[list[dict] | None] = []

    async def generate_playwright(
        self,
        scenario: Scenario,
        known_pages: list[dict] | None = None,
        known_locators: list[dict] | None = None,
        *,
        requires_auth: bool = False,
        field_input_types: dict[str, str] | None = None,
        repair: tuple[str, list[str]] | None = None,
        live_action_sequence: list[dict] | None = None,
        previous_code: str | None = None,
        changed_test_data: list[dict] | None = None,
        failure_error_message: str | None = None,
        failure_stack_trace: str | None = None,
        failure_console_output: str | None = None,
        target_url: str | None = None,
        failure_screenshot_png: bytes | None = None,
        live_inspection_locators: list[dict] | None = None,
    ) -> TestAssetCode:
        self.previous_code_calls.append(previous_code)
        self.changed_test_data_calls.append(changed_test_data)
        return TestAssetCode(code=self._code)


def _seed_scenario_with_test_asset(
    test_data: list[dict] | None = None, prior_code: str = _FAKE_CODE
) -> tuple[Scenario, TestAsset]:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        application = Application(
            organization_id=org.id,
            name="Regenerate Test App",
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
            name="Checkout",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()

        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name="Guest checkout",
            steps=["Add item to cart", "Submit payment"],
            expected_result="Order confirmation is shown",
            test_data=test_data
            if test_data is not None
            else [{"name": "promo_code", "mandatory": False, "value": "SAVE10"}],
            generation_run_id=journey.attempt,
        )
        session.add(scenario)
        session.flush()

        test_suite = TestSuite(
            journey_id=journey.id,
            name="Checkout Test Suite",
            generation_run_id=journey.attempt,
            current=True,
        )
        session.add(test_suite)
        session.flush()

        test_asset = TestAsset(
            scenario_id=scenario.id,
            test_suite_id=test_suite.id,
            code=prior_code,
            current=True,
        )
        session.add(test_asset)
        session.commit()
        session.refresh(scenario)
        session.refresh(test_asset)
        return scenario, test_asset


def test_regenerate_test_asset_activity_supersedes_the_current_test_asset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, prior_asset = _seed_scenario_with_test_asset(
        test_data=[{"name": "promo_code", "mandatory": False, "value": "NEWCODE"}]
    )
    fake_provider = _FakeAIProvider(
        "import { test, expect } from '@playwright/test'\n\n"
        "test('test_guest_checkout', async ({ page }) => {})\n"
    )
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    new_asset_id = asyncio.run(
        activities_module.regenerate_test_asset_activity(
            RegenerateTestAssetActivityInput(scenario_id=str(scenario.external_id))
        )
    )

    # The AI call was given the existing code and the changed test_data —
    # never a blind, from-scratch prompt.
    assert fake_provider.previous_code_calls == [prior_asset.code]
    [changed] = fake_provider.changed_test_data_calls
    assert changed is not None
    assert changed[0]["name"] == "promo_code"
    assert changed[0]["value"] == "NEWCODE"

    with Session(engine) as session:
        old_asset = session.get(TestAsset, prior_asset.id)
        assert old_asset is not None
        assert old_asset.current is False

        new_asset = session.exec(
            select(TestAsset).where(TestAsset.external_id == uuid.UUID(new_asset_id))
        ).one()
        assert new_asset.current is True
        assert new_asset.scenario_id == prior_asset.scenario_id
        assert new_asset.test_suite_id == prior_asset.test_suite_id
        assert "test_guest_checkout" in new_asset.code


def test_regenerate_test_asset_activity_leaves_the_current_test_asset_untouched_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed regeneration must never disturb a working test — the prior
    TestAsset stays `current=True` and no new TestAsset is ever inserted."""
    scenario, prior_asset = _seed_scenario_with_test_asset()
    fake_provider = _FakeAIProvider(
        "import { test, expect } from '@playwright/test'\n\n"
        "test('broken', async ({ page }) => {\n"
        "  await expect(page.locator('#x')).toBeSuperVisible();\n"
        "  console.log(undefinedVar);\n"
        "});\n"
    )
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    with pytest.raises(ValueError, match="failed typecheck"):
        asyncio.run(
            activities_module.regenerate_test_asset_activity(
                RegenerateTestAssetActivityInput(scenario_id=str(scenario.external_id))
            )
        )

    with Session(engine) as session:
        assets = session.exec(
            select(TestAsset).where(TestAsset.scenario_id == prior_asset.scenario_id)
        ).all()
        assert len(assets) == 1
        assert assets[0].id == prior_asset.id
        assert assets[0].current is True
        assert assets[0].code == prior_asset.code


def test_supersede_test_asset_aborts_if_the_prior_asset_was_already_superseded() -> None:
    """Concurrency guard — RegenerateTestAssetActivity is a second caller of
    `supersede_test_asset` alongside HealTestActivity, and the two can race
    for the same scenario's current TestAsset. The loser must abort cleanly
    rather than insert a second `current=True` row."""
    _scenario, prior_asset = _seed_scenario_with_test_asset()

    with Session(engine) as session:
        prior = session.get(TestAsset, prior_asset.id)
        assert prior is not None
        activities_module.supersede_test_asset(
            session,
            prior,
            code="// first winner\n",
            requires_auth=False,
            warnings=[],
            status="ready",
            primary_page_id=None,
        )
        session.commit()

        # Simulate a second, concurrent caller that loaded `prior` before the
        # first caller's commit above — it still thinks `current` is True.
        stale_prior = TestAsset(**{**prior.model_dump(), "id": prior.id})
        with pytest.raises(RuntimeError, match="already superseded"):
            activities_module.supersede_test_asset(
                session,
                stale_prior,
                code="// second loser\n",
                requires_auth=False,
                warnings=[],
                status="ready",
                primary_page_id=None,
            )

    with Session(engine) as session:
        current_assets = session.exec(
            select(TestAsset).where(
                TestAsset.scenario_id == prior_asset.scenario_id,
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).all()
        assert len(current_assets) == 1
        assert current_assets[0].code == "// first winner\n"
