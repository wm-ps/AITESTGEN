"""DiscoveryError entity (Story 2.18 Task 1) — real Postgres, same
skip-cleanly convention as test_diagnostics.py.
"""

import uuid

import pytest
from discovery_worker.db import engine, init_db
from domain import Application, DiscoveryError, DiscoveryRun, Organization
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select


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


def _seed_discovery_run() -> tuple[uuid.UUID, uuid.UUID]:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Discovery Error Test App",
            url="https://example.test",
            environment="test",
            secret_ref="unused",
        )
        session.add(application)
        session.flush()
        run = DiscoveryRun(application_id=application.id)
        session.add(run)
        session.commit()
        return application.id, run.id


def test_discovery_error_round_trips_code_message_and_retry_count() -> None:
    init_db()
    application_id, run_id = _seed_discovery_run()

    with Session(engine) as session:
        session.add(
            DiscoveryError(
                application_id=application_id,
                discovery_run_id=run_id,
                error_code="DISC-003",
                message="Target application unresponsive after 3 attempts.",
                retry_count=3,
            )
        )
        session.commit()

    with Session(engine) as session:
        rows = session.exec(
            select(DiscoveryError).where(DiscoveryError.discovery_run_id == run_id)
        ).all()

    assert len(rows) == 1
    assert rows[0].error_code == "DISC-003"
    assert rows[0].retry_count == 3
    assert rows[0].page_id is None
