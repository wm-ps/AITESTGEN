"""materialize_live_flow_sync — Postgres only. Writes a fresh, isolated
DiscoveryRun/Page/Action/PageTransition set and confirms build_application_model
derives Components from it, without touching any pre-existing DiscoveryRun."""

import uuid

import pytest
from domain import Action, Application, Component, DiscoveryRun, Form, FormField, Organization, Page
from generation_worker.db import engine, init_db
from generation_worker.live_exploration.live_flow import LiveFlowModel, LiveFlowStep
from generation_worker.live_exploration.materialize import materialize_live_flow_sync
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
                run_ids = [
                    r.id
                    for r in session.exec(
                        select(DiscoveryRun).where(DiscoveryRun.application_id.in_(app_ids))
                    ).all()
                ]
                session.exec(
                    text(
                        "DELETE FROM component_locator WHERE component_id IN "
                        "(SELECT id FROM component WHERE application_id = ANY(:app_ids))"
                    ),
                    params={"app_ids": app_ids},
                )
                session.exec(
                    text(
                        "DELETE FROM form_field WHERE form_id IN "
                        "(SELECT id FROM form WHERE application_id = ANY(:app_ids))"
                    ),
                    params={"app_ids": app_ids},
                )
                for table in (
                    "assertion",
                    "component",
                    "page_transition",
                    "action",
                    "form",
                    "page",
                ):
                    session.exec(
                        text(f"DELETE FROM {table} WHERE application_id = ANY(:app_ids)"),
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
                text("DELETE FROM organization WHERE id = :org_id"),
                params={"org_id": organization_id},
            )
        session.commit()
    _created_org_ids.clear()


def _seed_application() -> Application:
    init_db()
    with Session(engine) as session:
        org = Organization(name=f"Live Exploration Test Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        _created_org_ids.append(org.id)

        application = Application(
            organization_id=org.id,
            name="Live Exploration Test App",
            url="https://app.example.com",
            environment="test",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.commit()
        session.refresh(application)
        return application


def test_materialize_creates_a_live_exploration_discovery_run() -> None:
    application = _seed_application()
    live_flow = LiveFlowModel(
        requirement="Create a new MCP connection for a tenant.",
        steps=[
            LiveFlowStep(
                "browser_navigate", {"url": "https://app.example.com/tenants"}, "open tenants",
                page_url="https://app.example.com/tenants", page_heading="Tenants",
            ),
            LiveFlowStep(
                "browser_click", {"element": "Settings", "ref": "e1"}, "open settings",
                page_url="https://app.example.com/tenants", page_heading="Tenants",
                locator_candidate={
                    "strategy": "role", "value": 'get_by_role("button", name="Settings")',
                    "fragile": False, "element_tag": "button",
                },
            ),
            LiveFlowStep(
                "browser_click", {"element": "Create connection", "ref": "e9"}, "create connection",
                page_url="https://app.example.com/tenants/mcp", page_heading="MCP Connections",
                locator_candidate={
                    "strategy": "role", "value": 'get_by_role("button", name="Create connection")',
                    "fragile": False, "element_tag": "button",
                },
            ),
        ],
        goal_satisfied=True,
    )

    result = materialize_live_flow_sync(application.id, live_flow)

    with Session(engine) as session:
        discovery_run = session.get(DiscoveryRun, result.discovery_run_id)
        assert discovery_run is not None
        assert discovery_run.source == "live_exploration"

        pages = session.exec(
            select(Page).where(Page.discovery_run_id == result.discovery_run_id)
        ).all()
        assert {p.url for p in pages} == {
            "https://app.example.com/tenants",
            "https://app.example.com/tenants/mcp",
        }
        assert [p.url for p in result.pages] == [
            "https://app.example.com/tenants",
            "https://app.example.com/tenants/mcp",
        ]

        components = session.exec(
            select(Component).where(Component.application_id == application.id)
        ).all()
        component_names = {c.name for c in components}
        assert "Settings" in component_names
        assert "Create connection" in component_names

        # No pre-existing Page shares this run's URLs, so nothing merges —
        # canonical ids are just each page's own id.
        assert result.canonical_page_ids == [p.id for p in result.pages]


def test_materialize_tags_an_option_revealed_by_a_same_page_prior_click() -> None:
    """A custom-widget dropdown option (e.g. a styled div, role="generic")
    is often only interactable after its trigger (a combobox) is clicked —
    with no other capturable signal that this dependency exists. Without
    this tag, PlaywrightGenerationActivity's known_locators list both as
    unrelated, always-available elements and generated code tries the
    option directly, failing exactly the way this was observed live."""
    application = _seed_application()
    live_flow = LiveFlowModel(
        requirement="Add a Git MCP connection.",
        steps=[
            LiveFlowStep(
                "browser_navigate", {"url": "https://app.example.com/mcp"}, "open mcp page",
                page_url="https://app.example.com/mcp", page_heading="MCP Connections",
            ),
            LiveFlowStep(
                "browser_click", {"element": "Server type combobox", "ref": "e1"}, "open dropdown",
                page_url="https://app.example.com/mcp", page_heading="MCP Connections",
                locator_candidate={
                    "strategy": "role", "value": 'get_by_role("combobox", name="Server type")',
                    "fragile": False, "element_tag": "combobox",
                },
            ),
            LiveFlowStep(
                "browser_click", {"element": "GIT option", "ref": "e2"}, "select GIT",
                page_url="https://app.example.com/mcp", page_heading="MCP Connections",
                locator_candidate={
                    "strategy": "role", "value": 'get_by_role("generic", name="GIT")',
                    "fragile": False, "element_tag": "generic",
                },
            ),
        ],
        goal_satisfied=True,
    )

    materialize_live_flow_sync(application.id, live_flow)

    with Session(engine) as session:
        actions = session.exec(
            select(Action).where(Action.application_id == application.id)
        ).all()
        descriptions = {a.description for a in actions}
        assert "Server type combobox" in descriptions
        assert 'GIT option (revealed after clicking "Server type combobox")' in descriptions


def test_materialize_persists_the_full_page_sweep_not_just_acted_on_elements() -> None:
    """`[FIXED]` regression: a live-exploration Page used to only ever know
    about elements the agent's own steps happened to click/type on — a real
    dialog's OTHER fields/buttons were invisible to known_locators/
    required-field grounding entirely, unlike a crawled page's full Form/
    FormField scan. `LiveFlowModel.page_elements` (the full ARIA-snapshot
    sweep) must now also reach Form/FormField (for field-shaped roles) and
    Action (for the rest), for the whole page — not just what a step
    interacted with."""
    application = _seed_application()
    live_flow = LiveFlowModel(
        requirement="Add a GIT MCP connection.",
        steps=[
            LiveFlowStep(
                "browser_click", {"element": "Add connection", "ref": "e1"}, "open dialog",
                page_url="https://app.example.com/mcp", page_heading="MCP Connections",
                locator_candidate={
                    "strategy": "role", "value": 'get_by_role("button", name="Add connection")',
                    "fragile": False, "element_tag": "button",
                },
            ),
        ],
        goal_satisfied=True,
        page_elements={
            "https://app.example.com/mcp": [
                # Already captured via the step above — must not be
                # duplicated into a second Action row.
                {
                    "strategy": "role", "value": 'get_by_role("button", name="Add connection")',
                    "fragile": False, "element_tag": "button", "name": "Add connection",
                },
                # Never acted on by any step — only the full sweep finds it.
                {
                    "strategy": "role", "value": 'get_by_role("textbox", name="* Endpoint URL")',
                    "fragile": False, "element_tag": "textbox", "name": "* Endpoint URL",
                },
                {
                    "strategy": "role", "value": 'get_by_role("textbox", name="Notes (optional)")',
                    "fragile": False, "element_tag": "textbox", "name": "Notes (optional)",
                },
                {
                    "strategy": "role", "value": 'get_by_role("button", name="Cancel")',
                    "fragile": False, "element_tag": "button", "name": "Cancel",
                },
            ]
        },
    )

    materialize_live_flow_sync(application.id, live_flow)

    with Session(engine) as session:
        forms = session.exec(select(Form).where(Form.application_id == application.id)).all()
        assert len(forms) == 1
        fields = session.exec(select(FormField).where(FormField.form_id == forms[0].id)).all()
        by_name = {f.name: f for f in fields}
        assert by_name.keys() == {"* Endpoint URL", "Notes (optional)"}
        assert by_name["* Endpoint URL"].required is True
        assert by_name["* Endpoint URL"].input_type == "textbox"
        assert by_name["Notes (optional)"].required is False

        actions = session.exec(select(Action).where(Action.application_id == application.id)).all()
        descriptions = [a.description for a in actions]
        # "Add connection" appears exactly once — the step's own Action, not
        # duplicated by the sweep finding the same element again.
        assert descriptions.count("Add connection") == 1
        assert "Cancel" in descriptions

        components = session.exec(
            select(Component).where(Component.application_id == application.id)
        ).all()
        component_names = {c.name for c in components}
        # The untouched field/button are now real, locator-bearing
        # Components — exactly what a crawled page's own scan would give.
        assert "* Endpoint URL" in component_names
        assert "Cancel" in component_names


def test_canonical_page_ids_point_wherever_a_merged_page_s_components_actually_are() -> None:
    """`[FIXED]` regression: `build_application_model` (reused from the
    crawler pipeline) folds a freshly-created Page into a pre-existing one
    sharing the same URL — Components/ComponentLocators attach to that
    canonical page, never the pre-merge one. A JourneyStep built from
    `result.pages`' own (pre-merge) ids would find zero Components for a URL
    Discovery already knew about, even though the real locator was captured
    and stored correctly. `canonical_page_ids` must point at wherever the
    Components actually ended up."""
    application = _seed_application()
    with Session(engine) as session:
        pre_existing_run = DiscoveryRun(
            application_id=application.id, status="complete", source="crawler"
        )
        session.add(pre_existing_run)
        session.flush()
        pre_existing_page = Page(
            application_id=application.id,
            discovery_run_id=pre_existing_run.id,
            url="https://app.example.com/tenants",
            heading="Tenants",
        )
        session.add(pre_existing_page)
        session.commit()
        session.refresh(pre_existing_page)
        pre_existing_page_id = pre_existing_page.id

    live_flow = LiveFlowModel(
        requirement="Open settings for the first tenant.",
        steps=[
            LiveFlowStep(
                "browser_click", {"element": "Settings", "ref": "e1"}, "open settings",
                page_url="https://app.example.com/tenants", page_heading="Tenants",
                locator_candidate={
                    "strategy": "role", "value": 'get_by_role("link", name="Settings")',
                    "fragile": False, "element_tag": "link",
                },
            ),
        ],
        goal_satisfied=True,
    )

    result = materialize_live_flow_sync(application.id, live_flow)

    assert result.pages[0].id != pre_existing_page_id  # a fresh Page row was still created
    assert result.canonical_page_ids == [pre_existing_page_id]  # but merged into the pre-existing one

    with Session(engine) as session:
        components = session.exec(
            select(Component).where(Component.page_id == pre_existing_page_id)
        ).all()
        assert {c.name for c in components} == {"Settings"}
