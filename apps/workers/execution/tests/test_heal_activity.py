"""Self-healing (HealTestActivity) — DB-facing helpers only. The full loop
(real AI call + real `npx playwright test` subprocess + tsc typecheck) is
out of scope for a unit/integration test here, same convention
`test_activities.py` already states for `ExecuteTestActivity` itself — see
the plan's manual end-to-end verification step instead. What's covered:

- `_claim_heal_sync`/`_release_heal_claim_sync` — the concurrency guard that
  keeps an automatic heal and a manual retry from racing on the same
  TestResult.
- `_load_heal_context_sync` — the eligibility no-op condition (status/
  attempt-count) that lets HealTestActivity be called unconditionally with
  no branching in workflow code.
- `_record_typecheck_failure_sync`/`_record_heal_supersede_sync` — the two
  ways one loop iteration can end, and exactly what each persists.
"""

import uuid
from datetime import UTC, datetime, timedelta

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


def _seed_application() -> Application:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Heal Test App",
            url="https://app.example.com",
            environment="staging",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.commit()
        session.refresh(application)
        return application


def _seed_test_asset(application: Application) -> TestAsset:
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
            scenario_id=scenario.id, test_suite_id=test_suite.id, code="// original spec\n"
        )
        session.add(test_asset)
        session.commit()
        session.refresh(test_asset)
        return test_asset


def _seed_test_result(application: Application, test_asset: TestAsset, *, status: str) -> TestResult:
    with Session(engine) as session:
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
            status=status,
            error_message="Timed out 15000ms waiting for expect(locator).toBeVisible()" if status != "passed" else None,
        )
        session.add(test_result)
        session.commit()
        session.refresh(test_result)
        return test_result


def _set_max_heal_attempts(value: int) -> None:
    with Session(engine) as session:
        settings = session.exec(select(DiscoverySettings)).one()
        settings.max_heal_attempts = value
        session.add(settings)
        session.commit()


# --- Concurrency guard ------------------------------------------------------


def test_claim_succeeds_when_no_prior_claim_exists() -> None:
    init_db()
    application = _seed_application()
    asset = _seed_test_asset(application)
    result = _seed_test_result(application, asset, status="failed")

    claimed = activities_module._claim_heal_sync(str(result.external_id))

    assert claimed is True
    with Session(engine) as session:
        refreshed = session.exec(
            select(TestResult).where(TestResult.id == result.id)
        ).one()
        assert refreshed.heal_started_at is not None


def test_second_claim_fails_while_first_is_active() -> None:
    """The exact race this guard exists for: an automatic heal (run right
    after ExecuteTestActivity) and a manual retry click hitting the same
    TestResult at once — only one may proceed."""
    init_db()
    application = _seed_application()
    asset = _seed_test_asset(application)
    result = _seed_test_result(application, asset, status="failed")

    first = activities_module._claim_heal_sync(str(result.external_id))
    second = activities_module._claim_heal_sync(str(result.external_id))

    assert first is True
    assert second is False


def test_claim_succeeds_again_after_release() -> None:
    init_db()
    application = _seed_application()
    asset = _seed_test_asset(application)
    result = _seed_test_result(application, asset, status="failed")

    activities_module._claim_heal_sync(str(result.external_id))
    activities_module._release_heal_claim_sync(str(result.external_id))
    reclaimed = activities_module._claim_heal_sync(str(result.external_id))

    assert reclaimed is True


def test_claim_succeeds_when_prior_claim_is_stale() -> None:
    """A worker that crashed mid-heal without reaching the `finally` release
    must not permanently lock a TestResult out of ever being healed again."""
    init_db()
    application = _seed_application()
    asset = _seed_test_asset(application)
    result = _seed_test_result(application, asset, status="failed")

    with Session(engine) as session:
        stale = session.exec(select(TestResult).where(TestResult.id == result.id)).one()
        stale.heal_started_at = datetime.now(UTC) - timedelta(hours=1)
        session.add(stale)
        session.commit()

    claimed = activities_module._claim_heal_sync(str(result.external_id))

    assert claimed is True


# --- Eligibility (no-op) condition ------------------------------------------


def test_load_heal_context_is_none_for_passed_result() -> None:
    init_db()
    application = _seed_application()
    asset = _seed_test_asset(application)
    result = _seed_test_result(application, asset, status="passed")

    ctx = activities_module._load_heal_context_sync(
        activities_module.HealTestActivityInput(
            application_id=str(application.external_id),
            test_run_id="irrelevant",
            test_result_id=str(result.external_id),
        )
    )

    assert ctx is None


def test_load_heal_context_is_none_once_budget_is_spent() -> None:
    init_db()
    _set_max_heal_attempts(3)
    application = _seed_application()
    asset = _seed_test_asset(application)
    result = _seed_test_result(application, asset, status="failed")
    with Session(engine) as session:
        spent = session.exec(select(TestResult).where(TestResult.id == result.id)).one()
        spent.heal_attempt_count = 3
        session.add(spent)
        session.commit()

    ctx = activities_module._load_heal_context_sync(
        activities_module.HealTestActivityInput(
            application_id=str(application.external_id),
            test_run_id="irrelevant",
            test_result_id=str(result.external_id),
        )
    )

    assert ctx is None


def test_load_heal_context_populated_for_eligible_failed_result() -> None:
    init_db()
    _set_max_heal_attempts(3)
    application = _seed_application()
    asset = _seed_test_asset(application)
    result = _seed_test_result(application, asset, status="failed")

    ctx = activities_module._load_heal_context_sync(
        activities_module.HealTestActivityInput(
            application_id=str(application.external_id),
            test_run_id="irrelevant",
            test_result_id=str(result.external_id),
        )
    )

    assert ctx is not None
    assert ctx.max_heal_attempts == 3
    assert ctx.scenario.id == asset.scenario_id


# --- Loop-iteration outcomes -------------------------------------------------


def test_record_typecheck_failure_increments_count_and_sets_error() -> None:
    init_db()
    application = _seed_application()
    asset = _seed_test_asset(application)
    result = _seed_test_result(application, asset, status="failed")

    activities_module._record_typecheck_failure_sync(result.id, ["error TS2304: Cannot find name 'foo'."])

    with Session(engine) as session:
        refreshed = session.exec(select(TestResult).where(TestResult.id == result.id)).one()
        assert refreshed.heal_attempt_count == 1
        assert "TS2304" in (refreshed.error_message or "")
        # The TestAsset itself is untouched — a typecheck failure never
        # gets promoted.
        current_asset = session.exec(
            select(TestAsset).where(TestAsset.id == asset.id)
        ).one()
        assert current_asset.current is True
        assert current_asset.code == "// original spec\n"


def test_record_heal_supersede_promotes_new_asset_and_flips_prior() -> None:
    """A candidate that passes typecheck becomes `current` immediately —
    regardless of what the subsequent real execution does with it (the
    "latest typechecked version always wins" rule)."""
    init_db()
    application = _seed_application()
    asset = _seed_test_asset(application)
    result = _seed_test_result(application, asset, status="failed")

    activities_module._record_heal_supersede_sync(result.id, asset.id, "// healed spec\n")

    with Session(engine) as session:
        prior = session.exec(select(TestAsset).where(TestAsset.id == asset.id)).one()
        assert prior.current is False

        new_asset = session.exec(
            select(TestAsset).where(
                TestAsset.scenario_id == asset.scenario_id,
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).one()
        assert new_asset.id != prior.id
        assert new_asset.code == "// healed spec\n"

        refreshed_result = session.exec(select(TestResult).where(TestResult.id == result.id)).one()
        assert refreshed_result.heal_attempt_count == 1
        assert refreshed_result.healed_test_asset_id == new_asset.id
