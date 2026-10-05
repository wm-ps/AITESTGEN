"""save_recording_sync's "Recorded tests" bucket and the legacy conversion's
regrouping — Postgres only. Each test creates its own Organization/
Application and deletes everything under it afterwards."""

import hashlib
import uuid

import pytest
from domain import (
    Application,
    DiscoveryRun,
    Journey,
    Organization,
    Scenario,
    TestAsset,
    TestSuite,
)
from recording_worker.convert_legacy_recordings import (
    AssetPlan,
    convert_code,
    migrate_application_sync,
)
from recording_worker.db import engine
from recording_worker.persistence import (
    LEGACY_RECORDING_JOURNEY_DESCRIPTION,
    RECORDED_TESTS_JOURNEY_NAME,
    create_recording_discovery_run_sync,
    save_recording_sync,
)
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError, OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)

_LEGACY_CODE = """\
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: false
  });
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('https://app.example.com/');

  // ---------------------
  await context.close();
  await browser.close();
})();
"""


@pytest.fixture
def application():
    with Session(engine) as session:
        org = Organization(name=f"Recording Persistence Test Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        app = Application(
            organization_id=org.id,
            name="Recording Persistence Test App",
            url="https://app.example.com",
            environment="test",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(app)
        session.commit()
        session.refresh(app)
        session.expunge(app)
    yield app
    with Session(engine) as session:
        params = {"app_id": app.id}
        app_journeys = "(SELECT id FROM journey WHERE application_id = :app_id)"
        for statement in (
            "DELETE FROM test_asset WHERE scenario_id IN "
            f"(SELECT id FROM scenario WHERE journey_id IN {app_journeys})",
            f"DELETE FROM scenario WHERE journey_id IN {app_journeys}",
            f"DELETE FROM test_suite WHERE journey_id IN {app_journeys}",
            "DELETE FROM journey WHERE application_id = :app_id",
            "DELETE FROM discovery_run WHERE application_id = :app_id",
            "DELETE FROM application WHERE id = :app_id",
        ):
            session.exec(text(statement), params=params)
        session.exec(
            text("DELETE FROM organization WHERE id = :org_id"),
            params={"org_id": app.organization_id},
        )
        session.commit()


def _save(application: Application, name: str):
    return save_recording_sync(
        application_id=application.id,
        discovery_run_id=create_recording_discovery_run_sync(application.id),
        code="import { test } from '@playwright/test';\n\ntest('x', async ({ page }) => {});\n",
        steps=[],
        requires_auth=False,
        name=name,
    )


def test_recordings_share_one_recorded_tests_journey(application):
    first = _save(application, "check balance")
    second = _save(application, "check balance")

    assert first.journey_external_id == second.journey_external_id
    with Session(engine) as session:
        journeys = session.exec(
            select(Journey).where(Journey.application_id == application.id)
        ).all()
        assert [j.name for j in journeys] == [RECORDED_TESTS_JOURNEY_NAME]
        suites = session.exec(select(TestSuite).where(TestSuite.journey_id == journeys[0].id)).all()
        assert len(suites) == 1
        scenarios = session.exec(
            select(Scenario).where(Scenario.journey_id == journeys[0].id)
        ).all()
        assert sorted(s.name for s in scenarios) == ["check balance", "check balance"]
        assets = session.exec(
            select(TestAsset).where(TestAsset.test_suite_id == suites[0].id)
        ).all()
        assert len(assets) == 2
        runs = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.application_id == application.id, DiscoveryRun.source == "recorded"
            )
        ).all()
        assert len(runs) == 1


def _seed_legacy_recording(session: Session, application: Application, run_id, name: str):
    journey = Journey(
        application_id=application.id,
        discovery_run_id=run_id,
        name=name,
        description=LEGACY_RECORDING_JOURNEY_DESCRIPTION,
        identity_key=hashlib.sha256(f"recording:{uuid.uuid4()}".encode()).hexdigest(),
        attempt=1,
    )
    session.add(journey)
    session.flush()
    suite = TestSuite(
        journey_id=journey.id,
        name=f"{name} Test Suite",
        generation_run_id=1,
        current=True,
        status="complete",
    )
    session.add(suite)
    session.flush()
    scenario = Scenario(
        journey_id=journey.id,
        type="happy",
        name=name,
        steps=[],
        expected_result="",
        test_data=[],
        generation_run_id=1,
        test_case_number=1,
        current=True,
        source="recorded",
    )
    session.add(scenario)
    session.flush()
    asset = TestAsset(
        scenario_id=scenario.id,
        test_suite_id=suite.id,
        code=_LEGACY_CODE,
        current=True,
        requires_auth=False,
        status="ready",
        warnings=[],
    )
    session.add(asset)
    session.flush()
    return journey, asset


def _plan(asset: TestAsset, name: str) -> AssetPlan:
    return AssetPlan(
        test_asset_id=asset.id,
        application_name="app",
        old_journey_name=name,
        requires_auth=False,
        old_code=asset.code,
        new_code=convert_code(asset.code, name=name, requires_auth=False),
    )


def test_conversion_moves_legacy_recordings_into_the_bucket(application):
    with Session(engine) as session:
        run = DiscoveryRun(application_id=application.id, status="complete", source="recorded")
        session.add(run)
        session.flush()
        old_a, asset_a = _seed_legacy_recording(session, application, run.id, "Recorded flow")
        old_b, asset_b = _seed_legacy_recording(session, application, run.id, "Recorded flow (2)")
        # A non-recorded Scenario still on old_b must keep it from being deleted.
        session.add(
            Scenario(
                journey_id=old_b.id,
                type="happy",
                name="not a recording",
                steps=[],
                expected_result="",
                test_data=[],
                generation_run_id=1,
                test_case_number=2,
                current=True,
                source="discovery",
            )
        )
        session.commit()
        plans = {asset_a.id: _plan(asset_a, old_a.name), asset_b.id: _plan(asset_b, old_b.name)}

        report = migrate_application_sync(session, application.id, plans)
        session.commit()

        assert sorted(report.moved) == ["Recorded flow", "Recorded flow (2)"]
        assert report.deleted_journeys == ["Recorded flow"]
        assert len(report.skipped_journeys) == 1 and "scenario" in report.skipped_journeys[0]

        names = {
            j.name
            for j in session.exec(select(Journey).where(Journey.application_id == application.id))
        }
        assert names == {RECORDED_TESTS_JOURNEY_NAME, "Recorded flow (2)"}
        bucket = session.exec(
            select(Journey).where(
                Journey.application_id == application.id,
                Journey.name == RECORDED_TESTS_JOURNEY_NAME,
            )
        ).one()
        moved = session.exec(select(Scenario).where(Scenario.journey_id == bucket.id)).all()
        assert sorted(s.name for s in moved) == ["Recorded flow", "Recorded flow (2)"]
        session.refresh(asset_a)
        assert asset_a.code.startswith("import { test, expect } from '@playwright/test';")
        assert "test('Recorded flow', { tag: '@public' }, async ({ page }) => {" in asset_a.code


def test_conversion_dry_run_rolls_back(application):
    with Session(engine) as session:
        run = DiscoveryRun(application_id=application.id, status="complete", source="recorded")
        session.add(run)
        session.flush()
        old, asset = _seed_legacy_recording(session, application, run.id, "Recorded flow")
        session.commit()
        migrate_application_sync(session, application.id, {asset.id: _plan(asset, old.name)})
        session.rollback()

        names = {
            j.name
            for j in session.exec(select(Journey).where(Journey.application_id == application.id))
        }
        assert names == {"Recorded flow"}
        session.refresh(asset)
        assert asset.code == _LEGACY_CODE
