"""`heal_test_activity`'s full loop, with live inspection wired in — proves
the new capability is additive: `heal_attempt_count`/`healed_test_asset_id`
semantics are exactly what they were before this feature existed, live
inspection never consumes an attempt on its own, and its output actually
reaches the AI call. Real AI/subprocess/typecheck/browser calls are all
mocked (same DB-real, external-I/O-mocked convention as
`test_heal_activity.py`); only the activity's own control flow and DB
writes are real.
"""

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
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            from sqlalchemy import text

            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)

_LOCATOR_FAILURE_MESSAGE = "TimeoutError: waiting for locator('button[name=\"save\"]')"


def _seed_application() -> Application:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Live Inspection Test App",
            url="https://app.example.com",
            environment="staging",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.commit()
        session.refresh(application)
        return application


def _seed_test_asset_and_result(
    application: Application, *, error_message: str
) -> tuple[TestAsset, TestResult, TestRun]:
    with Session(engine) as session:
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
            name="Completes checkout",
            steps=["Add item to cart", "Click save"],
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
            scenario_id=scenario.id, test_suite_id=test_suite.id, code="// original spec\n"
        )
        session.add(test_asset)
        session.flush()

        test_run = TestRun(
            application_id=application.id,
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
        session.refresh(test_asset)
        session.refresh(test_result)
        session.refresh(test_run)
        return test_asset, test_result, test_run


def _set_max_heal_attempts(value: int) -> None:
    with Session(engine) as session:
        settings = session.exec(select(DiscoverySettings)).one()
        settings.max_heal_attempts = value
        session.add(settings)
        session.commit()


class _FakeAIProvider:
    """Records every call so the test can assert live_inspection_locators
    actually reached the AI, and returns a fixed, typecheck-passing code
    string."""

    calls: list[dict] = []

    def __init__(self) -> None:
        pass

    async def generate_playwright(self, *args: object, **kwargs: object) -> object:
        from ai_provider.test_asset_code import TestAssetCode

        _FakeAIProvider.calls.append(kwargs)
        return TestAssetCode(code="// healed spec\n")


@pytest.fixture(autouse=True)
def _prepare_project_dir(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """`heal_test_activity` assembles a real Playwright project dir and
    resolves real Vault credentials for its subprocess env — neither is
    needed here since `_run_playwright_with_infra_retry` is mocked below,
    so both are stubbed. `project_dir_for` returns a real tmp_path (not a
    plain mock) so `spec_file.write_text(...)` — genuinely exercised, not
    mocked, since it's a real, cheap filesystem write reflecting exactly
    what a real heal attempt does — has somewhere real to land."""
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(activities_module, "project_dir_for", lambda test_run_id: tmp_path)
    monkeypatch.setattr(activities_module, "_build_subprocess_env", lambda application: {})
    _FakeAIProvider.calls = []
    monkeypatch.setattr(activities_module, "HostedAIProvider", _FakeAIProvider)
    monkeypatch.setattr(
        activities_module, "typecheck_playwright_code", AsyncMock(return_value=[])
    )
    return tmp_path


@pytest.mark.asyncio
async def test_live_inspection_runs_and_heal_attempt_count_increments_exactly_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    init_db()
    _set_max_heal_attempts(3)
    application = _seed_application()
    test_asset, test_result, test_run = _seed_test_asset_and_result(
        application, error_message=_LOCATOR_FAILURE_MESSAGE
    )

    heal_input = activities_module.HealTestActivityInput(
        application_id=str(application.external_id),
        test_run_id=str(test_run.external_id),
        test_result_id=str(test_result.external_id),
    )
    ctx = activities_module._load_heal_context_sync(heal_input)
    assert ctx is not None
    (tmp_path / ctx.spec_path).parent.mkdir(parents=True, exist_ok=True)

    inspection_result = LiveInspectionResult(
        url=application.url,
        locator_candidates=[{"strategy": "testid", "value": '[data-testid="save"]'}],
        page_title="Checkout",
    )
    fake_run_live_inspection = AsyncMock(return_value=inspection_result)
    monkeypatch.setattr(activities_module, "run_live_inspection", fake_run_live_inspection)
    monkeypatch.setattr(
        activities_module,
        "_run_playwright_with_infra_retry",
        AsyncMock(return_value={"status": "passed"}),
    )

    await activities_module.heal_test_activity(heal_input)

    # Live inspection actually ran, scoped to this application's URL (no
    # known_pages exist for this minimal seed, so it falls back to the
    # application's own URL rather than any page-specific one).
    fake_run_live_inspection.assert_awaited_once()
    assert fake_run_live_inspection.await_args.kwargs["target_url"] == application.url

    # ...and its output reached the AI call.
    assert len(_FakeAIProvider.calls) == 1
    assert (
        _FakeAIProvider.calls[0]["live_inspection_locators"]
        == inspection_result.locator_candidates
    )

    with Session(engine) as session:
        refreshed_result = session.exec(
            select(TestResult).where(TestResult.id == test_result.id)
        ).one()
        # Exactly one attempt — live inspection is a sub-step within the
        # attempt, never a second one of its own.
        assert refreshed_result.heal_attempt_count == 1
        assert refreshed_result.status == "passed"

        new_asset = session.exec(
            select(TestAsset).where(
                TestAsset.scenario_id == test_asset.scenario_id,
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).one()
        assert new_asset.id != test_asset.id
        assert new_asset.code == "// healed spec\n"
        assert refreshed_result.healed_test_asset_id == new_asset.id

        prior_asset = session.exec(
            select(TestAsset).where(TestAsset.id == test_asset.id)
        ).one()
        assert prior_asset.current is False


@pytest.mark.asyncio
async def test_no_progress_guard_still_stops_the_loop_when_inspection_ran(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A live inspection running mid-attempt must not interfere with the
    existing no-progress guard: if the healed code re-fails with the exact
    same normalized failure signature, the loop still stops rather than
    spinning through the full attempt budget."""
    init_db()
    _set_max_heal_attempts(3)
    application = _seed_application()
    test_asset, test_result, test_run = _seed_test_asset_and_result(
        application, error_message=_LOCATOR_FAILURE_MESSAGE
    )

    heal_input = activities_module.HealTestActivityInput(
        application_id=str(application.external_id),
        test_run_id=str(test_run.external_id),
        test_result_id=str(test_result.external_id),
    )
    ctx = activities_module._load_heal_context_sync(heal_input)
    assert ctx is not None
    (tmp_path / ctx.spec_path).parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        activities_module,
        "run_live_inspection",
        AsyncMock(
            return_value=LiveInspectionResult(
                url=application.url, locator_candidates=[], page_title=None
            )
        ),
    )
    # The rerun fails with the exact same error message as the failure that
    # triggered healing — the no-progress guard's trigger condition.
    monkeypatch.setattr(
        activities_module,
        "_run_playwright_with_infra_retry",
        AsyncMock(return_value={"status": "failed", "error_message": _LOCATOR_FAILURE_MESSAGE}),
    )

    await activities_module.heal_test_activity(heal_input)

    with Session(engine) as session:
        refreshed_result = session.exec(
            select(TestResult).where(TestResult.id == test_result.id)
        ).one()
        # Stopped after exactly one attempt, not the full budget of 3 —
        # proving the no-progress guard fired.
        assert refreshed_result.heal_attempt_count == 1
        assert refreshed_result.status == "failed"
