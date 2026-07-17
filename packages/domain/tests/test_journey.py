"""Journey.discovery_run_id immutability (Story 2.5, AD-8) — enforced, not
just documented, via a SQLAlchemy `@validates` check that fires once the
row is persistent.
"""

import os
import uuid

import pytest
from domain import Application, DiscoveryRun, Journey, Organization
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
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
            discovery_run_id=run_a.id,
            name="Checkout",
            identity_key="fixed-key-for-this-test",
        )
        session.add(journey)
        session.commit()

        with pytest.raises(ValueError, match="immutable"):
            journey.discovery_run_id = run_b.id
