"""Test-run/execution API surface (Application Workspace feature) —
`trigger_test_run`/`list_test_runs`/`get_test_run`/`get_test_suite_status`/
`get_test_asset_code`/`get_overview`. This surface had zero test coverage
before this file.

Most of these only need Postgres (they read/write `TestRun`/`TestResult`
rows directly, never touching Temporal/Vault) — only `trigger_test_run`
actually needs Temporal reachable, since it starts a real workflow.
"""

import asyncio
import random
import string
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from api.temporal_client import get_temporal_client
from domain import (
    Application,
    DiscoveryRun,
    Journey,
    PlatformUser,
    Scenario,
    TestAsset,
    TestResult,
    TestRun,
    TestSuite,
)
from fastapi.testclient import TestClient
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select


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
    application: dict, *, scenario_name: str = "Guest checkout", source: str = "discovery"
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
            source=source,
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
    """Bypasses `_prepare_test_run_sync`'s atomic counter claim entirely
    (this seeds a row directly, not through the activity), so `run_number`
    must be assigned here — counting existing rows for this
    `application_id` mimics what the real claim would have handed out, and
    satisfies the `uq_test_run_application_id_run_number` constraint when
    a test calls this helper more than once per application."""
    with Session(engine) as session:
        existing_count = session.exec(
            select(func.count()).where(TestRun.application_id == application_id)
        ).one()
        defaults = dict(
            application_id=application_id,
            run_number=existing_count + 1,
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


class TestTriggerRecordsStarter:
    def test_trigger_passes_the_starter_user_id_to_the_workflow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from api import main as api_main

        started: list = []

        class _FakeClient:
            async def start_workflow(self, _run, workflow_input, **_kwargs) -> None:
                started.append(workflow_input)

        async def _fake_client() -> _FakeClient:
            return _FakeClient()

        async def _has_pollers(client: object, task_queue: str) -> bool:
            return True

        init_db()
        client, email = _signed_in_client("Org Trigger Starter")
        application = _create_application(client, "Starter App")
        monkeypatch.setattr(api_main, "get_temporal_client", _fake_client)
        monkeypatch.setattr(api_main, "has_pollers", _has_pollers)

        response = client.post(f"/applications/{application['id']}/test-runs")

        assert response.status_code == 202
        [workflow_input] = started
        with Session(engine) as session:
            user = session.exec(select(PlatformUser).where(PlatformUser.email == email)).one()
        assert workflow_input.triggered_by_user_id == str(user.id)
        assert workflow_input.triggered_by_name == "Tester"


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

    def test_run_number_reflects_per_application_creation_order(self) -> None:
        init_db()
        client, _ = _signed_in_client("Org Run Number")
        application = _create_application(client, "Run Number App")
        app_id, _ = _seed_test_asset(application)
        _seed_test_run(app_id)
        _seed_test_run(app_id)

        body = client.get(f"/applications/{application['id']}/test-runs").json()

        # Newest first (list order) with run_number assigned in creation order.
        assert [item["run_number"] for item in body["items"]] == [2, 1]

    def test_excludes_live_exploration_internal_verification_runs(self) -> None:
        """`[FIXED]` `LiveExplorationTestWorkflow`'s internal execute+heal
        pass creates its `TestRun`s with `triggered_by_name="Add Test Case"`
        and discards them once read — but not instantly, so for however
        long one exists before its `DiscardTestRunActivity` call, the Runs
        tab used to show it like any other real run. Must never appear
        here, discarded or not."""
        init_db()
        client, _ = _signed_in_client("Org Internal Run")
        application = _create_application(client, "Internal Run App")
        app_id, _ = _seed_test_asset(application)
        real_run = _seed_test_run(app_id)
        _seed_test_run(app_id, triggered_by_name="Add Test Case")

        body = client.get(f"/applications/{application['id']}/test-runs").json()

        assert [item["id"] for item in body["items"]] == [str(real_run.external_id)]


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
        assert body["run_number"] == 1
        assert len(body["results"]) == 1
        assert body["results"][0]["scenario_name"] == "Guest checkout"


class TestFlakyDetection:
    """`TestResultRead.is_flaky`: one Scenario's outcomes across its recent
    runs (this one included) contain both a pass and a fail."""

    def _latest_is_flaky(self, org: str, runs: list[tuple[str, dict]]) -> bool:
        """Seeds one completed-by-default run per `(result status, run
        overrides)` entry, oldest first, all for one Scenario, and returns
        `is_flaky` of the last run's only result."""
        init_db()
        client, _ = _signed_in_client(org)
        application = _create_application(client, f"{org} App")
        app_id, asset = _seed_test_asset(application)
        latest = None
        for status, overrides in runs:
            latest = _seed_test_run(app_id, **overrides)
            with Session(engine) as session:
                session.add(
                    TestResult(
                        test_run_id=latest.id,
                        test_asset_id=asset.id,
                        scenario_id=asset.scenario_id,
                        status=status,
                    )
                )
                session.commit()
        assert latest is not None
        response = client.get(
            f"/applications/{application['id']}/test-runs/{latest.external_id}"
        )
        assert response.status_code == 200
        [result] = response.json()["results"]
        return result["is_flaky"]

    def test_first_run_is_never_flaky(self) -> None:
        assert not self._latest_is_flaky("Org Flaky First", [("failed", {})])

    def test_mixed_outcomes_across_runs_are_flaky(self) -> None:
        statuses = ["failed", "failed", "passed", "failed", "passed"]
        assert self._latest_is_flaky("Org Flaky Mixed", [(s, {}) for s in statuses])

    def test_a_pass_to_fail_flip_is_flaky(self) -> None:
        assert self._latest_is_flaky("Org Flaky Flip", [("passed", {}), ("failed", {})])

    def test_consistent_outcomes_are_not_flaky(self) -> None:
        assert not self._latest_is_flaky("Org Flaky All Pass", [("passed", {})] * 3)
        assert not self._latest_is_flaky("Org Flaky All Fail", [("failed", {})] * 3)

    def test_timed_out_and_errored_count_as_failures(self) -> None:
        runs = [("passed", {}), ("timed_out", {}), ("errored", {}), ("passed", {})]
        assert self._latest_is_flaky("Org Flaky Timeout", runs)

    def test_a_failure_older_than_the_window_stops_flagging(self) -> None:
        # 10 results = this run + the 9 before it; the lone failure is the 11th.
        runs = [("failed", {})] + [("passed", {})] * 10
        assert not self._latest_is_flaky("Org Flaky Aged Out", runs)
        runs = [("failed", {})] + [("passed", {})] * 9
        assert self._latest_is_flaky("Org Flaky In Window", runs)

    def test_cancelled_and_verification_runs_carry_no_signal(self) -> None:
        runs = [
            ("passed", {}),
            ("failed", {"status": "cancelled"}),
            ("failed", {"triggered_by_name": "Add Test Case"}),
            ("passed", {}),
        ]
        assert not self._latest_is_flaky("Org Flaky Skipped Runs", runs)

    def test_a_result_still_pending_is_not_flaky(self) -> None:
        runs = [("passed", {}), ("failed", {}), ("pending", {"status": "running"})]
        assert not self._latest_is_flaky("Org Flaky Pending", runs)


class _FakeObjectStore:
    presigned: list = []

    def presigned_get_url(self, key: str, expires_seconds: int = 900, **kwargs) -> str:
        _FakeObjectStore.presigned.append((key, kwargs))
        return f"https://s3.example.com/{key}?signed"


class TestGetAllureReport:
    def _app_pk(self, application: dict) -> uuid.UUID:
        external_id = uuid.UUID(application["id"])
        with Session(engine) as session:
            return session.exec(
                select(Application.id).where(Application.external_id == external_id)
            ).one()

    def test_returns_a_presigned_html_url_when_the_run_has_a_report(self, monkeypatch) -> None:
        init_db()
        import api.main as main_module

        monkeypatch.setattr(main_module, "ObjectStore", _FakeObjectStore)
        _FakeObjectStore.presigned = []
        client, _ = _signed_in_client("Org Allure Report")
        application = _create_application(client, "Allure Report App")
        key = "test-runs/x/allure-report.html"
        test_run = _seed_test_run(self._app_pk(application), allure_report_key=key)

        response = client.get(
            f"/applications/{application['id']}/test-runs/{test_run.external_id}/allure-report"
        )

        assert response.status_code == 200
        assert response.json() == {"url": f"https://s3.example.com/{key}?signed"}
        assert _FakeObjectStore.presigned == [(key, {"response_content_type": "text/html"})]

    def test_404_when_the_run_has_no_report(self) -> None:
        init_db()
        client, _ = _signed_in_client("Org Allure No Report")
        application = _create_application(client, "Allure No Report App")
        test_run = _seed_test_run(self._app_pk(application))

        response = client.get(
            f"/applications/{application['id']}/test-runs/{test_run.external_id}/allure-report"
        )

        assert response.status_code == 404

    def test_another_org_cannot_open_the_report(self, monkeypatch) -> None:
        init_db()
        import api.main as main_module

        monkeypatch.setattr(main_module, "ObjectStore", _FakeObjectStore)
        owner, _ = _signed_in_client("Org Allure Owner")
        application = _create_application(owner, "Allure Owner App")
        test_run = _seed_test_run(
            self._app_pk(application), allure_report_key="test-runs/y/allure-report.html"
        )
        outsider, _ = _signed_in_client("Org Allure Outsider")

        response = outsider.get(
            f"/applications/{application['id']}/test-runs/{test_run.external_id}/allure-report"
        )

        assert response.status_code == 404

    def test_run_read_reports_whether_a_report_is_available(self) -> None:
        init_db()
        client, _ = _signed_in_client("Org Allure Flag")
        application = _create_application(client, "Allure Flag App")
        app_pk = self._app_pk(application)
        with_report = _seed_test_run(app_pk, allure_report_key="test-runs/z/allure-report.html")
        without_report = _seed_test_run(app_pk)

        def flag(run: TestRun) -> bool:
            response = client.get(
                f"/applications/{application['id']}/test-runs/{run.external_id}"
            )
            assert response.status_code == 200
            return response.json()["allure_report_available"]

        assert flag(with_report) is True
        assert flag(without_report) is False


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

    def test_includes_the_underlying_scenario_id(self) -> None:
        """Edit Test Data (Test Suite page) — the row needs its Scenario's
        external_id to know which Scenario's test_data to edit; TestAsset
        only carries the internal scenario_id, so this is looked up and
        exposed here."""
        init_db()
        client, _ = _signed_in_client("Org Suite Status Scenario Id")
        application = _create_application(client, "Suite Status Scenario Id App")
        _, asset = _seed_test_asset(application)
        with Session(engine) as session:
            scenario = session.get(Scenario, asset.scenario_id)
            assert scenario is not None
            expected_scenario_id = str(scenario.external_id)

        body = client.get(f"/applications/{application['id']}/test-suite-status").json()

        assert body["items"][0]["scenario_id"] == expected_scenario_id

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

    def test_ignores_a_live_exploration_internal_verification_result(self) -> None:
        """`[FIXED]` The internal execute+heal pass that runs before a
        natural-language test case ships (see live_exploration_workflow.py)
        must never surface as this test case's status — only a real,
        user-triggered "Run All Tests" execution should, even while the
        internal TestRun/TestResult still exists (before its
        DiscardTestRunActivity call deletes it)."""
        init_db()
        client, _ = _signed_in_client("Org Suite Status Internal")
        application = _create_application(client, "Suite Status Internal App")
        app_id, asset = _seed_test_asset(application)
        internal_run = _seed_test_run(app_id, triggered_by_name="Add Test Case")
        with Session(engine) as session:
            session.add(
                TestResult(
                    test_run_id=internal_run.id,
                    test_asset_id=asset.id,
                    scenario_id=asset.scenario_id,
                    status="passed",
                )
            )
            session.commit()

        body = client.get(f"/applications/{application['id']}/test-suite-status").json()

        assert body["items"][0]["status"] == "not_run"
        assert body["items"][0]["last_run_at"] is None

    def test_source_filter_scopes_items_and_total_but_counts_reflect_every_source(
        self,
    ) -> None:
        """All / Author test cases / Record-and-play tabs (Test Suite tab)."""
        init_db()
        client, _ = _signed_in_client("Org Suite Status Source Filter")
        application = _create_application(client, "Suite Status Source Filter App")
        _seed_test_asset(application, scenario_name="Discovered flow", source="discovery")
        _seed_test_asset(application, scenario_name="Authored flow", source="nl")
        _seed_test_asset(application, scenario_name="Recorded flow", source="recorded")

        all_body = client.get(f"/applications/{application['id']}/test-suite-status").json()
        assert all_body["total"] == 3
        assert all_body["source_counts"] == {"all": 3, "nl": 1, "recorded": 1}

        nl_body = client.get(
            f"/applications/{application['id']}/test-suite-status", params={"source": "nl"}
        ).json()
        assert nl_body["total"] == 1
        assert [item["name"] for item in nl_body["items"]] == ["Authored flow"]
        # Counts never change with the active filter — every tab always
        # shows the true total for its own source, not just what's in view.
        assert nl_body["source_counts"] == {"all": 3, "nl": 1, "recorded": 1}

        recorded_body = client.get(
            f"/applications/{application['id']}/test-suite-status",
            params={"source": "recorded"},
        ).json()
        assert recorded_body["total"] == 1
        assert [item["name"] for item in recorded_body["items"]] == ["Recorded flow"]


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
                run_number=1,
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

    def test_a_run_scoped_to_a_single_test_case_is_not_the_suites_latest_run(self) -> None:
        """`[FIXED]` regression: running one test case alone ("Run
        Journey(s)" scoped to a single TestAsset, `suite_name` set) used to
        become `latest_run`/a `trend` point, showing a 100%/0% pass rate for
        the whole suite based on that one test. Only an unscoped Full Suite
        run (`suite_name is None`) should ever appear here."""
        init_db()
        client, _ = _signed_in_client("Org Overview Scoped Run")
        application = _create_application(client, "Overview Scoped Run App")
        app_id, _ = _seed_test_asset(application)
        _seed_test_run(app_id, suite_name="Checkout", total_count=1, passed_count=1, failed_count=0)

        body = client.get(f"/applications/{application['id']}/overview").json()

        assert body["latest_run"] is None
        assert body["trend"] == []

        full_suite_run = _seed_test_run(app_id, total_count=2, passed_count=1, failed_count=1)

        body = client.get(f"/applications/{application['id']}/overview").json()

        assert body["latest_run"]["id"] == str(full_suite_run.external_id)
        assert len(body["trend"]) == 1

    def test_latest_run_exposes_timed_out_and_errored_counts(self) -> None:
        """`[FIXED]` regression: `latest_run` used to omit `timed_out_count`/
        `errored_count` entirely — the Overview tab's "Pass rate" tile
        computed its own denominator from just passed+failed+blocked,
        undercounting real outcomes and showing a different (inflated)
        percentage than the same run's own trend-chart bar, which already
        divides by the run's real `total_count` (every outcome included)."""
        init_db()
        client, _ = _signed_in_client("Org Overview Timed Out")
        application = _create_application(client, "Overview Timed Out App")
        app_id, _ = _seed_test_asset(application)
        _seed_test_run(
            app_id,
            total_count=108,
            passed_count=54,
            failed_count=53,
            timed_out_count=1,
            errored_count=0,
        )

        body = client.get(f"/applications/{application['id']}/overview").json()

        assert body["latest_run"]["timed_out_count"] == 1
        assert body["latest_run"]["errored_count"] == 0
        # The bar and the tile must agree: both are `passed / total_count`
        # for the exact same run.
        assert body["trend"][0]["pass_rate"] == 54 / 108


class TestCancelTestRun:
    """`cancel_test_run` — the database decides first (run + unfinished
    results "cancelled", finished results untouched), Temporal follows
    best-effort."""

    @staticmethod
    def _running_run_with_results(application: dict) -> tuple[TestRun, dict[str, uuid.UUID]]:
        application_pk, asset = _seed_test_asset(application)
        test_run = _seed_test_run(
            application_pk,
            status="running",
            workflow_id=f"execution-test-{uuid.uuid4()}",
            total_count=3,
            passed_count=1,
            failed_count=0,
        )
        result_ids: dict[str, uuid.UUID] = {}
        with Session(engine) as session:
            for label, status in (("passed", "passed"), ("queued", "pending"), ("running", "pending")):
                result = TestResult(
                    test_run_id=test_run.id,
                    test_asset_id=asset.id,
                    scenario_id=asset.scenario_id,
                    status=status,
                )
                if label == "running":
                    result.heal_started_at = datetime.now(UTC)  # a heal in flight
                session.add(result)
                session.flush()
                result_ids[label] = result.id
            session.commit()
        return test_run, result_ids

    @staticmethod
    def _fake_temporal(monkeypatch: pytest.MonkeyPatch, *, fail: bool = False) -> list[str]:
        from api import main as api_main

        cancelled: list[str] = []

        class _Handle:
            def __init__(self, workflow_id: str) -> None:
                self.workflow_id = workflow_id

            async def cancel(self) -> None:
                if fail:
                    raise RuntimeError("temporal unavailable")
                cancelled.append(self.workflow_id)

        class _FakeClient:
            def get_workflow_handle(self, workflow_id: str) -> _Handle:
                return _Handle(workflow_id)

        async def _fake_client() -> _FakeClient:
            return _FakeClient()

        monkeypatch.setattr(api_main, "get_temporal_client", _fake_client)
        return cancelled

    def test_cancel_marks_run_and_unfinished_results_and_keeps_finished_ones(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        init_db()
        client, _ = _signed_in_client("Org Cancel Run")
        application = _create_application(client, "Cancel Run App")
        test_run, result_ids = self._running_run_with_results(application)
        cancelled = self._fake_temporal(monkeypatch)

        response = client.post(
            f"/applications/{application['id']}/test-runs/{test_run.external_id}/cancel"
        )

        assert response.status_code == 200
        body = response.json()
        # The response itself already shows the cancel — no poll needed.
        assert body["status"] == "cancelled"
        assert sorted(r["status"] for r in body["results"]) == ["cancelled", "cancelled", "passed"]
        assert body["passed_count"] == 1
        assert cancelled == [test_run.workflow_id]
        with Session(engine) as session:
            results = {
                label: session.exec(select(TestResult).where(TestResult.id == pk)).one()
                for label, pk in result_ids.items()
            }
            run = session.exec(select(TestRun).where(TestRun.id == test_run.id)).one()
        assert {label: r.status for label, r in results.items()} == {
            "passed": "passed",
            "queued": "cancelled",
            "running": "cancelled",
        }
        assert results["running"].heal_started_at is None
        assert run.status == "cancelled"
        assert run.completed_at is not None

    def test_cancel_stands_even_when_temporal_cancel_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        init_db()
        client, _ = _signed_in_client("Org Cancel Run Temporal Down")
        application = _create_application(client, "Cancel Temporal Down App")
        test_run, _ = self._running_run_with_results(application)
        self._fake_temporal(monkeypatch, fail=True)

        response = client.post(
            f"/applications/{application['id']}/test-runs/{test_run.external_id}/cancel"
        )

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    @pytest.mark.parametrize("status", ["completed", "cancelled"])
    def test_cancel_refuses_a_run_that_is_not_in_progress(
        self, monkeypatch: pytest.MonkeyPatch, status: str
    ) -> None:
        init_db()
        client, _ = _signed_in_client(f"Org Cancel Finished {status}")
        application = _create_application(client, f"Cancel Finished {status} App")
        application_pk, _ = _seed_test_asset(application)
        test_run = _seed_test_run(application_pk, status=status)
        cancelled = self._fake_temporal(monkeypatch)

        response = client.post(
            f"/applications/{application['id']}/test-runs/{test_run.external_id}/cancel"
        )

        assert response.status_code == 409
        assert cancelled == []
        with Session(engine) as session:
            assert session.exec(select(TestRun).where(TestRun.id == test_run.id)).one().status == status

    def test_cancel_is_organization_scoped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        init_db()
        owner, _ = _signed_in_client("Org Cancel Owner")
        application = _create_application(owner, "Cancel Owner App")
        test_run, _ = self._running_run_with_results(application)
        cancelled = self._fake_temporal(monkeypatch)
        outsider, _ = _signed_in_client("Org Cancel Outsider")

        response = outsider.post(
            f"/applications/{application['id']}/test-runs/{test_run.external_id}/cancel"
        )

        assert response.status_code == 404
        assert cancelled == []
        with Session(engine) as session:
            assert session.exec(select(TestRun).where(TestRun.id == test_run.id)).one().status == "running"


class TestHealInProgress:
    """`heal_in_progress`/`heal_kind` on each result — read from the
    `heal_started_at` claim with the 33-minute stale rule, so the "Healing…"
    label survives reloads and shows in every tab; "manual" only while the
    `heal-{id}` Retry workflow is running. Read-only: nothing here changes how
    healing itself behaves."""

    def test_flags_live_claims_only_and_tells_manual_from_automatic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from api import main as api_main
        from temporalio.client import WorkflowExecutionStatus
        from workflows import HEAL_CLAIM_STALE_AFTER

        init_db()
        client, _ = _signed_in_client("Org Heal In Progress")
        application = _create_application(client, "Heal In Progress App")
        application_pk, asset = _seed_test_asset(application)
        test_run = _seed_test_run(application_pk, status="running", total_count=4)
        now = datetime.now(UTC)
        claims = {
            "automatic": now,
            "manual": now,
            "none": None,
            "stale": now - HEAL_CLAIM_STALE_AFTER - timedelta(minutes=1),
        }
        external_ids: dict[str, str] = {}
        with Session(engine) as session:
            for label, started in claims.items():
                result = TestResult(
                    test_run_id=test_run.id,
                    test_asset_id=asset.id,
                    scenario_id=asset.scenario_id,
                    status="failed",
                    error_message="TimeoutError: locator.click: Timeout 15000ms exceeded.",
                    heal_started_at=started,
                )
                session.add(result)
                session.flush()
                external_ids[label] = str(result.external_id)
            session.commit()
        manual_workflow_id = f"heal-{external_ids['manual']}"
        described: list[str] = []

        class _Handle:
            def __init__(self, workflow_id: str) -> None:
                self.workflow_id = workflow_id

            async def describe(self) -> SimpleNamespace:
                described.append(self.workflow_id)
                running = self.workflow_id == manual_workflow_id
                return SimpleNamespace(
                    status=WorkflowExecutionStatus.RUNNING
                    if running
                    else WorkflowExecutionStatus.COMPLETED
                )

        class _FakeClient:
            def get_workflow_handle(self, workflow_id: str) -> _Handle:
                return _Handle(workflow_id)

        async def _fake_client() -> _FakeClient:
            return _FakeClient()

        monkeypatch.setattr(api_main, "get_temporal_client", _fake_client)

        body = client.get(
            f"/applications/{application['id']}/test-runs/{test_run.external_id}"
        ).json()

        by_id = {r["id"]: r for r in body["results"]}
        state = {
            label: (by_id[eid]["heal_in_progress"], by_id[eid]["heal_kind"])
            for label, eid in external_ids.items()
        }
        assert state == {
            "automatic": (True, "automatic"),
            "manual": (True, "manual"),
            "none": (False, None),
            "stale": (False, None),
        }
        # Temporal is asked only about the live claims, never the idle ones.
        assert sorted(described) == sorted(
            f"heal-{external_ids[label]}" for label in ("automatic", "manual")
        )

    def test_temporal_unreachable_still_shows_the_heal_as_automatic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from api import main as api_main

        init_db()
        client, _ = _signed_in_client("Org Heal In Progress Temporal Down")
        application = _create_application(client, "Heal Temporal Down App")
        application_pk, asset = _seed_test_asset(application)
        test_run = _seed_test_run(application_pk, status="running", total_count=1)
        with Session(engine) as session:
            session.add(
                TestResult(
                    test_run_id=test_run.id,
                    test_asset_id=asset.id,
                    scenario_id=asset.scenario_id,
                    status="failed",
                    heal_started_at=datetime.now(UTC),
                )
            )
            session.commit()

        async def _unreachable() -> None:
            raise RuntimeError("temporal unavailable")

        monkeypatch.setattr(api_main, "get_temporal_client", _unreachable)

        body = client.get(
            f"/applications/{application['id']}/test-runs/{test_run.external_id}"
        ).json()

        assert [(r["heal_in_progress"], r["heal_kind"]) for r in body["results"]] == [
            (True, "automatic")
        ]


class TestFailureExplanations:
    """Plain-language failures on `get_test_run`: rules for known errors,
    one cached LLM explanation per distinct unknown error (claimed atomically,
    run after the response), a conservative run-level root cause — and
    `error_message` always returned exactly as stored."""

    @staticmethod
    def _run_with_results(application: dict, messages: list[tuple[str, str | None]]) -> TestRun:
        application_pk, asset = _seed_test_asset(application)
        test_run = _seed_test_run(application_pk, status="completed", total_count=len(messages))
        with Session(engine) as session:
            for status, message in messages:
                session.add(
                    TestResult(
                        test_run_id=test_run.id,
                        test_asset_id=asset.id,
                        scenario_id=asset.scenario_id,
                        status=status,
                        error_message=message,
                    )
                )
            session.commit()
        return test_run

    @staticmethod
    def _unknown_error() -> str:
        # Letters only: digits are normalised and long hex strings redacted
        # before fingerprinting, so a uuid would collide across tests.
        word = "".join(random.choice(string.ascii_lowercase) for _ in range(12))
        return f"Error: the {word} widget exploded while the app was saving qa-test-account"

    @staticmethod
    def _fake_provider(
        monkeypatch: pytest.MonkeyPatch, *, result: str = "ok", delay: float = 0.0
    ) -> list[str]:
        from ai_provider.hosted import ExplainedFailure
        from api import main as api_main

        sent: list[str] = []
        lock = threading.Lock()

        class _Provider:
            async def explain_test_failure(self, text: str) -> ExplainedFailure | None:
                with lock:
                    sent.append(text)
                if delay:
                    await asyncio.sleep(delay)
                if result == "error":
                    raise RuntimeError("proxy down")
                if result == "undetermined":
                    return None
                return ExplainedFailure(title="A widget failed", detail="It likely crashed on save.")

        monkeypatch.setattr(api_main, "HostedAIProvider", _Provider)
        return sent

    @staticmethod
    def _get(client: TestClient, application: dict, test_run: TestRun) -> dict:
        response = client.get(f"/applications/{application['id']}/test-runs/{test_run.external_id}")
        assert response.status_code == 200, response.text
        return response.json()

    def test_known_errors_get_rule_explanations_and_raw_error_is_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        init_db()
        sent = self._fake_provider(monkeypatch)
        client, _ = _signed_in_client("Org Failure Rules")
        application = _create_application(client, "Failure Rules App")
        raw = (
            "TimeoutError: locator.click: Timeout 15000ms exceeded.\nCall log:\n"
            "  - waiting for getByRole('button', { name: 'Submit' })\n"
        )
        test_run = self._run_with_results(application, [("failed", raw), ("passed", None)])

        body = self._get(client, application, test_run)

        failed = next(r for r in body["results"] if r["status"] == "failed")
        passed = next(r for r in body["results"] if r["status"] == "passed")
        assert failed["failure_title"] == 'Couldn\'t click the "Submit" button'
        assert failed["failure_source"] == "rules"
        assert failed["error_message"] == raw
        assert passed["failure_title"] is None
        assert sent == []  # no LLM for a known error

    def test_root_cause_only_when_a_shared_cause_dominates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        init_db()
        self._fake_provider(monkeypatch)
        client, _ = _signed_in_client("Org Failure Root Cause")
        application = _create_application(client, "Failure Root Cause App")
        sign_in = "failed to prepare the test project: auth.setup.ts failed (exit 1):"
        shared = self._run_with_results(
            application, [("errored", sign_in)] * 3 + [("failed", "Error: locator not found")]
        )
        mixed = self._run_with_results(
            application,
            [
                ("failed", "Error: expect(locator).toBeVisible() failed"),
                ("failed", "Error: locator not found"),
            ]
            * 2,
        )

        assert self._get(client, application, shared)["root_cause"] == {
            "title": "Vantage couldn't sign in to the app",
            "affected": 3,
            "total": 4,
        }
        assert self._get(client, application, mixed)["root_cause"] is None

    def test_unknown_error_is_explained_once_after_the_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        init_db()
        sent = self._fake_provider(monkeypatch)
        client, _ = _signed_in_client("Org Failure AI")
        application = _create_application(client, "Failure AI App")
        message = self._unknown_error()
        test_run = self._run_with_results(application, [("failed", message), ("failed", message)])

        first = self._get(client, application, test_run)
        # Built before the LLM answered: the cleaned line, no source yet.
        assert {r["failure_source"] for r in first["results"]} == {None}
        assert first["results"][0]["failure_title"].startswith("the ")
        second = self._get(client, application, test_run)
        third = self._get(client, application, test_run)

        assert len(sent) == 1  # two results, three polls, one call
        for body in (second, third):
            for r in body["results"]:
                assert (r["failure_title"], r["failure_source"]) == ("A widget failed", "ai")
                assert r["error_message"] == message
        # The app's own saved username never reaches the LLM.
        assert "qa-test-account" not in sent[0]

    def test_simultaneous_requests_make_one_llm_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        init_db()
        sent = self._fake_provider(monkeypatch, delay=0.5)
        client, _ = _signed_in_client("Org Failure AI Concurrency")
        application = _create_application(client, "Failure AI Concurrency App")
        test_run = self._run_with_results(application, [("failed", self._unknown_error())] * 3)
        barrier = threading.Barrier(6)

        def poll() -> None:
            barrier.wait()
            self._get(client, application, test_run)

        threads = [threading.Thread(target=poll) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(sent) == 1

    def test_llm_failure_and_undetermined_answers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        init_db()
        client, _ = _signed_in_client("Org Failure AI Fallbacks")
        application = _create_application(client, "Failure AI Fallbacks App")

        sent = self._fake_provider(monkeypatch, result="error")
        broken = self._run_with_results(application, [("failed", self._unknown_error())])
        self._get(client, application, broken)
        after_error = self._get(client, application, broken)["results"][0]
        assert after_error["failure_source"] is None  # the cleaned line keeps showing
        assert len(sent) == 1  # a failed explanation isn't retried on every poll

        self._fake_provider(monkeypatch, result="undetermined")
        unclear = self._run_with_results(application, [("failed", self._unknown_error())])
        self._get(client, application, unclear)
        result = self._get(client, application, unclear)["results"][0]
        assert result["failure_title"] == "The test failed for a reason Vantage couldn't identify"
        assert result["failure_source"] == "ai"
