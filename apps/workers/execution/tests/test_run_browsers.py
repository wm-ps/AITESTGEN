"""A run executes against a list of browsers and one window size. Prepare
records both on the run, creates one TestResult per test per browser (reference
browser first, so its heals land before the others run), and installs only the
engines the run needs. A run that names neither is exactly what it was:
Chromium at 1280x720.

Postgres only; the assembler, `npm install` and the sign-in are stubbed through
test_run_environment's helpers.
"""

import uuid

import execution_worker.activities as activities_module
import pytest
from domain import Schedule, TestResult, TestRun
from execution_worker.db import engine
from sqlmodel import Session, select
from test_run_environment import _db_available, _prepare, _Recorder, _seed
from workflows import PrepareTestRunActivityInput

pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)


def _results(run: TestRun) -> list[TestResult]:
    with Session(engine) as session:
        return list(session.exec(select(TestResult).where(TestResult.test_run_id == run.id)).all())


def test_a_run_naming_no_browser_is_chromium_at_1280x720(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _, _ = _seed()
    _Recorder(monkeypatch)

    run = _prepare(application)

    assert (run.browsers, run.viewport_width, run.viewport_height) == (["chromium"], 1280, 720)
    assert [r.browser for r in _results(run)] == ["chromium"]
    assert run.total_count == 1


def test_a_multi_browser_run_gets_one_result_per_test_per_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _, asset = _seed()
    _Recorder(monkeypatch)
    installed: list[list[str]] = []
    monkeypatch.setattr(
        activities_module, "_install_project", lambda dest_dir, browsers=("chromium",): installed.append(list(browsers))
    )

    result = activities_module._prepare_test_run_sync(
        PrepareTestRunActivityInput(
            application_id=str(application.external_id),
            browsers=["webkit", "chromium"],
            viewport_width=1920,
            viewport_height=1080,
        )
    )

    with Session(engine) as session:
        run = session.exec(
            select(TestRun).where(TestRun.external_id == uuid.UUID(result.test_run_id))
        ).one()
    assert run.browsers == ["chromium", "webkit"]  # reference browser first
    assert (run.viewport_width, run.viewport_height) == (1920, 1080)
    assert run.total_count == 1  # one test; its two browsers are two results
    assert sorted(r.browser for r in _results(run)) == ["chromium", "webkit"]
    # The workflow runs one wave per browser in the order seen.
    assert [(t.browser, t.test_asset_id) for t in result.executable] == [
        ("chromium", str(asset.external_id)),
        ("webkit", str(asset.external_id)),
    ]
    assert installed == [["chromium", "webkit"]]


def test_a_scheduled_run_takes_its_schedules_browsers_and_window_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _, _ = _seed()
    _Recorder(monkeypatch)
    with Session(engine) as session:
        schedule = Schedule(
            application_id=application.id,
            name="Cross-browser nightly",
            cadence_type="daily",
            hour=2,
            minute=0,
            time_zone="UTC",
            temporal_schedule_id=f"app-schedule-{uuid.uuid4()}",
            browsers=["firefox"],
            viewport_width=1366,
            viewport_height=768,
        )
        session.add(schedule)
        session.commit()
        session.refresh(schedule)

    run = _prepare(application, schedule_id=str(schedule.external_id))

    assert (run.browsers, run.viewport_width, run.viewport_height) == (["firefox"], 1366, 768)
    assert [r.browser for r in _results(run)] == ["firefox"]


def test_a_schedule_without_a_browser_choice_keeps_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _, _ = _seed()
    _Recorder(monkeypatch)
    with Session(engine) as session:
        schedule = Schedule(
            application_id=application.id,
            name="Old nightly",
            cadence_type="daily",
            hour=2,
            minute=0,
            time_zone="UTC",
            temporal_schedule_id=f"app-schedule-{uuid.uuid4()}",
        )
        session.add(schedule)
        session.commit()
        session.refresh(schedule)

    run = _prepare(application, schedule_id=str(schedule.external_id))

    assert (run.browsers, run.viewport_width, run.viewport_height) == (["chromium"], 1280, 720)


def test_a_request_browser_choice_wins_over_the_schedules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _, _ = _seed()
    _Recorder(monkeypatch)
    with Session(engine) as session:
        schedule = Schedule(
            application_id=application.id,
            name="Webkit nightly",
            cadence_type="daily",
            hour=2,
            minute=0,
            time_zone="UTC",
            temporal_schedule_id=f"app-schedule-{uuid.uuid4()}",
            browsers=["webkit"],
            viewport_width=1366,
            viewport_height=768,
        )
        session.add(schedule)
        session.commit()
        session.refresh(schedule)

    run = _prepare(
        application,
        schedule_id=str(schedule.external_id),
        browsers=["firefox"],
        viewport_width=1920,
        viewport_height=1080,
    )

    assert (run.browsers, run.viewport_width, run.viewport_height) == (["firefox"], 1920, 1080)
