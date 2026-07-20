"""Journey invariants (Story 2.5/2.6, AD-8/AD-9/AD-13):
- `discovery_run_id` immutability, enforced via a SQLAlchemy `@validates`
  check that fires once the row is persistent.
- `UNIQUE(application_id, identity_key)`, enforced at the database level —
  this is what makes `InferenceActivity`'s find-or-create race-safe under
  concurrent/overlapping runs, not just a select-then-create convention.
"""

import os
import uuid

import pytest
from domain import Application, DiscoveryRun, Journey, Organization
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, SQLModel

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


def test_journey_discovery_run_id_cannot_change_after_creation() -> None:
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        application = Application(
            organization_id=org.id,
            name="Immutability Test App",
            url="https://app.example.com",
            environment="test",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.flush()

        run_a = DiscoveryRun(application_id=application.id, status="complete")
        run_b = DiscoveryRun(application_id=application.id, status="complete")
        session.add(run_a)
        session.add(run_b)
        session.flush()

        journey = Journey(
            application_id=application.id,
            discovery_run_id=run_a.id,
            name="Checkout",
            identity_key="fixed-key-for-this-test",
        )
        session.add(journey)
        session.commit()

        with pytest.raises(ValueError, match="immutable"):
            journey.discovery_run_id = run_b.id


def test_journey_identity_key_is_unique_per_application_at_the_database_level() -> None:
    """Proves the DB constraint itself prevents the duplicate — not just an
    application-level select-then-create check, which would be a TOCTOU race
    under two concurrent/overlapping InferenceActivity runs (AD-9)."""
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        application = Application(
            organization_id=org.id,
            name="Uniqueness Test App",
            url="https://app.example.com",
            environment="test",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.flush()

        run_a = DiscoveryRun(application_id=application.id, status="complete")
        session.add(run_a)
        session.flush()

        session.add(
            Journey(
                application_id=application.id,
                discovery_run_id=run_a.id,
                name="Checkout",
                identity_key="shared-identity-key",
            )
        )
        session.commit()

        # A second Journey row for the same Application with the same
        # identity_key — as a concurrent InferenceActivity run racing to
        # create the same candidate would attempt — must be rejected by the
        # database itself.
        session.add(
            Journey(
                application_id=application.id,
                discovery_run_id=run_a.id,
                name="Checkout (different AI-generated name)",
                identity_key="shared-identity-key",
            )
        )
        with pytest.raises(IntegrityError, match="uq_journey_application_id_identity_key"):
            session.commit()
