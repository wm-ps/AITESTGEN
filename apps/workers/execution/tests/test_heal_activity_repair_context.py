"""`heal_test_activity`'s typecheck-retry context: a failed candidate must
be retained and handed to the *next* attempt as `repair` (candidate code +
its exact tsc diagnostics), while `previous_code` keeps describing the
original, unsuperseded TestAsset the whole time — and `field_input_types`
(the same numeric-vs-text field hint original generation already gets)
must reach every attempt. Real AI/subprocess/typecheck calls are mocked;
only the activity's own control flow and DB writes are real.
"""

import uuid
from unittest.mock import AsyncMock

import execution_worker.activities as activities_module
import pytest
from domain import (
    Application,
    DiscoveryRun,
    DiscoverySettings,
    Form,
    FormField,
    Journey,
    JourneyStep,
    Organization,
    Page,
    Scenario,
    TestAsset,
    TestResult,
    TestRun,
    TestSuite,
)
from execution_worker.db import engine, init_db
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

_ORIGINAL_CODE = "// original spec\n"
_FIRST_CANDIDATE_CODE = "// first candidate — fails typecheck\n"
_SECOND_CANDIDATE_CODE = "// second candidate — passes typecheck\n"
_TSC_ERRORS = [
    "error TS2345: Argument of type 'string' is not assignable to parameter of type 'number'."
]


def _seed_application() -> Application:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Repair Context Test App",
            url="https://app.example.com",
            environment="staging",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.commit()
        session.refresh(application)
        return application


def _seed_scenario_with_numeric_field(
    application: Application,
) -> tuple[TestAsset, TestResult, TestRun]:
    """Seeds a Page with a Form/FormField whose input_type is "number" —
    exactly the signal `spec_linter.field_input_types_for_pages` surfaces
    and the original-generation prompt's "wrap it in Number(...)" rule
    depends on — plus a JourneyStep linking the Journey to that Page, so
    `resolve_known_application_model_sync`'s known_page_ids includes it."""
    with Session(engine) as session:
        discovery_run = DiscoveryRun(application_id=application.id, status="complete")
        session.add(discovery_run)
        session.flush()
        journey = Journey(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            name="Loan Calculator",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()

        page = Page(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            url="https://app.example.com/loans/calculate",
            title="Calculate Loan",
        )
        session.add(page)
        session.flush()
        session.add(
            JourneyStep(
                journey_id=journey.id, page_id=page.id, step_order=1, stage_label="Calculate"
            )
        )

        form = Form(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            page_id=page.id,
            action_url="https://app.example.com/loans/calculate",
            method="POST",
        )
        session.add(form)
        session.flush()
        session.add(FormField(form_id=form.id, name="principal", input_type="number"))
        session.flush()

        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name="Calculates loan EMI",
            steps=["Enter principal amount", "Submit"],
            generation_run_id=journey.attempt,
            safety_classification="SAFE",
        )
        session.add(scenario)
        session.flush()
        test_suite = TestSuite(
            journey_id=journey.id, name="Loan Test Suite", generation_run_id=journey.attempt
        )
        session.add(test_suite)
        session.flush()
        test_asset = TestAsset(
            scenario_id=scenario.id, test_suite_id=test_suite.id, code=_ORIGINAL_CODE
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
            error_message=(
                "expect(received).toHaveText(expected) — received: '0', expected: '500000'"
            ),
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
    """First call returns a candidate that fails typecheck; second call
    returns one that passes. Records every call's kwargs so the test can
    assert exactly what context each attempt received."""

    calls: list[dict] = []
    _codes = [_FIRST_CANDIDATE_CODE, _SECOND_CANDIDATE_CODE]

    def __init__(self) -> None:
        pass

    async def generate_playwright(self, *args: object, **kwargs: object) -> object:
        from ai_provider.test_asset_code import TestAssetCode

        _FakeAIProvider.calls.append(kwargs)
        code = _FakeAIProvider._codes[len(_FakeAIProvider.calls) - 1]
        return TestAssetCode(code=code)


@pytest.fixture(autouse=True)
def _prepare_project_dir(monkeypatch: pytest.MonkeyPatch, tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(activities_module, "project_dir_for", lambda test_run_id: tmp_path)
    monkeypatch.setattr(activities_module, "_build_subprocess_env", lambda application: {})
    monkeypatch.setattr(activities_module, "run_live_inspection", AsyncMock(return_value=None))
    _FakeAIProvider.calls = []
    monkeypatch.setattr(activities_module, "HostedAIProvider", _FakeAIProvider)
    monkeypatch.setattr(
        activities_module,
        "typecheck_playwright_code",
        AsyncMock(side_effect=[_TSC_ERRORS, []]),
    )
    monkeypatch.setattr(
        activities_module,
        "_run_playwright_with_infra_retry",
        AsyncMock(return_value={"status": "passed"}),
    )
    return tmp_path


@pytest.mark.asyncio
async def test_failed_candidate_and_diagnostics_carry_forward_as_repair(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    init_db()
    _set_max_heal_attempts(3)
    application = _seed_application()
    test_asset, test_result, test_run = _seed_scenario_with_numeric_field(application)

    heal_input = activities_module.HealTestActivityInput(
        application_id=str(application.external_id),
        test_run_id=str(test_run.external_id),
        test_result_id=str(test_result.external_id),
    )
    ctx = activities_module._load_heal_context_sync(heal_input)
    assert ctx is not None
    assert ctx.field_input_types == {"principal": "number"}
    (tmp_path / ctx.spec_path).parent.mkdir(parents=True, exist_ok=True)

    await activities_module.heal_test_activity(heal_input)

    assert len(_FakeAIProvider.calls) == 2
    first_call, second_call = _FakeAIProvider.calls

    # Attempt 1: no repair yet, previous_code is the original baseline,
    # field_input_types already resolved and supplied.
    assert first_call["repair"] is None
    assert first_call["previous_code"] == _ORIGINAL_CODE
    assert first_call["field_input_types"] == {"principal": "number"}

    # Attempt 2: repair carries the IMMEDIATELY PREVIOUS candidate (not the
    # original code) plus its exact tsc diagnostics — while previous_code
    # is STILL the original, untouched TestAsset (never reverted to
    # anything else, since attempt 1 never got promoted).
    assert second_call["repair"] == (_FIRST_CANDIDATE_CODE, _TSC_ERRORS)
    assert second_call["previous_code"] == _ORIGINAL_CODE
    assert second_call["field_input_types"] == {"principal": "number"}

    with Session(engine) as session:
        refreshed_result = session.exec(
            select(TestResult).where(TestResult.id == test_result.id)
        ).one()
        # Both the typecheck-failed attempt and the typecheck-passed
        # attempt each consumed exactly one heal attempt — 2 total, not 1.
        assert refreshed_result.auto_heal_attempt_count == 2
        assert refreshed_result.status == "passed"

        new_asset = session.exec(
            select(TestAsset).where(
                TestAsset.scenario_id == test_asset.scenario_id,
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).one()
        # Only the typecheck-PASSING candidate was ever promoted — the
        # failed first candidate never became the current TestAsset.
        assert new_asset.code == _SECOND_CANDIDATE_CODE
        assert new_asset.id != test_asset.id

        prior_asset = session.exec(
            select(TestAsset).where(TestAsset.id == test_asset.id)
        ).one()
        assert prior_asset.current is False
        assert prior_asset.code == _ORIGINAL_CODE
