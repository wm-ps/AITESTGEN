"""Authored test cases go to the journey the user chose when starting: an
existing one (its own scenarios untouched) or a new one by name."""

import uuid

from domain import Application, DiscoveryRun, Journey, Organization, Scenario
from explorer_core import ExplorerRun, ExplorerTestCase
from explorer_worker.authoring import promote
from explorer_worker.db import engine
from sqlmodel import Session, select


def _app_with_journey() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        app = Application(
            organization_id=org.id,
            name="Denali",
            url="https://staging.example.com",
            environment="staging",
            secret_ref="",
        )
        session.add(app)
        session.flush()
        crawl = DiscoveryRun(application_id=app.id, status="complete", source="crawler")
        session.add(crawl)
        session.flush()
        journey = Journey(
            application_id=app.id,
            discovery_run_id=crawl.id,
            name="Create territory",
            identity_key=f"test:{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()
        session.add(
            Scenario(
                journey_id=journey.id, type="happy", name="Theirs", steps=[], generation_run_id=1
            )
        )
        session.commit()
        return app.id, journey.id, journey.external_id


def _authored_run(app_id: uuid.UUID, choice: dict[str, str]) -> uuid.UUID:
    with Session(engine) as session:
        run = ExplorerRun(
            application_id=app_id,
            prompt="write test cases for territories",
            insights={"journey": choice},
        )
        session.add(run)
        session.flush()
        session.add(
            ExplorerTestCase(
                run_id=run.id,
                kind="validation",
                title="Territory Name is required",
                purpose="",
                steps=["Leave Territory Name empty"],
                expected="Territory Name is required.",
                trust="confirmed",
                script=[{"how_to_run": ""}],
                status="proven",
            )
        )
        # Never carried out in the app: no test case for it.
        session.add(
            ExplorerTestCase(
                run_id=run.id,
                kind="happy",
                title="Export downloads the list",
                purpose="",
                steps=["Press Export"],
                expected="A file downloads.",
                trust="confirmed",
                script=[{"how_to_run": ""}],
                status="dropped",
            )
        )
        session.commit()
        return run.id


def _names(journey_id: uuid.UUID) -> list[str]:
    with Session(engine) as session:
        rows = session.exec(
            select(Scenario).where(Scenario.journey_id == journey_id, Scenario.current == True)  # noqa: E712
        ).all()
        return sorted(s.name for s in rows)


def test_an_existing_journey_gets_the_test_cases_and_keeps_its_own() -> None:
    app_id, journey_id, external = _app_with_journey()
    run_id = _authored_run(app_id, {"id": str(external)})
    assert promote._promote(run_id) == [str(external)]
    assert _names(journey_id) == ["Territory Name is required", "Theirs"]
    # Sent again: this request's copy is replaced, the journey's own stays.
    assert promote._promote(run_id) == [str(external)]
    assert _names(journey_id) == ["Territory Name is required", "Theirs"]


def test_a_new_journey_takes_the_name_given() -> None:
    app_id, _, _ = _app_with_journey()
    run_id = _authored_run(app_id, {"name": "Territory rules"})
    [external] = promote._promote(run_id)
    with Session(engine) as session:
        journey = session.exec(
            select(Journey).where(Journey.external_id == uuid.UUID(external))
        ).one()
        assert journey.name == "Territory rules"
        assert _names(journey.id) == ["Territory Name is required"]
