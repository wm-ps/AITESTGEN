"""Test-run/execution API surface (Application Workspace feature) —
`trigger_test_run`/`list_test_runs`/`get_test_run`/`get_test_suite_status`/
`get_test_asset_code`/`get_overview`. This surface had zero test coverage
before this file.

Most of these only need Postgres (they read/write `TestRun`/`TestResult`
rows directly, never touching Temporal/Vault) — only `trigger_test_run`
actually needs Temporal reachable, since it starts a real workflow.
"""

import asyncio
import uuid

import pytest
from api.db import engine, init_db
from api.scripts.seed_dev_data import seed
from api.temporal_client import get_temporal_client
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
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from api.main import app


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


def _temporal_available() -> bool:
    async def _check() -> bool:
        try:
            await get_temporal_client()
            return True
        except Exception:
            return False

    return asyncio.run(_check())


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)


def _signed_in_client(org_name: str) -> tuple[TestClient, str]:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org_name, name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client, email


def _create_application(client: TestClient, name: str) -> dict:
    response = client.post(
        "/applications",
        json={
            "name": name,
            "url": "https://staging.example.com",
            "environment": "staging",
            "auth_method": "standard_login",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )
    assert response.status_code == 201
    return response.json()


def _seed_test_asset(
    application: dict, *, scenario_name: str = "Guest checkout"
) -> tuple[uuid.UUID, TestAsset]:
    """Seeds a Journey -> Scenario -> TestSuite -> TestAsset chain for an
    onboarded Application, mirroring `_add_candidate_journey_with_suite` in
    `test_test_suite_export.py`. Returns `(application_internal_id,
    test_asset)` — callers use the returned `TestAsset` directly rather than
    re-querying "the first TestAsset in the table", which is unsafe once
    more than one test has run against this shared, never-truncated dev DB
    (this codebase's own established test convention relies on unique
    names/orgs per test, not table resets)."""
    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        journey = Journey(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            name="Checkout",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()
        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name=scenario_name,
            steps=["Add item to cart"],
            expected_result="Order confirmed",
            test_data=[],
            generation_run_id=journey.attempt,
        )
        session.add(scenario)
        session.flush()
        test_suite = TestSuite(
            journey_id=journey.id, name="Checkout Test Suite", generation_run_id=journey.attempt
        )
        session.add(test_suite)
        session.flush()
        test_asset = TestAsset(scenario_id=scenario.id, test_suite_id=test_suite.id, code="// spec\n")
        session.add(test_asset)
        session.commit()
        session.refresh(test_asset)
        return discovery_run.application_id, test_asset


def _seed_test_run(application_id: uuid.UUID, **overrides) -> TestRun:
    with Session(engine) as session:
        defaults = dict(
            application_id=application_id,
            status="completed",
            environment_snapshot="staging",
            target_base_url_snapshot="https://staging.example.com",
            total_count=2,
            passed_count=1,
            failed_count=1,
        )
        defaults.update(overrides)
        test_run = TestRun(**defaults)
        session.add(test_run)
        session.commit()
        session.refresh(test_run)
        return test_run


class TestTriggerTestRun:
    @pytest.mark.skipif(not _temporal_available(), reason="requires Temporal reachable")
    def test_trigger_starts_a_workflow_and_returns_started(self) -> None:
        init_db()
        client, _ = _signed_in_client("Org Trigger")
        application = _create_application(client, "Trigger App")

        response = client.post(f"/applications/{application['id']}/test-runs")

        assert response.status_code == 202
        assert response.json() == {"started": True}

    @pytest.mark.skipif(not _temporal_available(), reason="requires Temporal reachable")
    def test_trigger_reports_unavailable_when_execution_queue_has_no_worker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from api import main as api_main

        async def _no_pollers(client: object, task_queue: str) -> bool:
            return False

        monkeypatch.setattr(api_main, "has_pollers", _no_pollers)

        init_db()
        client, _ = _signed_in_client("Org Trigger Worker Down")
        application = _create_application(client, "No Execution Worker App")

        response = client.post(f"/applications/{application['id']}/test-runs")

        assert response.status_code == 503
        assert response.json()["detail"] == "EXECUTION_UNAVAILABLE"


class TestExecutionStatus:
    @pytest.mark.skipif(not _temporal_available(), reason="requires Temporal reachable")
    def test_reports_unavailable_when_execution_queue_has_no_worker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`has_pollers` is only checked once, before the workflow starts —
        a worker that crashes right after leaves the run sitting at
        "running" with nothing to explain why. RunsTab polls this
        separately to tell that apart from a run genuinely still in
        flight."""
        from api import main as api_main

        async def _no_pollers(client: object, task_queue: str) -> bool:
            return False

        monkeypatch.setattr(api_main, "has_pollers", _no_pollers)

        init_db()
        client, _ = _signed_in_client("Org Execution Status Down")
        application = _create_application(client, "No Execution Worker Status App")

        response = client.get(f"/applications/{application['id']}/execution-status")

        assert response.status_code == 200
        assert response.json() == {"available": False}


class TestListTestRuns:
    def test_returns_cursor_envelope_newest_first(self) -> None:
        init_db()
        client, _ = _signed_in_client("Org List Runs")
        application = _create_application(client, "List Runs App")
        app_id, _ = _seed_test_asset(application)
        older = _seed_test_run(app_id)
        newer = _seed_test_run(app_id)

        response = client.get(f"/applications/{application['id']}/test-runs")

        assert response.status_code == 200
        body = response.json()
        assert body["next_cursor"] is None
        assert [r["id"] for r in body["items"]] == [str(newer.external_id), str(older.external_id)]

    def test_limit_is_respected(self) -> None:
        init_db()
        client, _ = _signed_in_client("Org List Runs Paged")
        application = _create_application(client, "List Runs Paged App")
        app_id, _ = _seed_test_asset(application)
        for _ in range(3):
            _seed_test_run(app_id)

        response = client.get(
            f"/applications/{application['id']}/test-runs", params={"limit": 2}
        )

        body = response.json()
        assert len(body["items"]) == 2
        assert body["next_cursor"] is not None

    def test_cursor_pages_through_all_items_without_duplicates_or_gaps(self) -> None:
        init_db()
        client, _ = _signed_in_client("Org List Runs Cursor")
        application = _create_application(client, "List Runs Cursor App")
        app_id, _ = _seed_test_asset(application)
        runs = [_seed_test_run(app_id) for _ in range(5)]
        expected_ids = [str(r.external_id) for r in reversed(runs)]

        seen_ids: list[str] = []
        cursor: str | None = None
        for _ in range(10):  # safety cap against an infinite loop if next_cursor never clears
            params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
            body = client.get(f"/applications/{application['id']}/test-runs", params=params).json()
            seen_ids += [r["id"] for r in body["items"]]
            cursor = body["next_cursor"]
            if cursor is None:
                break

        assert seen_ids == expected_ids

    def test_trigger_and_pass_rate_fields(self) -> None:
        init_db()
        client, _ = _signed_in_client("Org Trigger Field")
        application = _create_application(client, "Trigger Field App")
        app_id, _ = _seed_test_asset(application)
        _seed_test_run(app_id, triggered_by_name="Sailaja Poranki", total_count=4, passed_count=3)

        body = client.get(f"/applications/{application['id']}/test-runs").json()

        item = body["items"][0]
        assert item["trigger"] == "Manual run by Sailaja Poranki"
        assert item["pass_rate"] == 0.75

    def test_no_triggered_by_name_reads_as_plain_manual_run(self) -> None:
        init_db()
        client, _ = _signed_in_client("Org No Trigger Name")
        application = _create_application(client, "No Trigger Name App")
        app_id, _ = _seed_test_asset(application)
        _seed_test_run(app_id, triggered_by_name=None)

        body = client.get(f"/applications/{application['id']}/test-runs").json()

        assert body["items"][0]["trigger"] == "Manual run"


class TestGetTestRun:
    def test_detail_includes_results(self) -> None:
        init_db()
        client, _ = _signed_in_client("Org Run Detail")
        application = _create_application(client, "Run Detail App")
        app_id, asset = _seed_test_asset(application)
        test_run = _seed_test_run(app_id)
        with Session(engine) as session:
            session.add(
                TestResult(
                    test_run_id=test_run.id,
                    test_asset_id=asset.id,
                    scenario_id=asset.scenario_id,
                    status="passed",
                )
            )
            session.commit()

        response = client.get(
            f"/applications/{application['id']}/test-runs/{test_run.external_id}"
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["results"]) == 1
        assert body["results"][0]["scenario_name"] == "Guest checkout"


class TestGetTestSuiteStatus:
    def test_never_run_asset_reads_as_not_run(self) -> None:
        init_db()
        client, _ = _signed_in_client("Org Suite Status")
        application = _create_application(client, "Suite Status App")
        _seed_test_asset(application)

        response = client.get(f"/applications/{application['id']}/test-suite-status")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "not_run"
        assert body["items"][0]["last_run_at"] is None

    def test_collapses_timed_out_and_errored_to_failed(self) -> None:
        init_db()
        client, _ = _signed_in_client("Org Suite Status Collapse")
        application = _create_application(client, "Suite Status Collapse App")
        app_id, asset = _seed_test_asset(application)
        test_run = _seed_test_run(app_id)
        with Session(engine) as session:
            session.add(
                TestResult(
                    test_run_id=test_run.id,
                    test_asset_id=asset.id,
                    scenario_id=asset.scenario_id,
                    status="timed_out",
                )
            )
            session.commit()

        body = client.get(f"/applications/{application['id']}/test-suite-status").json()

        assert body["items"][0]["status"] == "failed"


class TestGetTestAssetCode:
    def test_returns_the_generated_code(self) -> None:
        init_db()
        client, _ = _signed_in_client("Org Asset Code")
        application = _create_application(client, "Asset Code App")
        _, asset = _seed_test_asset(application)

        response = client.get(f"/test-assets/{asset.external_id}/code")

        assert response.status_code == 200
        assert response.json() == {"code": "// spec\n"}

    def test_other_org_cannot_read_the_code(self) -> None:
        init_db()
        client_a, _ = _signed_in_client("Org Asset Code A")
        application = _create_application(client_a, "Asset Code App A")
        _, asset = _seed_test_asset(application)
        client_b, _ = _signed_in_client("Org Asset Code B")

        response = client_b.get(f"/test-assets/{asset.external_id}/code")

        assert response.status_code == 404


class TestGetOverview:
    def test_no_runs_yet_is_critical_with_zero_pass_rate(self) -> None:
        """A never-run test is still a current test under the confirmed
        Pass Rate = passed / every current test formula — 0 passed / 1
        total is a real 0.0, not None. `pass_rate` is only None when
        `total_tests == 0` (no current tests exist at all), which isn't
        this scenario."""
        init_db()
        client, _ = _signed_in_client("Org Overview Empty")
        application = _create_application(client, "Overview Empty App")
        _seed_test_asset(application)

        response = client.get(f"/applications/{application['id']}/overview")

        assert response.status_code == 200
        body = response.json()
        assert body["total_tests"] == 1
        assert body["not_run"] == 1
        assert body["pass_rate"] == 0.0
        assert body["health"]["tier"] == "critical"
        assert body["latest_run"] is None

    def test_not_run_tests_count_against_pass_rate(self) -> None:
        """Confirmed product decision: Pass Rate = passed / every current
        test, not passed / (passed + failed) — a not-run test counts
        against you, it isn't excluded from the denominator."""
        init_db()
        client, _ = _signed_in_client("Org Overview Denominator")
        application = _create_application(client, "Overview Denominator App")
        app_id, asset_a = _seed_test_asset(application, scenario_name="Scenario A")
        # A second current TestAsset that's never been run.
        with Session(engine) as session:
            journey = session.exec(select(Journey).where(Journey.application_id == app_id)).one()
            test_suite = session.exec(
                select(TestSuite).where(TestSuite.journey_id == journey.id)
            ).one()
            scenario_b = Scenario(
                journey_id=journey.id,
                type="happy",
                name="Scenario B",
                steps=["Do a thing"],
                generation_run_id=journey.attempt,
            )
            session.add(scenario_b)
            session.flush()
            session.add(
                TestAsset(scenario_id=scenario_b.id, test_suite_id=test_suite.id, code="// b\n")
            )
            session.commit()

            test_run = TestRun(
                application_id=app_id,
                status="completed",
                environment_snapshot="staging",
                target_base_url_snapshot="https://staging.example.com",
            )
            session.add(test_run)
            session.flush()
            session.add(
                TestResult(
                    test_run_id=test_run.id,
                    test_asset_id=asset_a.id,
                    scenario_id=asset_a.scenario_id,
                    status="passed",
                )
            )
            session.commit()

        body = client.get(f"/applications/{application['id']}/overview").json()

        assert body["total_tests"] == 2
        assert body["passed"] == 1
        assert body["not_run"] == 1
        assert body["pass_rate"] == 0.5  # 1 passed / 2 total, not 1/1
