"""TestSuite invariants (Story 4.2): `UNIQUE(journey_id, generation_run_id)`
is enforced at the database level — this is what makes
`EnsureTestSuiteActivity`'s insert-or-fetch race-safe under two concurrent
`PlaywrightGenerationActivity` calls for the same Journey, not just a
select-then-create convention.
"""

import os
import uuid

import pytest
from domain import Application, DiscoveryRun, Journey, Organization, TestSuite
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, SQLModel, select

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/aitestgen",
)
engine = create_engine(DATABASE_URL, echo=False)


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


def _seed_journey(session: Session) -> Journey:
    org = Organization(name=f"Org {uuid.uuid4()}")
    session.add(org)
    session.flush()

    application = Application(
        organization_id=org.id,
        name="Test Suite Uniqueness App",
        url="https://app.example.com",
        environment="test",
        auth_method="standard_login",
        secret_ref="applications/irrelevant/secret",
    )
    session.add(application)
    session.flush()

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
    session.commit()
    return journey


def test_test_suite_is_unique_per_journey_and_generation_run_id_at_the_database_level() -> None:
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        journey = _seed_journey(session)

        session.add(
            TestSuite(journey_id=journey.id, name="Checkout Test Suite", generation_run_id=1)
        )
        session.commit()

        # A second TestSuite for the same Journey/attempt — as a concurrent
        # PlaywrightGenerationActivity call for a different Scenario in the
        # same Journey would attempt — must be rejected by the database itself.
        session.add(
            TestSuite(journey_id=journey.id, name="Checkout Test Suite", generation_run_id=1)
        )
        with pytest.raises(
            IntegrityError, match="uq_test_suite_journey_id_generation_run_id"
        ):
            session.commit()


def test_test_suite_allows_a_new_row_for_a_later_attempt() -> None:
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        journey = _seed_journey(session)

        session.add(
            TestSuite(journey_id=journey.id, name="Checkout Test Suite", generation_run_id=1)
        )
        session.commit()

        # A later regeneration's attempt is a genuinely different row — no
        # constraint violation.
        session.add(
            TestSuite(journey_id=journey.id, name="Checkout Test Suite", generation_run_id=2)
        )
        session.commit()

        count = len(
            session.exec(select(TestSuite).where(TestSuite.journey_id == journey.id)).all()
        )
        assert count == 2
