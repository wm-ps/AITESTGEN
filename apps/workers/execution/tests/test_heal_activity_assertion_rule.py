"""`heal_test_activity` under the self-healing rule: a failure raised inside
an `expect(...)` assertion is never healed, every other failure heals
exactly as before, and no heal may change an assertion.

DB-real, external-I/O-mocked (same convention as
`test_heal_activity_live_inspection.py`): the AI, Playwright reruns, typecheck
and live inspection are mocked, but the assertion guard runs for real
(node + TypeScript, `packages/playwright_typecheck/typecheck/assertions.js`).
"""

import os
import uuid
from unittest.mock import AsyncMock

import execution_worker.activities as activities_module
import pytest
from domain import (
    Application,
    DiscoveryRun,
    DiscoverySettings,
    Journey,
    Organization,
    Scenario,
    TestAsset,
    TestResult,
    TestRun,
    TestSuite,
)
from execution_worker.db import engine, init_db
from execution_worker.live_inspection import LiveInspectionResult
from playwright_typecheck.assertions import _TYPESCRIPT_DIR
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import HEAL_ASSERTION_GUARD_ERROR_PREFIX


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            from sqlalchemy import text

            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError, OSError:
        return False


pytestmark = [
    pytest.mark.skipif(
        not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
    ),
    pytest.mark.skipif(
        not os.path.exists(_TYPESCRIPT_DIR),
        reason="run `npm install` in packages/playwright_typecheck/typecheck",
    ),
]

ORIGINAL_SPEC = """import { test, expect } from '@playwright/test';

test('submit a claim', async ({ page }) => {
  await page.goto('https://app.example.com/claims');
  await page.getByRole('button', { name: 'Submit' }).click();
  await expect(page.getByText('Claim submitted')).toBeVisible();
});
"""
# Fixes the broken action locator only — the assertion is untouched.
LOCATOR_ONLY_FIX = ORIGINAL_SPEC.replace(
    "page.getByRole('button', { name: 'Submit' }).click()",
    "page.getByTestId('submit-claim').click()",
)
# Also "fixes" the assertion — must be rejected.
ASSERTION_CHANGING_FIX = LOCATOR_ONLY_FIX.replace(
    "page.getByText('Claim submitted')", "page.getByText('Submitted')"
)

ACTION_LOCATOR_FAILURE = (
    "TimeoutError: locator.click: Timeout 15000ms exceeded.\n"
    "Call log:\n  - waiting for getByRole('button', { name: 'Submit' })"
)
ASSERTION_ELEMENT_NOT_FOUND = {
    "toBeVisible": (
        "Error: expect(locator).toBeVisible() failed\n\n"
        "Locator: getByText('Claim submitted')\nExpected: visible\nTimeout: 15000ms\n"
        "Error: element(s) not found\n\n"
        "Call log:\n"
        "  - Expect \"toBeVisible\" getByText('Claim submitted') with timeout 15000ms\n"
        "  - waiting for getByText('Claim submitted')\n"
    ),
    "toHaveText": (
        "Error: expect(locator).toHaveText(expected) failed\n\n"
        "Locator: getByTestId('claim-status')\nExpected string: \"Submitted\"\n"
        "Error: element(s) not found\n\n"
        "Call log:\n"
        "  - Expect \"toHaveText\" getByTestId('claim-status') with timeout 15000ms\n"
        "  - waiting for getByTestId('claim-status')\n"
    ),
    "toHaveCount": (
        "Error: expect(locator).toHaveCount(expected) failed\n\n"
        "Locator: getByRole('row')\nExpected: 20\nReceived: 0\n\n"
        "Call log:\n  - Expect \"toHaveCount\" getByRole('row') with timeout 30000ms\n"
    ),
}


def _seed(error_message: str) -> tuple[Application, TestAsset, TestResult, TestRun]:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Assertion Rule Test App",
            url="https://app.example.com",
            environment="staging",
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
            name="Claims",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()
        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name="Submits a claim",
            steps=["Open claims", "Click submit"],
            generation_run_id=journey.attempt,
            safety_classification="SAFE",
        )
        session.add(scenario)
        session.flush()
        test_suite = TestSuite(
            journey_id=journey.id, name="Claims Test Suite", generation_run_id=journey.attempt
        )
        session.add(test_suite)
        session.flush()
        test_asset = TestAsset(
            scenario_id=scenario.id, test_suite_id=test_suite.id, code=ORIGINAL_SPEC
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
            scenario_id=test_asset.scenario_id,
            status="failed",
            error_message=error_message,
        )
        session.add(test_result)
        session.commit()
        for row in (application, test_asset, test_result, test_run):
            session.refresh(row)
        return application, test_asset, test_result, test_run


def _set_max_heal_attempts(value: int) -> None:
    with Session(engine) as session:
        settings = session.exec(select(DiscoverySettings)).one()
        settings.max_heal_attempts = value
        session.add(settings)
        session.commit()


class _ScriptedAIProvider:
    """Returns the queued candidates in order and records every call."""

    responses: list[str] = []
    calls: list[dict] = []

    async def generate_playwright(self, *args: object, **kwargs: object) -> object:
        from ai_provider.test_asset_code import TestAssetCode

        _ScriptedAIProvider.calls.append(kwargs)
        return TestAssetCode(code=_ScriptedAIProvider.responses.pop(0))


@pytest.fixture(autouse=True)
def _mock_external_io(monkeypatch: pytest.MonkeyPatch, tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(activities_module, "project_dir_for", lambda test_run_id: tmp_path)
    monkeypatch.setattr(activities_module, "_build_subprocess_env", lambda application: {})
    _ScriptedAIProvider.responses = []
    _ScriptedAIProvider.calls = []
    monkeypatch.setattr(activities_module, "HostedAIProvider", _ScriptedAIProvider)
    monkeypatch.setattr(activities_module, "typecheck_playwright_code", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        activities_module,
        "run_live_inspection",
        AsyncMock(
            return_value=LiveInspectionResult(
                url="https://app.example.com", locator_candidates=[], page_title=None
            )
        ),
    )
    init_db()
    _set_max_heal_attempts(3)
    return tmp_path


def _heal_input(application, test_run, test_result, *, manual: bool = False):
    return activities_module.HealTestActivityInput(
        application_id=str(application.external_id),
        test_run_id=str(test_run.external_id),
        test_result_id=str(test_result.external_id),
        triggered_manually=manual,
    )


def _reload(test_result: TestResult) -> TestResult:
    with Session(engine) as session:
        return session.exec(select(TestResult).where(TestResult.id == test_result.id)).one()


def _current_code(test_asset: TestAsset) -> str:
    with Session(engine) as session:
        return (
            session.exec(
                select(TestAsset).where(
                    TestAsset.scenario_id == test_asset.scenario_id,
                    TestAsset.current.is_(True),  # type: ignore[attr-defined]
                )
            )
            .one()
            .code
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("manual", [False, True], ids=["automatic", "manual"])
@pytest.mark.parametrize(
    "message", ASSERTION_ELEMENT_NOT_FOUND.values(), ids=ASSERTION_ELEMENT_NOT_FOUND
)
async def test_eligibility_missing_element_in_assertion_is_never_healed(
    monkeypatch: pytest.MonkeyPatch, message: str, manual: bool
) -> None:
    application, test_asset, test_result, test_run = _seed(message)
    rerun = AsyncMock(return_value={"status": "passed"})
    monkeypatch.setattr(activities_module, "_run_playwright_with_infra_retry", rerun)

    await activities_module.heal_test_activity(
        _heal_input(application, test_run, test_result, manual=manual)
    )

    # No AI call, no rerun, no attempt spent, nothing promoted — the test
    # reports exactly what it found.
    assert _ScriptedAIProvider.calls == []
    rerun.assert_not_awaited()
    refreshed = _reload(test_result)
    assert refreshed.auto_heal_attempt_count == 0
    assert refreshed.manual_heal_attempt_count == 0
    assert refreshed.status == "failed"
    assert refreshed.error_message == message
    assert refreshed.healed_test_asset_id is None
    assert _current_code(test_asset) == ORIGINAL_SPEC


@pytest.mark.asyncio
async def test_eligibility_broken_action_locator_still_heals(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    application, test_asset, test_result, test_run = _seed(ACTION_LOCATOR_FAILURE)
    ctx = activities_module._load_heal_context_sync(_heal_input(application, test_run, test_result))
    assert ctx is not None
    (tmp_path / ctx.spec_path).parent.mkdir(parents=True, exist_ok=True)
    _ScriptedAIProvider.responses = [LOCATOR_ONLY_FIX]
    monkeypatch.setattr(
        activities_module,
        "_run_playwright_with_infra_retry",
        AsyncMock(return_value={"status": "passed"}),
    )

    await activities_module.heal_test_activity(_heal_input(application, test_run, test_result))

    refreshed = _reload(test_result)
    assert refreshed.status == "passed"
    assert refreshed.auto_heal_attempt_count == 1
    assert refreshed.healed_test_asset_id is not None
    assert _current_code(test_asset) == LOCATOR_ONLY_FIX


NON_ASSERTION_FAILURES = {
    "navigation guard": (
        "Error: Failed to load page. HTTP status: undefined\n"
        "  31 |\n  32 |   if (!response || response.status() >= 400) {\n"
        "> 33 |     throw new Error(`Failed to load page. HTTP status: ${response?.status()}`);\n"
    ),
    "page.goto timeout": (
        "TimeoutError: page.goto: Timeout 30000ms exceeded.\n"
        'Call log:\n  - navigating to "https://app.example.com/claims", waiting until "load"\n'
    ),
    "script error": "TypeError: Cannot read properties of undefined (reading 'click')",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("message", NON_ASSERTION_FAILURES.values(), ids=NON_ASSERTION_FAILURES)
async def test_eligibility_other_failures_still_heal_exactly_as_before(
    monkeypatch: pytest.MonkeyPatch, tmp_path, message: str
) -> None:
    """Only assertion failures are excluded. A failure that is neither an
    assertion nor a locator problem still goes to the AI, is rerun and
    promoted as before — and, matching the original classifier, doesn't
    trigger a live inspection."""
    application, test_asset, test_result, test_run = _seed(message)
    ctx = activities_module._load_heal_context_sync(_heal_input(application, test_run, test_result))
    assert ctx is not None
    (tmp_path / ctx.spec_path).parent.mkdir(parents=True, exist_ok=True)
    _ScriptedAIProvider.responses = [LOCATOR_ONLY_FIX]
    monkeypatch.setattr(
        activities_module,
        "_run_playwright_with_infra_retry",
        AsyncMock(return_value={"status": "passed"}),
    )

    await activities_module.heal_test_activity(_heal_input(application, test_run, test_result))

    assert len(_ScriptedAIProvider.calls) == 1
    assert _ScriptedAIProvider.calls[0]["failure_error_message"] == message
    activities_module.run_live_inspection.assert_not_awaited()
    refreshed = _reload(test_result)
    assert refreshed.status == "passed"
    assert refreshed.auto_heal_attempt_count == 1
    assert refreshed.healed_test_asset_id is not None


@pytest.mark.asyncio
async def test_guard_rejects_a_fix_that_changes_an_assertion(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The first candidate also rewrites the assertion: counted as an
    attempt, never promoted, carried forward as `repair`. The second fixes
    only the action locator and is promoted."""
    application, test_asset, test_result, test_run = _seed(ACTION_LOCATOR_FAILURE)
    ctx = activities_module._load_heal_context_sync(_heal_input(application, test_run, test_result))
    assert ctx is not None
    (tmp_path / ctx.spec_path).parent.mkdir(parents=True, exist_ok=True)
    _ScriptedAIProvider.responses = [ASSERTION_CHANGING_FIX, LOCATOR_ONLY_FIX]
    rerun = AsyncMock(return_value={"status": "passed"})
    monkeypatch.setattr(activities_module, "_run_playwright_with_infra_retry", rerun)

    await activities_module.heal_test_activity(_heal_input(application, test_run, test_result))

    assert len(_ScriptedAIProvider.calls) == 2
    repair_code, repair_problems = _ScriptedAIProvider.calls[1]["repair"]
    assert repair_code == ASSERTION_CHANGING_FIX
    assert any("Restore it exactly" in p and "Submitted" in p for p in repair_problems)
    # Only the accepted candidate was ever run or promoted.
    rerun.assert_awaited_once()
    refreshed = _reload(test_result)
    assert refreshed.auto_heal_attempt_count == 2
    assert refreshed.status == "passed"
    assert _current_code(test_asset) == LOCATOR_ONLY_FIX


@pytest.mark.asyncio
async def test_guard_rejection_is_recorded_when_the_budget_runs_out(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    application, test_asset, test_result, test_run = _seed(ACTION_LOCATOR_FAILURE)
    _ScriptedAIProvider.responses = [ASSERTION_CHANGING_FIX, ASSERTION_CHANGING_FIX]
    rerun = AsyncMock(return_value={"status": "passed"})
    monkeypatch.setattr(activities_module, "_run_playwright_with_infra_retry", rerun)

    await activities_module.heal_test_activity(_heal_input(application, test_run, test_result))

    rerun.assert_not_awaited()
    refreshed = _reload(test_result)
    assert refreshed.auto_heal_attempt_count == 2  # AUTO_HEAL_ATTEMPT_CAP
    assert refreshed.status == "failed"
    assert (refreshed.error_message or "").startswith(HEAL_ASSERTION_GUARD_ERROR_PREFIX)
    assert refreshed.healed_test_asset_id is None
    assert _current_code(test_asset) == ORIGINAL_SPEC


@pytest.mark.asyncio
async def test_eligibility_loop_stops_when_the_rerun_fails_inside_an_assertion(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The locator fix worked, and now the assertion fails — a real result.
    The loop stops there instead of spending its second attempt on it."""
    application, test_asset, test_result, test_run = _seed(ACTION_LOCATOR_FAILURE)
    ctx = activities_module._load_heal_context_sync(_heal_input(application, test_run, test_result))
    assert ctx is not None
    (tmp_path / ctx.spec_path).parent.mkdir(parents=True, exist_ok=True)
    assertion_failure = ASSERTION_ELEMENT_NOT_FOUND["toBeVisible"]
    _ScriptedAIProvider.responses = [LOCATOR_ONLY_FIX, ORIGINAL_SPEC]
    monkeypatch.setattr(
        activities_module,
        "_run_playwright_with_infra_retry",
        AsyncMock(return_value={"status": "failed", "error_message": assertion_failure}),
    )

    await activities_module.heal_test_activity(_heal_input(application, test_run, test_result))

    assert len(_ScriptedAIProvider.calls) == 1
    refreshed = _reload(test_result)
    assert refreshed.auto_heal_attempt_count == 1
    assert refreshed.status == "failed"
    assert refreshed.error_message == assertion_failure
