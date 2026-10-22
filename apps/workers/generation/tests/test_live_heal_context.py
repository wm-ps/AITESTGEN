"""_load_heal_context_sync / live_heal_activity — Postgres only.

`[FIXED]` regression: `LiveHealActivity` used to pass `test_asset.scenario_id`
(the internal PK) straight into `_resolve_scenario_defaults_sync`, which
looks a Scenario up by its *external* id — every live heal attempt crashed
with `NoResultFound` before ever reaching the AI/browser. What's covered:
`_load_heal_context_sync` returns the Scenario's real `external_id`, and
that value is exactly what `_resolve_scenario_defaults_sync` needs to
resolve the same Scenario back.
"""

import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import generation_worker.live_exploration_activities as live_module
import pytest
from domain import (
    Application,
    DiscoveryRun,
    Journey,
    Organization,
    Scenario,
    TestAsset,
    TestResult,
    TestRun,
    TestSuite,
)
from generation_worker.activities import _resolve_scenario_defaults_sync
from generation_worker.db import engine, init_db
from generation_worker.live_exploration_activities import (
    _load_heal_context_sync,
    _supersede_heal_result_sync,
)
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from playwright_typecheck.assertions import _TYPESCRIPT_DIR
from sqlmodel import Session, select
from workflows import AUTO_HEAL_ATTEMPT_CAP, LiveHealActivityInput


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


def _seed_test_result(
    *, error_message: str = "locator not found", code: str = "// spec\n"
) -> TestResult:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Live Heal Context Test App",
            url="https://app.example.com",
            environment="staging",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.flush()
        discovery_run = DiscoveryRun(
            application_id=application.id, status="complete", source="live_exploration"
        )
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
            name="Completes checkout",
            steps=["Add item to cart"],
            generation_run_id=journey.attempt,
            safety_classification="SAFE",
        )
        session.add(scenario)
        session.flush()
        test_suite = TestSuite(
            journey_id=journey.id, name="Checkout Test Suite", generation_run_id=journey.attempt
        )
        session.add(test_suite)
        session.flush()
        test_asset = TestAsset(
            scenario_id=scenario.id, test_suite_id=test_suite.id, code=code
        )
        session.add(test_asset)
        session.flush()
        test_run = TestRun(
            application_id=application.id,
            run_number=1,
            status="completed",
            environment_snapshot=application.environment,
            target_base_url_snapshot=application.url,
        )
        session.add(test_run)
        session.flush()
        test_result = TestResult(
            test_run_id=test_run.id,
            test_asset_id=test_asset.id,
            scenario_id=scenario.id,
            status="failed",
            error_message=error_message,
        )
        session.add(test_result)
        session.commit()
        session.refresh(test_result)
        return test_result


def test_load_heal_context_returns_the_scenario_external_id_not_the_internal_one() -> None:
    init_db()
    test_result = _seed_test_result()

    context = _load_heal_context_sync(str(test_result.external_id))

    assert context is not None
    _application, _test_result, test_asset, max_heal_attempts, scenario_external_id = context
    assert scenario_external_id != str(test_asset.scenario_id)
    # `[FIXED]` regression: this used to read `DiscoverySettings.max_heal_attempts`
    # — the *manual* "Retry with self-healing" budget — for what is really
    # the automatic path; it must use the fixed AUTO_HEAL_ATTEMPT_CAP instead.
    assert max_heal_attempts == AUTO_HEAL_ATTEMPT_CAP

    # The real regression: this must not raise NoResultFound.
    scenario, *_rest = _resolve_scenario_defaults_sync(scenario_external_id)
    assert str(scenario.id) == str(test_asset.scenario_id)


def test_supersede_heal_result_increments_auto_heal_attempt_count() -> None:
    """`[FIXED]` regression: `TestResult.heal_attempt_count` was split into
    `auto_heal_attempt_count`/`manual_heal_attempt_count` — this still wrote
    the old, now-nonexistent name, crashing every real live-heal attempt
    with `AttributeError: 'TestResult' object has no attribute
    'heal_attempt_count'` (surfaced to the user as "Something went wrong
    during live exploration")."""
    init_db()
    test_result = _seed_test_result()

    new_asset_external_id = _supersede_heal_result_sync(
        test_result.test_asset_id,
        test_result.id,
        code="// healed spec\n",
        requires_auth=False,
        warnings=["Healed via live re-exploration."],
        primary_page_id=None,
    )

    with Session(engine) as session:
        refreshed = session.exec(
            select(TestResult).where(TestResult.id == test_result.id)
        ).one()
        assert refreshed.auto_heal_attempt_count == 1
        assert refreshed.manual_heal_attempt_count == 0
        assert refreshed.healed_test_asset_id is not None

        new_asset = session.exec(
            select(TestAsset).where(TestAsset.external_id == uuid.UUID(new_asset_external_id))
        ).one()
        assert new_asset.code == "// healed spec\n"


# --- live_heal_activity: heal broken action locators, never assertions ------

ORIGINAL_SPEC = """import { test, expect } from '@playwright/test';

test('completes checkout', async ({ page }) => {
  await page.getByRole('button', { name: 'Add to cart' }).click();
  await expect(page.getByText('1 item in cart')).toBeVisible();
});
"""
LOCATOR_ONLY_FIX = ORIGINAL_SPEC.replace(
    "page.getByRole('button', { name: 'Add to cart' })", "page.getByTestId('add-to-cart')"
)
ASSERTION_CHANGING_FIX = LOCATOR_ONLY_FIX.replace("'1 item in cart'", "'Cart'")
ACTION_LOCATOR_FAILURE = (
    "TimeoutError: locator.click: Timeout 15000ms exceeded.\n"
    "Call log:\n  - waiting for getByRole('button', { name: 'Add to cart' })"
)
ASSERTION_ELEMENT_NOT_FOUND = (
    "Error: expect(locator).toBeVisible() failed\n\n"
    "Locator: getByText('1 item in cart')\nExpected: visible\nError: element(s) not found\n\n"
    "Call log:\n  - Expect \"toBeVisible\" getByText('1 item in cart') with timeout 15000ms\n"
    "  - waiting for getByText('1 item in cart')\n"
)

needs_typescript = pytest.mark.skipif(
    not os.path.exists(_TYPESCRIPT_DIR),
    reason="run `npm install` in packages/playwright_typecheck/typecheck",
)


class _FakeMCPClient:
    def __init__(self, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "_FakeMCPClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


def _mock_live_heal_io(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ai_code: str) -> dict:
    storage_state = tmp_path / "storage.json"
    storage_state.write_text("{}", encoding="utf-8")
    calls = {
        "bootstrap": AsyncMock(return_value=storage_state),
        "explore": AsyncMock(
            return_value=SimpleNamespace(
                goal_satisfied=True,
                steps=[
                    SimpleNamespace(
                        tool_name="browser_click",
                        tool_args={"element": "Add to cart button"},
                        semantic_target="Add to cart",
                        locator_candidate={"strategy": "testid", "value": "add-to-cart"},
                    )
                ],
            )
        ),
        "ai": AsyncMock(return_value=SimpleNamespace(code=ai_code)),
    }
    monkeypatch.setattr(live_module, "bootstrap_storage_state", calls["bootstrap"])
    monkeypatch.setattr(live_module, "PlaywrightMCPClient", _FakeMCPClient)
    monkeypatch.setattr(live_module, "run_exploration", calls["explore"])
    monkeypatch.setattr(
        live_module, "HostedAIProvider", lambda: SimpleNamespace(generate_playwright=calls["ai"])
    )
    monkeypatch.setattr(live_module, "typecheck_playwright_code", AsyncMock(return_value=[]))
    return calls


def _heal_input(test_result: TestResult) -> LiveHealActivityInput:
    with Session(engine) as session:
        test_run = session.get(TestRun, test_result.test_run_id)
        return LiveHealActivityInput(
            application_id=str(test_run.application_id),
            test_run_id=str(test_run.external_id),
            test_result_id=str(test_result.external_id),
        )


def _current_code(test_result: TestResult) -> str:
    with Session(engine) as session:
        asset = session.get(TestAsset, test_result.test_asset_id)
        return session.exec(
            select(TestAsset).where(
                TestAsset.scenario_id == asset.scenario_id,
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).one().code


@pytest.mark.asyncio
async def test_eligibility_live_heal_never_heals_a_missing_element_inside_an_assertion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    init_db()
    test_result = _seed_test_result(error_message=ASSERTION_ELEMENT_NOT_FOUND, code=ORIGINAL_SPEC)
    calls = _mock_live_heal_io(monkeypatch, tmp_path, LOCATOR_ONLY_FIX)

    result = await live_module.live_heal_activity(_heal_input(test_result))

    assert result.healed is False
    # No browser, no exploration, no AI call.
    calls["bootstrap"].assert_not_awaited()
    calls["explore"].assert_not_awaited()
    calls["ai"].assert_not_awaited()
    assert _current_code(test_result) == ORIGINAL_SPEC


@needs_typescript
@pytest.mark.asyncio
async def test_guard_live_heal_rejects_a_fix_that_changes_an_assertion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    init_db()
    test_result = _seed_test_result(error_message=ACTION_LOCATOR_FAILURE, code=ORIGINAL_SPEC)
    calls = _mock_live_heal_io(monkeypatch, tmp_path, ASSERTION_CHANGING_FIX)

    result = await live_module.live_heal_activity(_heal_input(test_result))

    calls["ai"].assert_awaited_once()
    assert result.healed is False
    assert _current_code(test_result) == ORIGINAL_SPEC
    with Session(engine) as session:
        refreshed = session.exec(select(TestResult).where(TestResult.id == test_result.id)).one()
        assert refreshed.healed_test_asset_id is None


@needs_typescript
@pytest.mark.asyncio
async def test_guard_live_heal_accepts_a_locator_only_fix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    init_db()
    test_result = _seed_test_result(error_message=ACTION_LOCATOR_FAILURE, code=ORIGINAL_SPEC)
    _mock_live_heal_io(monkeypatch, tmp_path, LOCATOR_ONLY_FIX)

    result = await live_module.live_heal_activity(_heal_input(test_result))

    assert result.healed is True
    assert "getByTestId('add-to-cart')" in _current_code(test_result)
