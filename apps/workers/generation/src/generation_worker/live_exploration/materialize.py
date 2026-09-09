"""Persists a finished LiveFlowModel into fresh, isolated DB rows — the one
place this feature writes into the tables the crawler also writes into. Never
reads an existing `Page`/`Component`/`DiscoveryRun` row; only ever creates new
ones, scoped to a brand-new `DiscoveryRun(source="live_exploration")`, then
reuses the existing, idempotent `build_application_model` to derive
`Component`/`ComponentLocator` from them exactly as the crawler's own output
would be derived.
"""

import uuid
from dataclasses import dataclass

from discovery_worker.model_builder import build_application_model
from domain import Action, DiscoveryRun, Form, FormField, Page, PageTransition
from sqlmodel import Session

from generation_worker.db import engine
from generation_worker.live_exploration.live_flow import FIELD_ROLES, LiveFlowModel


@dataclass
class MaterializeResult:
    discovery_run_id: uuid.UUID
    pages: list[Page]  # in visited order — LiveExploreActivity's own JourneyStep source
    # Same order as `pages`, but each id is post-merge: `build_application_model`
    # (called below) may fold a freshly-created Page into a pre-existing one
    # sharing the same URL, and Components/ComponentLocators attach to that
    # canonical id, never the pre-merge one. `[FIXED]` — observed live: a
    # JourneyStep built from the pre-merge `pages` ids found zero locators
    # for a URL Discovery already knew about, even though the real one was
    # captured and stored correctly just now. Callers building JourneyStep
    # rows (the only thing `known_locators` queries by page id) must use
    # these, not `pages`' own ids.
    canonical_page_ids: list[uuid.UUID]


def materialize_live_flow_sync(
    application_id: uuid.UUID, live_flow: LiveFlowModel
) -> MaterializeResult:
    with Session(engine, expire_on_commit=False) as session:
        discovery_run = DiscoveryRun(
            application_id=application_id,
            status="complete",
            source="live_exploration",
        )
        session.add(discovery_run)
        session.commit()
        session.refresh(discovery_run)

        page_by_url: dict[str, Page] = {}
        ordered_pages: list[Page] = []
        for url, heading in live_flow.ordered_pages():
            page = Page(
                application_id=application_id,
                discovery_run_id=discovery_run.id,
                url=url,
                heading=heading,
                title=heading or "",
            )
            session.add(page)
            page_by_url[url] = page
            ordered_pages.append(page)
        session.commit()
        for page in ordered_pages:
            session.refresh(page)

        # Element-targeting steps become Action rows on the page they acted
        # on; build_application_model groups them into Components by
        # (page_id, description), so `description` must be a stable label
        # per distinct element, not the per-turn rationale.
        action_id_by_step_index: dict[int, uuid.UUID] = {}
        captured_selectors_by_page: dict[uuid.UUID, set[str]] = {}
        prev_captured_description: str | None = None
        prev_captured_page_url: str | None = None
        for index, step in enumerate(live_flow.steps):
            if step.locator_candidate is None or step.page_url is None:
                # A non-captured turn in between (e.g. `browser_wait_for`)
                # doesn't break the causal chain — deliberately not reset
                # here; the page_url equality check below already prevents
                # a false link once the page genuinely changes.
                continue
            page = page_by_url.get(step.page_url)
            if page is None:
                continue
            base_description = step.tool_args.get("element") or step.locator_candidate.get(
                "value", f"element in step {index}"
            )
            # `[FIXED]` A dropdown/menu/accordion option is often a custom
            # widget with no real "reveal" state captured anywhere — the
            # option simply wasn't interactable until the immediately
            # preceding captured step (its trigger) ran. Without this,
            # PlaywrightGenerationActivity's known_locators listed both as
            # unrelated, always-available elements, and generated code tried
            # the option's locator directly — failing exactly the way this
            # was observed live (getByRole('option', ...) not visible; the
            # code never opened the parent Server type combobox first).
            # Grounded in the agent's own recorded action order, not a guess
            # about DOM nesting (which a portal-rendered popup wouldn't
            # reflect anyway).
            if (
                prev_captured_description is not None
                and prev_captured_page_url == step.page_url
                and prev_captured_description != base_description
            ):
                description = (
                    f'{base_description} (revealed after clicking "{prev_captured_description}")'
                )
            else:
                description = base_description
            prev_captured_description = base_description
            prev_captured_page_url = step.page_url
            action = Action(
                application_id=application_id,
                discovery_run_id=discovery_run.id,
                page_id=page.id,
                description=description,
                captured_selector=step.locator_candidate.get("value"),
                locator_candidates=[
                    {
                        "strategy": step.locator_candidate["strategy"],
                        "value": step.locator_candidate["value"],
                        "fragile": step.locator_candidate["fragile"],
                    }
                ],
            )
            session.add(action)
            session.commit()
            session.refresh(action)
            action_id_by_step_index[index] = action.id
            captured_selectors_by_page.setdefault(page.id, set()).add(
                step.locator_candidate["value"]
            )

        # Full per-page element inventory (see `LiveFlowModel.page_elements`)
        # — everything the ARIA snapshot exposed for a page, not just what an
        # actual step acted on. Field-shaped roles become Form/FormField rows
        # (the same shape a crawled page's own form gets, so
        # spec_linter's required-field/input-type grounding works
        # identically); everything else becomes an Action row, skipped when
        # a step above already captured the exact same element.
        for url, elements in live_flow.page_elements.items():
            page = page_by_url.get(url)
            if page is None or not elements:
                continue
            already_captured = captured_selectors_by_page.get(page.id, set())

            field_elements = [e for e in elements if e["element_tag"] in FIELD_ROLES]
            if field_elements:
                form = Form(
                    application_id=application_id,
                    discovery_run_id=discovery_run.id,
                    page_id=page.id,
                    action_url=url,
                    method="POST",
                )
                session.add(form)
                session.commit()
                session.refresh(form)
                for element in field_elements:
                    name = element["name"].strip()
                    session.add(
                        FormField(
                            form_id=form.id,
                            name=name or None,
                            input_type=element["element_tag"],
                            # A leading "*" on the accessible name is this
                            # app's own required-field convention (observed
                            # live: "* Server type", "* Endpoint URL") — the
                            # only required-ness signal a live snapshot
                            # actually exposes without triggering real HTML5
                            # validation, which this pass doesn't attempt.
                            required=name.startswith("*"),
                            captured_selector=element["value"],
                            locator_candidates=[
                                {
                                    "strategy": element["strategy"],
                                    "value": element["value"],
                                    "fragile": element["fragile"],
                                }
                            ],
                        )
                    )

            for element in elements:
                if element["element_tag"] in FIELD_ROLES:
                    continue
                if element["value"] in already_captured:
                    continue
                session.add(
                    Action(
                        application_id=application_id,
                        discovery_run_id=discovery_run.id,
                        page_id=page.id,
                        description=element["name"] or element["value"],
                        captured_selector=element["value"],
                        locator_candidates=[
                            {
                                "strategy": element["strategy"],
                                "value": element["value"],
                                "fragile": element["fragile"],
                            }
                        ],
                    )
                )
        session.commit()

        # Consecutive distinct pages in visit order become PageTransition
        # edges; the transition is attributed to the immediately preceding
        # step's Action when that step produced one (a `browser_navigate`
        # jump has no Action to attribute to, and that's fine —
        # `triggered_by_action_id` is nullable for exactly this case).
        prev_page: Page | None = None
        prev_action_id: uuid.UUID | None = None
        last_seen_url: str | None = None
        for index, step in enumerate(live_flow.steps):
            if step.page_url is None:
                continue
            if step.page_url != last_seen_url:
                page = page_by_url[step.page_url]
                if prev_page is not None and prev_page.id != page.id:
                    session.add(
                        PageTransition(
                            application_id=application_id,
                            discovery_run_id=discovery_run.id,
                            from_page_id=prev_page.id,
                            to_page_id=page.id,
                            triggered_by_action_id=prev_action_id,
                        )
                    )
                prev_page = page
                last_seen_url = step.page_url
            prev_action_id = action_id_by_step_index.get(index)
        session.commit()

    with Session(engine) as session:
        _, page_resolution = build_application_model(session, application_id)

    canonical_page_ids = [page_resolution.get(page.id, page.id) for page in ordered_pages]
    return MaterializeResult(
        discovery_run_id=discovery_run.id, pages=ordered_pages, canonical_page_ids=canonical_page_ids
    )
