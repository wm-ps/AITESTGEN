"""A run against a non-default environment uses that environment's URL, login
URL, auth and secret on every path that picks one — prepare (snapshots, the
assembled project, the shared sign-in), the per-test context (which feeds the
auth refresh and the credentials env), the rebuild of an evicted project dir,
and self-heal's saved code. A run with no environment is exactly what it was.

Postgres only; the assembler, `npm install` and the sign-in are stubbed (same
approach as test_activities.py) and record what they were handed.
"""

import uuid
from types import SimpleNamespace

import execution_worker.activities as activities_module
import pytest
from domain import (
    Application,
    ApplicationEnvironment,
    DiscoveryRun,
    Journey,
    Organization,
    Scenario,
    Schedule,
    TestAsset,
    TestCollection,
    TestResult,
    TestRun,
    TestSuite,
)
from execution_worker.db import engine, init_db
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import ExecuteTestActivityInput, PrepareTestRunActivityInput

DEFAULT_URL = "https://prod.example.com/"
ENV_URL = "https://uat.example.com/"


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


def _seed() -> tuple[Application, ApplicationEnvironment, TestAsset]:
    init_db()
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Env Run App",
            url=DEFAULT_URL,
            login_url="https://prod.example.com/signin",
            environment="production",
            auth_method="standard_login",
            secret_ref="applications/org/default",
        )
        session.add(application)
        session.flush()
        environment = ApplicationEnvironment(
            application_id=application.id,
            name="UAT",
            url=ENV_URL,
            login_url="https://uat.example.com/signin",
            auth_method="standard_login",
            secret_ref="applications/org/uat",
        )
        session.add(environment)
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
        suite = TestSuite(
            journey_id=journey.id, name="Checkout Test Suite", generation_run_id=journey.attempt
        )
        session.add(suite)
        session.flush()
        asset = TestAsset(
            scenario_id=scenario.id,
            test_suite_id=suite.id,
            code=f"await page.goto('{DEFAULT_URL}cart');\n",
        )
        session.add(asset)
        session.commit()
        for row in (application, environment, asset):
            session.refresh(row)
        return application, environment, asset


def _view(application: Application) -> SimpleNamespace:
    """What a stub was handed, copied at call time (the real row is bound to a
    session that is closed by the time a test looks at it)."""
    return SimpleNamespace(
        url=application.url,
        login_url=application.login_url,
        secret_ref=application.secret_ref,
        auth_method=application.auth_method,
        environment=application.environment,
    )


class _Recorder:
    """Stubs the assembler / install / sign-in and remembers their arguments.
    There is no captured login page in these fixtures, so the evidence lookup
    is stubbed to a non-None value — that is what makes a run sign in."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.assembled: list[tuple[SimpleNamespace, str | None]] = []
        self.signed_in: list[SimpleNamespace] = []
        self.evidence_for: list[SimpleNamespace] = []

        def _assemble(dest_dir, application, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            retarget_from = args[-1] if len(args) >= 6 else kwargs.get("retarget_from")
            self.assembled.append((_view(application), retarget_from))

        def _evidence(session, application):  # noqa: ANN001
            self.evidence_for.append(_view(application))
            return object()

        monkeypatch.setattr(activities_module, "assemble_test_suite_project_to_dir", _assemble)
        monkeypatch.setattr(activities_module, "find_login_page_evidence", _evidence)
        monkeypatch.setattr(activities_module, "_install_project", lambda *a, **k: None)
        monkeypatch.setattr(
            activities_module,
            "_run_auth_setup_once",
            lambda dest_dir, application: self.signed_in.append(_view(application)),
        )


def _prepare(application: Application, **fields) -> TestRun:
    result = activities_module._prepare_test_run_sync(
        PrepareTestRunActivityInput(application_id=str(application.external_id), **fields)
    )
    with Session(engine) as session:
        return session.exec(
            select(TestRun).where(TestRun.external_id == uuid.UUID(result.test_run_id))
        ).one()


def test_a_run_with_no_environment_targets_the_application_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _, _ = _seed()
    recorder = _Recorder(monkeypatch)

    run = _prepare(application)

    assert (run.environment_id, run.environment_snapshot, run.target_base_url_snapshot) == (
        None,
        "production",
        DEFAULT_URL,
    )
    (assembled, retarget_from), = recorder.assembled
    assert assembled.url == DEFAULT_URL and retarget_from is None


def test_a_run_for_an_environment_records_and_assembles_for_that_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, environment, _ = _seed()
    recorder = _Recorder(monkeypatch)

    run = _prepare(application, environment_id=str(environment.external_id))

    assert run.environment_id == environment.id
    assert (run.environment_snapshot, run.target_base_url_snapshot) == ("UAT", ENV_URL)
    (assembled, retarget_from), = recorder.assembled
    assert (assembled.url, assembled.login_url, assembled.secret_ref) == (
        ENV_URL,
        "https://uat.example.com/signin",
        "applications/org/uat",
    )
    assert retarget_from == DEFAULT_URL  # tests' default-host URLs get rewritten
    assert [a.secret_ref for a in recorder.signed_in] == ["applications/org/uat"]
    assert [a.url for a in recorder.evidence_for] == [ENV_URL]
    # The Application row itself is untouched.
    with Session(engine) as session:
        stored = session.exec(select(Application).where(Application.id == application.id)).one()
        assert (stored.url, stored.environment) == (DEFAULT_URL, "production")


def test_a_scheduled_run_uses_its_schedules_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    application, environment, _ = _seed()
    _Recorder(monkeypatch)
    with Session(engine) as session:
        schedule = Schedule(
            application_id=application.id,
            name="UAT nightly",
            cadence_type="daily",
            hour=2,
            minute=0,
            time_zone="UTC",
            temporal_schedule_id=f"app-schedule-{uuid.uuid4()}",
            environment_id=environment.id,
        )
        session.add(schedule)
        session.commit()
        session.refresh(schedule)

    run = _prepare(application, schedule_id=str(schedule.external_id), triggered_by_name="UAT nightly")

    assert run.schedule_id == schedule.id
    assert (run.environment_id, run.environment_snapshot) == (environment.id, "UAT")


def test_an_unknown_environment_fails_before_a_run_number_is_claimed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _, _ = _seed()
    _Recorder(monkeypatch)

    with pytest.raises(LookupError):
        _prepare(application, environment_id=str(uuid.uuid4()))

    with Session(engine) as session:
        stored = session.exec(select(Application).where(Application.id == application.id)).one()
        assert stored.next_test_run_number == 1
        assert session.exec(select(TestRun).where(TestRun.application_id == application.id)).all() == []


def test_the_per_test_context_carries_the_runs_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    application, environment, asset = _seed()
    _Recorder(monkeypatch)
    run = _prepare(application, environment_id=str(environment.external_id))
    with Session(engine) as session:
        result = session.exec(select(TestResult).where(TestResult.test_run_id == run.id)).one()

    context = activities_module._load_execution_context_sync(
        ExecuteTestActivityInput(
            application_id=str(application.external_id),
            test_run_id=str(run.external_id),
            test_result_id=str(result.external_id),
            test_asset_id=str(asset.external_id),
        )
    )

    assert context is not None
    assert (context.application.url, context.application.secret_ref) == (
        ENV_URL,
        "applications/org/uat",
    )


def test_rebuilding_an_evicted_project_dir_uses_the_runs_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    application, environment, _ = _seed()
    recorder = _Recorder(monkeypatch)
    run = _prepare(application, environment_id=str(environment.external_id))
    recorder.assembled.clear()
    recorder.signed_in.clear()
    monkeypatch.setattr(activities_module, "project_dir_for", lambda _id: tmp_path / "gone")

    activities_module._rebuild_project_dir_sync(run.external_id, application.external_id)

    (assembled, retarget_from), = recorder.assembled
    assert (assembled.url, retarget_from) == (ENV_URL, DEFAULT_URL)
    assert [a.url for a in recorder.signed_in] == [ENV_URL]


def test_heal_shows_and_runs_the_environments_urls_but_saves_default_host_code() -> None:
    environment_ctx = SimpleNamespace(retarget_from=DEFAULT_URL, application=SimpleNamespace(url=ENV_URL))
    default_ctx = SimpleNamespace(retarget_from=None, application=SimpleNamespace(url=DEFAULT_URL))
    saved = f"await page.goto('{DEFAULT_URL}cart');"
    healed_on_env = f"await page.goto('{ENV_URL}cart');"

    assert activities_module._code_for_run(saved, environment_ctx) == healed_on_env
    assert activities_module._code_for_default(healed_on_env, environment_ctx) == saved
    # Default environment: code passes through untouched, including None.
    assert activities_module._code_for_run(saved, default_ctx) == saved
    assert activities_module._code_for_run(None, environment_ctx) is None
    assert activities_module._code_for_default(saved, default_ctx) == saved


def test_a_suite_run_records_its_suite_and_takes_the_suites_current_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _, _ = _seed()
    _Recorder(monkeypatch)
    with Session(engine) as session:
        suite = TestCollection(application_id=application.id, name="Smoke v2")
        session.add(suite)
        session.commit()
        session.refresh(suite)

    # The workflow was started under the old name; the suite has since been renamed.
    run = _prepare(
        application, suite_name="Smoke", test_collection_id=str(suite.external_id)
    )

    assert (run.test_collection_id, run.suite_name) == (suite.id, "Smoke v2")


def test_a_suite_deleted_before_prepare_falls_back_to_a_plain_named_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _, _ = _seed()
    _Recorder(monkeypatch)

    run = _prepare(application, suite_name="Smoke", test_collection_id=str(uuid.uuid4()))

    assert (run.test_collection_id, run.suite_name) == (None, "Smoke")


def test_a_run_without_a_suite_has_no_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _, _ = _seed()
    _Recorder(monkeypatch)

    run = _prepare(application, suite_name="Hand named")

    assert (run.test_collection_id, run.suite_name) == (None, "Hand named")
