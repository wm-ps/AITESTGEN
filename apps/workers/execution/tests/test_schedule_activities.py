"""CheckScheduleGateActivity (Schedules feature) — Postgres only, direct
calls to the sync activity function (no Temporal needed for these cases).

Application-soft-delete defense-in-depth (§9.10 of the design review): this
test calls the gate directly against a soft-deleted Application with no
Temporal involved at all — proving the gate blocks purely from its own DB
check, independent of whether `delete_application`'s best-effort Temporal
pause succeeded. There is nothing to mock here for that guarantee to hold;
the gate never talks to Temporal in the first place.
"""

import uuid
from datetime import UTC, datetime

import pytest
from domain import Application, Organization, Schedule, TestRun
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from execution_worker.db import engine, init_db
from execution_worker.schedule_activities import check_schedule_gate_activity
from workflows import ScheduleGateActivityInput


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


def _seed_application(*, deleted_at: datetime | None = None) -> Application:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Schedule Gate Test App",
            url="https://app.example.com",
            environment="staging",
            auth_method="standard_login",
            secret_ref=f"applications/{org.id}/{uuid.uuid4()}",
            deleted_at=deleted_at,
        )
        session.add(application)
        session.commit()
        session.refresh(application)
        return application


def _seed_schedule(application: Application, *, deleted_at: datetime | None = None) -> Schedule:
    with Session(engine) as session:
        schedule = Schedule(
            application_id=application.id,
            name="Nightly Regression",
            cadence_type="daily",
            hour=2,
            minute=0,
            time_zone="UTC",
            temporal_schedule_id=f"app-schedule-{uuid.uuid4()}",
            deleted_at=deleted_at,
        )
        session.add(schedule)
        session.commit()
        session.refresh(schedule)
        return schedule


def test_proceeds_when_application_active_schedule_active_and_no_run_in_progress() -> None:
    init_db()
    application = _seed_application()
    schedule = _seed_schedule(application)

    result = check_schedule_gate_activity(
        ScheduleGateActivityInput(
            application_id=str(application.external_id), schedule_id=str(schedule.external_id)
        )
    )

    assert result.proceed is True
    assert result.reason is None


def test_blocks_when_application_is_missing() -> None:
    init_db()
    application = _seed_application()
    schedule = _seed_schedule(application)

    result = check_schedule_gate_activity(
        ScheduleGateActivityInput(application_id=str(uuid.uuid4()), schedule_id=str(schedule.external_id))
    )

    assert result.proceed is False
    assert result.reason == "application_unavailable"


def test_blocks_when_application_is_soft_deleted() -> None:
    """The defense-in-depth guarantee (§9.10): this is a pure DB check with
    no Temporal call involved, so it blocks regardless of whether
    `delete_application`'s own best-effort Temporal pause succeeded."""
    init_db()
    application = _seed_application(deleted_at=datetime.now(UTC))
    schedule = _seed_schedule(application)

    result = check_schedule_gate_activity(
        ScheduleGateActivityInput(
            application_id=str(application.external_id), schedule_id=str(schedule.external_id)
        )
    )

    assert result.proceed is False
    assert result.reason == "application_unavailable"


def test_blocks_when_schedule_is_missing() -> None:
    init_db()
    application = _seed_application()

    result = check_schedule_gate_activity(
        ScheduleGateActivityInput(
            application_id=str(application.external_id), schedule_id=str(uuid.uuid4())
        )
    )

    assert result.proceed is False
    assert result.reason == "schedule_unavailable"


def test_blocks_when_schedule_is_soft_deleted() -> None:
    init_db()
    application = _seed_application()
    schedule = _seed_schedule(application, deleted_at=datetime.now(UTC))

    result = check_schedule_gate_activity(
        ScheduleGateActivityInput(
            application_id=str(application.external_id), schedule_id=str(schedule.external_id)
        )
    )

    assert result.proceed is False
    assert result.reason == "schedule_unavailable"


def test_blocks_when_a_run_is_already_in_progress() -> None:
    init_db()
    application = _seed_application()
    schedule = _seed_schedule(application)
    with Session(engine) as session:
        session.add(
            TestRun(
                application_id=application.id,
                run_number=1,
                status="running",
                environment_snapshot="staging",
                target_base_url_snapshot="https://app.example.com",
            )
        )
        session.commit()

    result = check_schedule_gate_activity(
        ScheduleGateActivityInput(
            application_id=str(application.external_id), schedule_id=str(schedule.external_id)
        )
    )

    assert result.proceed is False
    assert result.reason == "execution_in_progress"


def test_proceeds_when_a_run_is_completed_not_in_progress() -> None:
    init_db()
    application = _seed_application()
    schedule = _seed_schedule(application)
    with Session(engine) as session:
        session.add(
            TestRun(
                application_id=application.id,
                run_number=1,
                status="completed",
                environment_snapshot="staging",
                target_base_url_snapshot="https://app.example.com",
            )
        )
        session.commit()

    result = check_schedule_gate_activity(
        ScheduleGateActivityInput(
            application_id=str(application.external_id), schedule_id=str(schedule.external_id)
        )
    )

    assert result.proceed is True
