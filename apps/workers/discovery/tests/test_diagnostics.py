"""record_diagnostic() sink (Story 2.22 Task 1) — real Postgres, same
skip-cleanly convention as test_discovery_activity_integration.py.
"""

import uuid

import pytest
from discovery_worker.db import engine, init_db
from discovery_worker.diagnostics import record_diagnostic
from domain import Application, DiagnosticRecord, DiscoveryRun, Organization
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


def _seed_discovery_run() -> uuid.UUID:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Diagnostics Test App",
            url="https://example.test",
            environment="test",
            secret_ref="unused",
        )
        session.add(application)
        session.flush()
        run = DiscoveryRun(application_id=application.id)
        session.add(run)
        session.commit()
        return run.id


def test_record_diagnostic_persists_kind_and_payload() -> None:
    init_db()
    run_id = _seed_discovery_run()

    with Session(engine) as session:
        record_diagnostic(
            session, run_id, "state_identity", {"score": 0.82, "verdict": "SAME"}
        )

    with Session(engine) as session:
        rows = session.exec(
            select(DiagnosticRecord).where(DiagnosticRecord.discovery_run_id == run_id)
        ).all()

    assert len(rows) == 1
    assert rows[0].kind == "state_identity"
    assert rows[0].payload == {"score": 0.82, "verdict": "SAME"}


def test_record_diagnostic_never_raises_on_bad_foreign_key() -> None:
    init_db()
    bogus_run_id = uuid.uuid7()

    with Session(engine) as session:
        # Violates the discovery_run_id foreign key — must be swallowed, not
        # propagated, so a diagnostics write can never take down the crawl.
        record_diagnostic(session, bogus_run_id, "safety", {"verdict": "DEFER"})
        session.rollback()
