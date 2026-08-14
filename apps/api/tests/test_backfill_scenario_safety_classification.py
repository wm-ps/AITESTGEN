"""backfill_scenario_safety_classification — Postgres only."""

import uuid

import pytest
from api.db import engine, init_db
from api.scripts.backfill_scenario_safety_classification import backfill
from domain import Application, DiscoveryRun, Journey, Organization, Scenario
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


def _seed_scenario(steps: list[str], *, safety_classification_reason: str | None = None) -> Scenario:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        application = Application(
            organization_id=org.id,
            name="Backfill Test App",
            url="https://app.example.com",
            environment="staging",
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
            name="Backfill Journey",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()

        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name="Backfill Scenario",
            steps=steps,
            generation_run_id=journey.attempt,
            # Simulates a migration-defaulted pre-existing row: classification
            # defaults to UNKNOWN with no reason set, unless a test wants to
            # simulate an already-classified row.
            safety_classification_reason=safety_classification_reason,
        )
        session.add(scenario)
        session.commit()
        session.refresh(scenario)
        return scenario


def test_backfill_classifies_rows_with_no_reason_set() -> None:
    init_db()
    scenario = _seed_scenario(["Delete the order"])

    updated = backfill()

    assert updated >= 1
    with Session(engine) as session:
        refreshed = session.exec(select(Scenario).where(Scenario.id == scenario.id)).one()
    assert refreshed.safety_classification == "DESTRUCTIVE"
    assert refreshed.safety_classification_reason is not None


def test_backfill_never_reclassifies_a_row_that_already_has_a_reason() -> None:
    init_db()
    scenario = _seed_scenario(
        ["Delete the order"],
        safety_classification_reason="already classified by generation",
    )
    with Session(engine) as session:
        stored = session.exec(select(Scenario).where(Scenario.id == scenario.id)).one()
        stored.safety_classification = "SAFE"  # deliberately "wrong", to prove it's untouched
        session.add(stored)
        session.commit()

    backfill()

    with Session(engine) as session:
        refreshed = session.exec(select(Scenario).where(Scenario.id == scenario.id)).one()
    assert refreshed.safety_classification == "SAFE"
    assert refreshed.safety_classification_reason == "already classified by generation"


def test_backfill_is_idempotent() -> None:
    init_db()
    _seed_scenario(["View the order"])

    first_count = backfill()
    second_count = backfill()

    assert first_count >= 1
    assert second_count == 0
