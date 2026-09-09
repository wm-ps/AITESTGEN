"""`_create_live_journey_sync` — Postgres only. Builds exactly one Journey +
ordered JourneySteps directly from the materialized live-flow pages, no AI
call, no `infer_journeys` clustering. Folded directly into `LiveExploreActivity`
(no separate LiveJourneyGenerationActivity step) — this test exercises the
same sync helper `live_explore_activity` calls internally."""

import uuid

import pytest
from domain import Application, DiscoveryRun, Journey, JourneyStep, Organization, Page
from generation_worker.db import engine, init_db
from generation_worker.live_exploration_activities import _create_live_journey_sync
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


pytestmark = [
    pytest.mark.skipif(
        not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
    ),
]

_created_org_ids: list[uuid.UUID] = []


@pytest.fixture(autouse=True)
def _cleanup_created_organizations():
    _created_org_ids.clear()
    yield
    with Session(engine) as session:
        for organization_id in _created_org_ids:
            app_ids = [
                a.id
                for a in session.exec(
                    select(Application).where(Application.organization_id == organization_id)
                ).all()
            ]
            if app_ids:
                journey_ids = [
                    j.id
                    for j in session.exec(
                        select(Journey).where(Journey.application_id.in_(app_ids))
                    ).all()
                ]
                if journey_ids:
                    session.exec(
                        text("DELETE FROM journey_step WHERE journey_id = ANY(:journey_ids)"),
                        params={"journey_ids": journey_ids},
                    )
                    session.exec(
                        text("DELETE FROM journey WHERE id = ANY(:journey_ids)"),
                        params={"journey_ids": journey_ids},
                    )
                run_ids = [
                    r.id
                    for r in session.exec(
                        select(DiscoveryRun).where(DiscoveryRun.application_id.in_(app_ids))
                    ).all()
                ]
                session.exec(
                    text("DELETE FROM page WHERE application_id = ANY(:app_ids)"),
                    params={"app_ids": app_ids},
                )
                if run_ids:
                    session.exec(
                        text("DELETE FROM discovery_run WHERE id = ANY(:run_ids)"),
                        params={"run_ids": run_ids},
                    )
                session.exec(
                    text("DELETE FROM application WHERE id = ANY(:app_ids)"),
                    params={"app_ids": app_ids},
                )
            session.exec(
                text("DELETE FROM organization WHERE id = :oid"), params={"oid": organization_id}
            )
        session.commit()
    _created_org_ids.clear()


def _seed_application_with_pages() -> tuple[Application, DiscoveryRun, list[Page]]:
    init_db()
    with Session(engine) as session:
        org = Organization(name=f"Live Journey Test Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        _created_org_ids.append(org.id)

        application = Application(
            organization_id=org.id,
            name="Live Journey Test App",
            url="https://app.example.com",
            environment="test",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.flush()

        discovery_run = DiscoveryRun(
            application_id=application.id, status="complete", source="live_exploration"
        )
        session.add(discovery_run)
        session.flush()

        pages = [
            Page(
                application_id=application.id,
                discovery_run_id=discovery_run.id,
                url="https://app.example.com/tenants",
                heading="Tenants",
            ),
            Page(
                application_id=application.id,
                discovery_run_id=discovery_run.id,
                url="https://app.example.com/tenants/mcp",
                heading="MCP Connections",
            ),
        ]
        session.add_all(pages)
        session.commit()
        for page in pages:
            session.refresh(page)
        session.refresh(application)
        session.refresh(discovery_run)
        return application, discovery_run, pages


def test_creates_one_journey_with_ordered_steps() -> None:
    application, discovery_run, pages = _seed_application_with_pages()

    journey_id, _ = _create_live_journey_sync(
        application_id=application.id,
        discovery_run_id=discovery_run.id,
        page_ids=[p.id for p in pages],
        requirement="Create a new MCP connection for a tenant.",
        functionality_summary="",
        captured_flow=[],
    )

    with Session(engine) as session:
        journey = session.exec(
            select(Journey).where(Journey.external_id == uuid.UUID(journey_id))
        ).one()
        assert journey.discovery_run_id == discovery_run.id
        steps = session.exec(
            select(JourneyStep)
            .where(JourneyStep.journey_id == journey.id)
            .order_by(JourneyStep.step_order)  # type: ignore[arg-type]
        ).all()
        assert [s.stage_label for s in steps] == ["Tenants", "MCP Connections"]
        assert [s.page_id for s in steps] == [p.id for p in pages]


def test_names_the_journey_from_functionality_summary_not_the_raw_prompt() -> None:
    application, discovery_run, pages = _seed_application_with_pages()

    _, journey_name = _create_live_journey_sync(
        application_id=application.id,
        discovery_run_id=discovery_run.id,
        page_ids=[p.id for p in pages],
        requirement=(
            "Write happy-path, negative-path, and edge-case test cases for the following "
            "scenario on the Tenants page: create a new MCP connection."
        ),
        functionality_summary="Create a new MCP connection for a tenant",
        captured_flow=[],
    )

    assert journey_name == "Create a new MCP connection for a tenant"


def test_is_idempotent_on_retry_with_the_same_pages() -> None:
    application, discovery_run, pages = _seed_application_with_pages()
    kwargs = dict(
        application_id=application.id,
        discovery_run_id=discovery_run.id,
        page_ids=[p.id for p in pages],
        requirement="Create a new MCP connection for a tenant.",
        functionality_summary="",
        captured_flow=[],
    )

    first_id, _ = _create_live_journey_sync(**kwargs)
    second_id, _ = _create_live_journey_sync(**kwargs)

    assert first_id == second_id


def test_persists_the_captured_flow_transcript() -> None:
    application, discovery_run, pages = _seed_application_with_pages()
    captured_flow = [
        {
            "tool_name": "browser_click",
            "element_description": "settings icon for the first tenant",
            "typed_value": None,
            "page_url": "https://app.example.com/tenants",
            "page_heading": "Tenants",
            "rationale": "open the mcp-connections page for the first tenant",
        }
    ]

    journey_id, _ = _create_live_journey_sync(
        application_id=application.id,
        discovery_run_id=discovery_run.id,
        page_ids=[p.id for p in pages],
        requirement="Create a new MCP connection for a tenant.",
        functionality_summary="",
        captured_flow=captured_flow,
    )

    with Session(engine) as session:
        journey = session.exec(
            select(Journey).where(Journey.external_id == uuid.UUID(journey_id))
        ).one()
        assert journey.captured_flow == captured_flow
