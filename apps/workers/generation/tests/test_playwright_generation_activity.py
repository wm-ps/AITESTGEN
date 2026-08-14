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
    Component,
    ComponentLocator,
    DiscoveryRun,
    Journey,
    JourneyStep,
    Organization,
    Page,
    Scenario,
    TestAsset,
    TestSuite,
)
from generation_worker.db import engine, init_db
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import EnsureTestSuiteActivityInput, PlaywrightGenerationActivityInput

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
        self.calls: list[str] = []
        self.known_pages_calls: list[list[dict]] = []
        self.known_locators_calls: list[list[dict]] = []

    async def generate_playwright(
        self,
        scenario: Scenario,
        known_pages: list[dict] | None = None,
        known_locators: list[dict] | None = None,
        grounding_feedback: str | None = None,
        *,
        requires_auth: bool = False,
    ) -> TestAssetCode:
        self.calls.append(str(scenario.external_id))
        self.known_pages_calls.append(known_pages or [])
        self.known_locators_calls.append(known_locators or [])
        return TestAssetCode(code=self._code)


class _SequencedAIProvider:
    """Returns a different code string on each successive call, in order —
    the last one repeats for any call beyond the list. Used to simulate a
    first attempt producing a locator-grounding violation and a later
    attempt (in-process retry, or a seeded wave-level `grounding_feedback`)
    correcting it."""

    def __init__(self, codes: list[str]) -> None:
        self._codes = list(codes)
        self.calls: list[dict] = []

    async def generate_playwright(
        self,
        scenario: Scenario,
        known_pages: list[dict] | None = None,
        known_locators: list[dict] | None = None,
        grounding_feedback: str | None = None,
        *,
        requires_auth: bool = False,
    ) -> TestAssetCode:
        self.calls.append({"grounding_feedback": grounding_feedback})
        index = min(len(self.calls) - 1, len(self._codes) - 1)
        return TestAssetCode(code=self._codes[index])


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


def _seed_page(journey: Journey, url: str = "https://app.example.com/checkout") -> Page:
    with Session(engine) as session:
        page = Page(
            application_id=journey.application_id,
            discovery_run_id=journey.discovery_run_id,
            url=url,
            title="Checkout",
        )
        session.add(page)
        session.commit()
        session.refresh(page)
        return page


def _seed_journey_step(
    journey: Journey, page: Page, step_order: int = 1, stage_label: str = "Checkout"
) -> None:
    with Session(engine) as session:
        session.add(
            JourneyStep(
                journey_id=journey.id,
                page_id=page.id,
                step_order=step_order,
                stage_label=stage_label,
            )
        )
        session.commit()


def _seed_component_with_locators(
    page: Page,
    name: str = "Save button",
    type_: str = "button",
    locators: list[dict] | None = None,
) -> Component:
    """`locators=None` (the default) seeds a single preferred locator; pass
    explicit kind/priority/value dicts (an empty list included) to exercise
    the fallback-selection/no-locator logic."""
    if locators is None:
        locators = [
            {
                "kind": "preferred",
                "strategy": "testid",
                "value": '[data-testid="save"]',
                "priority": 0,
            }
        ]
    with Session(engine) as session:
        component = Component(
            application_id=page.application_id,
            page_id=page.id,
            name=name,
            type=type_,
            action="click",
        )
        session.add(component)
        session.flush()
        for loc in locators:
            session.add(ComponentLocator(component_id=component.id, **loc))
        session.commit()
        session.refresh(component)
        return component


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
        # AD-8) — still current=True here, matching real conditions right
        # before a next attempt's ScenarioGenerationActivity flips it False
        # as part of writing the *next* attempt's Scenarios.
        old_scenario = session.exec(select(Scenario).where(Scenario.journey_id == journey.id)).one()
        old_asset = TestAsset(
            scenario_id=old_scenario.id,
            test_suite_id=old_suite.id,
            code=_FAKE_CODE,
            current=True,
        )
        session.add(old_asset)
        session.commit()

        # Simulate a Journey.attempt bump (AD-1/AD-8's versioning scaffold —
        # no feature triggers this today, but EnsureTestSuiteActivity's
        # supersede logic must hold if attempt ever changes). `journey` is
        # detached (its own seeding session already closed) — re-fetch the
        # live row in this session before mutating it.
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


def test_playwright_generation_activity_rejects_code_that_fails_typecheck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checklist rule 3: a hallucinated matcher / undefined variable — real
    failure modes seen this session — must fail the activity, never reach
    `TestAsset`."""
    init_db()
    journey = _seed_journey()
    scenario = _seed_scenario(journey)
    prep = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
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
            activities_module.playwright_generation_activity(
                PlaywrightGenerationActivityInput(
                    scenario_id=str(scenario.external_id), test_suite_id=prep.test_suite_id
                )
            )
        )

    with Session(engine) as session:
        assert session.exec(
            select(TestAsset).where(TestAsset.scenario_id == scenario.id)
        ).first() is None


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
    fake_provider = _FakeAIProvider(
        "import { test, expect } from '@playwright/test'\n\n"
        "test('test_guest_checkout', async ({ page }) => {})\n"
    )
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
        # PlaywrightGenerationActivity deterministically tags the test() call
        # with the requires_auth-derived `@public`/`@auth` tag — no login
        # page was ever seeded for this Application, so no auth is required.
        assert test_asset.code == (
            "import { test, expect } from '@playwright/test'\n\n"
            "test('test_guest_checkout', { tag: '@public' }, async ({ page }) => {})\n"
        )
        assert test_asset.scenario_id == scenario.id
        assert test_asset.current is True
        assert test_asset.requires_auth is False
        assert test_asset.status == "ready"

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


def test_playwright_generation_activity_passes_known_page_to_ai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()
    page = _seed_page(journey, url="https://app.example.com/checkout")
    _seed_journey_step(journey, page, step_order=1, stage_label="Checkout")
    scenario = _seed_scenario(journey)
    prep = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    fake_provider = _FakeAIProvider()
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    asyncio.run(
        activities_module.playwright_generation_activity(
            PlaywrightGenerationActivityInput(
                scenario_id=str(scenario.external_id), test_suite_id=prep.test_suite_id
            )
        )
    )

    assert fake_provider.known_pages_calls == [
        [{"stage_label": "Checkout", "url": "https://app.example.com/checkout"}]
    ]


def test_playwright_generation_activity_dedupes_known_pages_by_page_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()
    page = _seed_page(journey, url="https://app.example.com/checkout")
    _seed_journey_step(journey, page, step_order=1, stage_label="Checkout")
    _seed_journey_step(journey, page, step_order=2, stage_label="Checkout Confirmation")
    scenario = _seed_scenario(journey)
    prep = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    fake_provider = _FakeAIProvider()
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    asyncio.run(
        activities_module.playwright_generation_activity(
            PlaywrightGenerationActivityInput(
                scenario_id=str(scenario.external_id), test_suite_id=prep.test_suite_id
            )
        )
    )

    # Same Page visited by two steps — appears once, keeping the first
    # step's stage_label.
    assert fake_provider.known_pages_calls == [
        [{"stage_label": "Checkout", "url": "https://app.example.com/checkout"}]
    ]


def test_playwright_generation_activity_passes_known_locator_to_ai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()
    page = _seed_page(journey)
    _seed_journey_step(journey, page, stage_label="Checkout")
    _seed_component_with_locators(page, name="Save button", type_="button")
    scenario = _seed_scenario(journey)
    prep = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    fake_provider = _FakeAIProvider()
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    asyncio.run(
        activities_module.playwright_generation_activity(
            PlaywrightGenerationActivityInput(
                scenario_id=str(scenario.external_id), test_suite_id=prep.test_suite_id
            )
        )
    )

    assert fake_provider.known_locators_calls == [
        [
            {
                "stage_label": "Checkout",
                "component_type": "button",
                "component_name": "Save button",
                "selector": '[data-testid="save"]',
                "strategy": "testid",
            }
        ]
    ]


def test_playwright_generation_activity_prefers_preferred_locator_over_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()
    page = _seed_page(journey)
    _seed_journey_step(journey, page)
    _seed_component_with_locators(
        page,
        locators=[
            {"kind": "fallback", "strategy": "css", "value": "#save-btn", "priority": 1},
            {
                "kind": "preferred",
                "strategy": "testid",
                "value": '[data-testid="save"]',
                "priority": 0,
            },
        ],
    )
    scenario = _seed_scenario(journey)
    prep = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    fake_provider = _FakeAIProvider()
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    asyncio.run(
        activities_module.playwright_generation_activity(
            PlaywrightGenerationActivityInput(
                scenario_id=str(scenario.external_id), test_suite_id=prep.test_suite_id
            )
        )
    )

    [locators] = fake_provider.known_locators_calls
    assert locators[0]["selector"] == '[data-testid="save"]'


def test_playwright_generation_activity_falls_back_to_lowest_priority_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()
    page = _seed_page(journey)
    _seed_journey_step(journey, page)
    _seed_component_with_locators(
        page,
        locators=[
            {"kind": "fallback", "strategy": "css", "value": "#save-btn-b", "priority": 2},
            {"kind": "fallback", "strategy": "css", "value": "#save-btn-a", "priority": 1},
        ],
    )
    scenario = _seed_scenario(journey)
    prep = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    fake_provider = _FakeAIProvider()
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    asyncio.run(
        activities_module.playwright_generation_activity(
            PlaywrightGenerationActivityInput(
                scenario_id=str(scenario.external_id), test_suite_id=prep.test_suite_id
            )
        )
    )

    [locators] = fake_provider.known_locators_calls
    assert locators[0]["selector"] == "#save-btn-a"


def test_playwright_generation_activity_skips_component_with_no_locators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()
    page = _seed_page(journey)
    _seed_journey_step(journey, page)
    _seed_component_with_locators(page, name="Save button", locators=[])
    scenario = _seed_scenario(journey)
    prep = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    fake_provider = _FakeAIProvider()
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    asyncio.run(
        activities_module.playwright_generation_activity(
            PlaywrightGenerationActivityInput(
                scenario_id=str(scenario.external_id), test_suite_id=prep.test_suite_id
            )
        )
    )

    assert fake_provider.known_locators_calls == [[]]


def test_playwright_generation_activity_passes_empty_known_data_when_journey_has_no_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()  # no Page/JourneyStep seeded — today's default shape
    scenario = _seed_scenario(journey)
    prep = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    fake_provider = _FakeAIProvider()
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    asyncio.run(
        activities_module.playwright_generation_activity(
            PlaywrightGenerationActivityInput(
                scenario_id=str(scenario.external_id), test_suite_id=prep.test_suite_id
            )
        )
    )

    assert fake_provider.known_pages_calls == [[]]
    assert fake_provider.known_locators_calls == [[]]


# --- locator-grounding hardening: in-process retry + wave-level seeding ---

_GROUNDED_CODE = (
    "import { test, expect } from '@playwright/test'\n\n"
    "test('test_x', async ({ page }) => {\n"
    "  const btn = page.locator('[data-testid=\"save\"]');\n"
    "});\n"
)
_UNGROUNDED_CODE = (
    "import { test, expect } from '@playwright/test'\n\n"
    "test('test_x', async ({ page }) => {\n"
    "  const btn = page.locator('#totally-invented');\n"
    "});\n"
)


def _seed_scenario_with_grounding_data(journey: Journey) -> None:
    """A Component with a real captured locator — needed for `GroundingContext`
    to be non-empty, since an empty context short-circuits to "no violations"
    (a Journey with nothing captured has nothing to ground against)."""
    page = _seed_page(journey)
    _seed_journey_step(journey, page, stage_label="Checkout")
    _seed_component_with_locators(page, name="Save button", type_="button")


def test_playwright_generation_activity_retries_in_process_on_grounding_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()
    _seed_scenario_with_grounding_data(journey)
    scenario = _seed_scenario(journey)
    prep = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    fake_provider = _SequencedAIProvider([_UNGROUNDED_CODE, _GROUNDED_CODE])
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    asset_id = asyncio.run(
        activities_module.playwright_generation_activity(
            PlaywrightGenerationActivityInput(
                scenario_id=str(scenario.external_id), test_suite_id=prep.test_suite_id
            )
        )
    )

    # Two in-process attempts: the first's invented locator was rejected, the
    # second (fed the first's specific violation as feedback) succeeded —
    # never reaches the outer Temporal retry/wave machinery at all.
    assert len(fake_provider.calls) == 2
    assert fake_provider.calls[0]["grounding_feedback"] is None
    assert "#totally-invented" in fake_provider.calls[1]["grounding_feedback"]
    with Session(engine) as session:
        test_asset = session.exec(
            select(TestAsset).where(TestAsset.external_id == uuid.UUID(asset_id))
        ).one()
        # Not exact-equal to `_GROUNDED_CODE` — `_persist_test_asset_sync` runs
        # `spec_linter.apply_auth_tag` on the way in, rewriting the `test(...)`
        # call to carry an `@auth`/`@public` tag regardless of what the AI
        # provider returned. What this test actually cares about is that the
        # grounding retry produced the corrected, real locator rather than the
        # first attempt's invented one.
        assert '[data-testid="save"]' in test_asset.code
        assert "#totally-invented" not in test_asset.code


def test_playwright_generation_activity_raises_grounding_violation_after_exhausting_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()
    _seed_scenario_with_grounding_data(journey)
    scenario = _seed_scenario(journey)
    prep = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    fake_provider = _SequencedAIProvider([_UNGROUNDED_CODE])  # always ungrounded
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    with pytest.raises(ValueError, match="GROUNDING_VIOLATION"):
        asyncio.run(
            activities_module.playwright_generation_activity(
                PlaywrightGenerationActivityInput(
                    scenario_id=str(scenario.external_id), test_suite_id=prep.test_suite_id
                )
            )
        )

    # 3 total attempts (1 initial + 2 in-process corrective retries), then
    # gives up rather than looping forever.
    assert len(fake_provider.calls) == 3
    with Session(engine) as session:
        assert (
            session.exec(select(TestAsset).where(TestAsset.scenario_id == scenario.id)).first()
            is None
        )


def test_playwright_generation_activity_seeds_first_attempt_with_wave_level_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `grounding_feedback` already present on the input (threaded in by
    `SuiteGenerationWorkflow` from a prior wave's rejected attempt) must reach
    the very first `generate_playwright` call of this Activity attempt, not
    just in-process retries after it."""
    init_db()
    journey = _seed_journey()
    _seed_scenario_with_grounding_data(journey)
    scenario = _seed_scenario(journey)
    prep = asyncio.run(
        activities_module.ensure_test_suite_activity(
            EnsureTestSuiteActivityInput(journey_id=str(journey.external_id))
        )
    )
    fake_provider = _SequencedAIProvider([_GROUNDED_CODE])
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: fake_provider)

    asyncio.run(
        activities_module.playwright_generation_activity(
            PlaywrightGenerationActivityInput(
                scenario_id=str(scenario.external_id),
                test_suite_id=prep.test_suite_id,
                grounding_feedback="prior wave: #invented-earlier did not resolve",
            )
        )
    )

    assert len(fake_provider.calls) == 1
    assert fake_provider.calls[0]["grounding_feedback"] == (
        "prior wave: #invented-earlier did not resolve"
    )
