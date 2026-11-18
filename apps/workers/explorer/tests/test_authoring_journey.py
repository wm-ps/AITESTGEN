"""Authored test cases go to the journey the user chose when starting: an
existing one (its own scenarios untouched) or a new one by name."""

import uuid
from typing import Any

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


async def test_tests_that_couldnt_be_carried_out_are_replaced_up_to_the_number_asked(
    monkeypatch: Any,
) -> None:
    from explorer_core import ExplorerEvent, ExplorerScreen
    from explorer_worker.authoring import plan

    app_id, _, _ = _app_with_journey()
    with Session(engine) as session:
        run = ExplorerRun(
            application_id=app_id,
            status="testing",
            prompt="write 3 test cases for the territory list",
            brief={"request": {"flow": "territory list", "scenarios": [], "count": 3}},
        )
        session.add(run)
        session.flush()
        session.add(
            ExplorerScreen(
                run_id=run.id,
                signature="s",
                name="Territories",
                view_kind="list",
                url="https://staging.example.com/t",
                url_pattern="/t",
                aria='- button "Export"\n- textbox "Search"',
            )
        )
        for title, status in (("main", "proven"), ("x", "dropped"), ("y", "dropped")):
            session.add(
                ExplorerTestCase(
                    run_id=run.id,
                    kind="data_load",
                    title=title,
                    purpose="",
                    steps=[],
                    expected="e",
                    trust="confirmed",
                    script=[{"how_to_run": ""}],
                    status=status,
                    drop_reason="Couldn't carry it out" if status == "dropped" else None,
                )
            )
        session.commit()
        run_id = run.id
    asked: list[str] = []

    async def plan_tests(*a: Any, **k: Any) -> list[dict[str, Any]]:
        asked.append(a[5])
        return [
            {
                "kind": "data_load",
                "title": f"r{len(asked)}-{i}",
                "expected": "e",
                "start_screen": "Territories",
                "path": [{"screen": "Territories", "element": 'button "Export"'}],
            }
            for i in range(2)
        ]

    monkeypatch.setattr(plan.brain, "plan_tests", plan_tests)
    assert await plan.refill(run_id) == 2  # 1 delivered of 3: two replacements
    assert "exactly 2" in asked[0] and "x — Couldn't carry it out" in asked[0]

    def statuses() -> dict[str, str]:
        with Session(engine) as session:
            rows = session.exec(select(ExplorerTestCase).where(ExplorerTestCase.run_id == run_id))
            return {t.title: t.status for t in rows}

    assert statuses()["r1-0"] == "planned" and statuses()["r1-1"] == "planned"
    with Session(engine) as session:  # one replacement works, one can't be carried out
        for t in session.exec(select(ExplorerTestCase).where(ExplorerTestCase.run_id == run_id)):
            if t.title.startswith("r1"):
                t.status = "proven" if t.title == "r1-0" else "dropped"
                session.add(t)
        session.commit()
    assert await plan.refill(run_id) == 1  # second round: the last one missing
    with Session(engine) as session:
        for t in session.exec(select(ExplorerTestCase).where(ExplorerTestCase.run_id == run_id)):
            if t.status == "planned":
                t.status = "dropped"
                session.add(t)
        session.commit()
    assert await plan.refill(run_id) == 0  # rounds used up: said plainly
    with Session(engine) as session:
        said = session.exec(
            select(ExplorerEvent).where(
                ExplorerEvent.run_id == run_id, ExplorerEvent.kind == "summary"
            )
        ).one()
    assert said.title == "2 of the 3 test cases you asked for"
