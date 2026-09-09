"""_load_heal_context_sync — Postgres only.

`[FIXED]` regression: `LiveHealActivity` used to pass `test_asset.scenario_id`
(the internal PK) straight into `_resolve_scenario_defaults_sync`, which
looks a Scenario up by its *external* id — every live heal attempt crashed
with `NoResultFound` before ever reaching the AI/browser. What's covered:
`_load_heal_context_sync` returns the Scenario's real `external_id`, and
that value is exactly what `_resolve_scenario_defaults_sync` needs to
resolve the same Scenario back.
"""

import uuid

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
from sqlmodel import Session, select
from workflows import AUTO_HEAL_ATTEMPT_CAP


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


def _seed_test_result() -> TestResult:
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
            scenario_id=scenario.id, test_suite_id=test_suite.id, code="// spec\n"
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
            error_message="locator not found",
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
