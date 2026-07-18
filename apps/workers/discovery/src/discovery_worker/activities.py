"""DiscoveryActivity / ApplicationModelBuilderActivity / InferenceActivity —
the I/O boundary DiscoveryWorkflow dispatches to (AD-2).

Story 2.2 (reworked 2026-07-18): establish a session using the Application's
stored credentials (via `SecretsClient`), autonomously explore the entire
Application, and write each captured page/form/action/API call/transition
directly as a typed row (`Page`/`Form`/`FormField`/`ValidationRule`/`Action`/
`ApiEndpoint`/`PageTransition`) — there is no generic `Evidence` table.
Story 2.3 adds the `complete` transition; Story 2.4 adds the
`failed`/`session_expired` distinction (AD-11) and a catch-all for any other
crash. Story 2.5 adds `ApplicationModelBuilderActivity`: merges duplicate
typed captures into canonical rows and derives Component/ComponentLocator/
Assertion. Story 2.6 adds `InferenceActivity`: canonical Page rows ->
candidate Journey/Capability rows, plus starting `GenerationWorkflow` per
candidate (no approval gate, AD-1/AD-9).
"""

import uuid

from ai_provider.hosted import HostedAIProvider
from domain import (
    Action,
    ApiEndpoint,
    Application,
    Assertion,
    Capability,
    Component,
    DiscoveryRun,
    Form,
    FormField,
    Journey,
    Page,
    PageTransition,
    ValidationRule,
)
from playwright.async_api import async_playwright
from secrets_client.vault_client import SecretRef, VaultSecretsClient
from sqlmodel import Session, select
from temporalio import activity
from temporalio.exceptions import WorkflowAlreadyStartedError
from workflows import (
    GENERATION_TASK_QUEUE,
    ApplicationModelBuilderActivityInput,
    ApplicationModelBuilderActivityOutput,
    DiscoveryActivityInput,
    DiscoveryActivityOutput,
    GenerationWorkflow,
    InferenceActivityInput,
)

from discovery_worker.crawler import (
    CapturedAction,
    CapturedApiCall,
    CapturedForm,
    CapturedItem,
    CapturedPage,
    CapturedTransition,
    CrawlResult,
    run_discovery_crawl,
)
from discovery_worker.db import engine
from discovery_worker.identity_key import compute_identity_key
from discovery_worker.model_builder import build_application_model
from discovery_worker.object_store import ObjectStore
from discovery_worker.session import establish_session
from discovery_worker.temporal_client import get_temporal_client


@activity.defn(name="DiscoveryActivity")
async def discovery_activity(input: DiscoveryActivityInput) -> DiscoveryActivityOutput:
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(input.application_id))
        ).one()
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(input.discovery_run_id)
            )
        ).one()

        # Captured now, before any incremental commit below expires the ORM
        # object — rows are persisted as they're captured (`_persist`), not
        # batched to the end, so a crawl that outlives an Activity attempt
        # (a real site with no traversal cap, Story 2.3) never loses what it
        # already found, and the live feed (Story 2.2, AC 3) actually has
        # something to show while discovery is still running.
        discovery_run_pk = discovery_run.id
        application_pk = application.id

        page_ids_by_url: dict[str, uuid.UUID] = {}
        action_ids_by_key: dict[tuple[str, str], uuid.UUID] = {}
        page_count = 0

        def _persist(item: CapturedItem) -> None:
            nonlocal page_count
            if isinstance(item, CapturedPage):
                page = Page(
                    application_id=application_pk,
                    discovery_run_id=discovery_run_pk,
                    url=item.url,
                    title=item.title,
                    object_storage_key=item.object_storage_key,
                )
                session.add(page)
                session.commit()
                session.refresh(page)
                page_ids_by_url[item.url] = page.id
                page_count += 1
            elif isinstance(item, CapturedForm):
                page_id = page_ids_by_url.get(item.page_url)
                if page_id is None:
                    return
                form = Form(
                    application_id=application_pk,
                    discovery_run_id=discovery_run_pk,
                    page_id=page_id,
                    action_url=item.action_url,
                    method=item.method,
                )
                session.add(form)
                session.commit()
                session.refresh(form)
                for captured_field in item.fields:
                    field_row = FormField(
                        form_id=form.id,
                        name=captured_field.name,
                        input_type=captured_field.input_type,
                        required=captured_field.required,
                        default_value=captured_field.default_value,
                        captured_selector=captured_field.captured_selector,
                    )
                    session.add(field_row)
                    session.commit()
                    session.refresh(field_row)
                    if captured_field.required:
                        session.add(
                            ValidationRule(form_field_id=field_row.id, rule_type="required")
                        )
                session.commit()
            elif isinstance(item, CapturedAction):
                page_id = page_ids_by_url.get(item.page_url)
                if page_id is None:
                    return
                action_row = Action(
                    application_id=application_pk,
                    discovery_run_id=discovery_run_pk,
                    page_id=page_id,
                    description=item.description,
                    captured_selector=item.captured_selector,
                    representative=item.representative,
                )
                session.add(action_row)
                session.commit()
                session.refresh(action_row)
                action_ids_by_key[(item.page_url, item.description)] = action_row.id
            elif isinstance(item, CapturedApiCall):
                page_id = page_ids_by_url.get(item.page_url)
                if page_id is None:
                    return
                session.add(
                    ApiEndpoint(
                        application_id=application_pk,
                        discovery_run_id=discovery_run_pk,
                        page_id=page_id,
                        method=item.method,
                        path=item.path,
                        status_code=item.status_code,
                        response_summary=item.response_summary,
                    )
                )
                session.commit()
            elif isinstance(item, CapturedTransition):
                from_id = page_ids_by_url.get(item.from_url)
                to_id = page_ids_by_url.get(item.to_url)
                if from_id is None or to_id is None:
                    return
                triggered_by_action_id = None
                if item.triggered_by_description:
                    triggered_by_action_id = action_ids_by_key.get(
                        (item.from_url, item.triggered_by_description)
                    )
                session.add(
                    PageTransition(
                        application_id=application_pk,
                        discovery_run_id=discovery_run_pk,
                        from_page_id=from_id,
                        to_page_id=to_id,
                        triggered_by_action_id=triggered_by_action_id,
                    )
                )
                session.commit()

        try:
            credential = VaultSecretsClient().resolve(SecretRef(path=input.secret_ref))
            object_store = ObjectStore()

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                context = await establish_session(
                    browser,
                    auth_method=application.auth_method,
                    credential=credential,
                    base_url=application.url,
                )
                result = await run_discovery_crawl(
                    context,
                    application.url,
                    object_store,
                    discovery_run.id,
                    on_capture=_persist,
                    # `activity.heartbeat()` raises outside a real Temporal
                    # activity execution context — only true in production,
                    # not when this function is called directly (as the
                    # integration tests do).
                    heartbeat=activity.heartbeat if activity.in_activity() else None,
                )
                await context.close()
                await browser.close()
        except Exception:
            # A genuine crash, unrelated to session expiry (AD-11 is the
            # distinct, expected case above) — this story doesn't build a
            # full error-handling framework, only ensures the run doesn't
            # stay stuck showing `running` forever. Whatever was captured
            # before the crash is already committed via `_persist` above —
            # this empty result only affects the return value below.
            result = CrawlResult()
            discovery_run.status = "failed"
        else:
            if result.session_expired:
                # This must stay a distinct code path from `complete` below —
                # AD-11 exists specifically so a session-expired run never
                # silently lands in `complete`.
                discovery_run.status = "failed"
                discovery_run.failure_reason = "session_expired"
            else:
                # Story 2.3, AD-10: exhaustive traversal is the only stop
                # condition this story implements, and this is the one and
                # only place `complete` gets written.
                discovery_run.status = "complete"

        session.add(discovery_run)
        session.commit()

        return DiscoveryActivityOutput(status=discovery_run.status, page_count=page_count)


@activity.defn(name="ApplicationModelBuilderActivity")
async def application_model_builder_activity(
    input: ApplicationModelBuilderActivityInput,
) -> ApplicationModelBuilderActivityOutput:
    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(input.discovery_run_id)
            )
        ).one()
        application = session.get(Application, discovery_run.application_id)
        assert application is not None

        component_count = build_application_model(session, application.id)
        return ApplicationModelBuilderActivityOutput(component_count=component_count)


def _get_or_create_capability(session: Session, application_id: uuid.UUID, name: str) -> Capability:
    existing = session.exec(
        select(Capability).where(
            Capability.application_id == application_id, Capability.name == name
        )
    ).first()
    if existing is not None:
        return existing
    capability = Capability(application_id=application_id, name=name)
    session.add(capability)
    session.flush()
    return capability


@activity.defn(name="InferenceActivity")
async def inference_activity(input: InferenceActivityInput) -> list[str]:
    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(input.discovery_run_id)
            )
        ).one()
        application = session.get(Application, discovery_run.application_id)
        assert application is not None

        # Canonical rows only (merged_into_id IS NULL) — never a superseded
        # row (AD-14).
        pages = list(
            session.exec(
                select(Page).where(
                    Page.application_id == application.id, Page.merged_into_id.is_(None)  # type: ignore[union-attr]
                )
            ).all()
        )
        forms = list(
            session.exec(
                select(Form).where(
                    Form.application_id == application.id, Form.merged_into_id.is_(None)  # type: ignore[union-attr]
                )
            ).all()
        )
        api_endpoints = list(
            session.exec(
                select(ApiEndpoint).where(
                    ApiEndpoint.application_id == application.id,
                    ApiEndpoint.merged_into_id.is_(None),  # type: ignore[union-attr]
                )
            ).all()
        )
        components = list(
            session.exec(select(Component).where(Component.application_id == application.id)).all()
        )
        # PageTransition has no `merged_into_id` of its own (deduped in place
        # by 2.5's ApplicationModelBuilderActivity) but its `from_page_id`/
        # `to_page_id` can still point at a since-superseded Page row, so
        # resolving through every Page (not just canonical ones) is needed to
        # find the transition's actual canonical endpoint.
        all_pages_by_id = {
            p.id: p
            for p in session.exec(
                select(Page).where(Page.application_id == application.id)
            ).all()
        }

        def _canonical_page_id(page_id: uuid.UUID) -> uuid.UUID:
            row = all_pages_by_id.get(page_id)
            return (row.merged_into_id or row.id) if row else page_id

        transitions = list(
            session.exec(
                select(PageTransition).where(PageTransition.application_id == application.id)
            ).all()
        )
        assertions = list(
            session.exec(select(Assertion).where(Assertion.application_id == application.id)).all()
        )

        forms_by_page: dict[uuid.UUID, list[Form]] = {}
        for form in forms:
            forms_by_page.setdefault(form.page_id, []).append(form)
        api_by_page: dict[uuid.UUID, list[ApiEndpoint]] = {}
        for endpoint in api_endpoints:
            api_by_page.setdefault(endpoint.page_id, []).append(endpoint)
        components_by_page: dict[uuid.UUID, list[Component]] = {}
        for component in components:
            components_by_page.setdefault(component.page_id, []).append(component)
        transitions_by_page: dict[uuid.UUID, list[Page]] = {}
        for transition in transitions:
            canonical_from = _canonical_page_id(transition.from_page_id)
            canonical_to = all_pages_by_id.get(_canonical_page_id(transition.to_page_id))
            if canonical_to is not None:
                transitions_by_page.setdefault(canonical_from, []).append(canonical_to)
        assertions_by_page: dict[uuid.UUID, list[Assertion]] = {}
        for assertion in assertions:
            assertions_by_page.setdefault(assertion.page_id, []).append(assertion)

        for page in pages:
            # Transient attributes (not mapped columns) so HostedAIProvider
            # gets the full canonical picture per page, not just a bare URL.
            # SQLModel/Pydantic rejects `page.forms = ...` outright (no such
            # declared field) — `object.__setattr__` bypasses that check to
            # attach plain, non-persisted instance data.
            object.__setattr__(page, "forms", forms_by_page.get(page.id, []))
            object.__setattr__(page, "api_endpoints", api_by_page.get(page.id, []))
            object.__setattr__(page, "components", components_by_page.get(page.id, []))
            object.__setattr__(page, "outgoing_transitions", transitions_by_page.get(page.id, []))
            object.__setattr__(page, "assertions", assertions_by_page.get(page.id, []))

        candidates = HostedAIProvider().infer_journeys(pages)

        pages_by_id = {page.id: page for page in pages}
        journey_external_ids: list[str] = []
        temporal_client = await get_temporal_client()

        for candidate in candidates:
            supporting_pages = [
                pages_by_id[page_id]
                for pid in candidate.page_ids
                if (page_id := uuid.UUID(pid)) in pages_by_id
            ]
            supporting_page_ids = {page.id for page in supporting_pages}
            supporting_forms = [f for f in forms if f.page_id in supporting_page_ids]
            supporting_api_endpoints = [
                e for e in api_endpoints if e.page_id in supporting_page_ids
            ]
            supporting_components = [c for c in components if c.page_id in supporting_page_ids]

            identity_key = compute_identity_key(
                supporting_pages, supporting_components, supporting_api_endpoints
            )

            # AD-13/AD-9: a retry that finds a matching identity_key already
            # on this Application skips re-creating the Journey row.
            existing_journey = session.exec(
                select(Journey)
                .join(DiscoveryRun, Journey.discovery_run_id == DiscoveryRun.id)  # type: ignore[arg-type]
                .where(
                    DiscoveryRun.application_id == application.id,
                    Journey.identity_key == identity_key,
                )
            ).first()

            if existing_journey is not None:
                journey = existing_journey
            else:
                capability = _get_or_create_capability(
                    session, application.id, candidate.capability_name
                )
                journey = Journey(
                    discovery_run_id=discovery_run.id,
                    capability_id=capability.id,
                    name=candidate.name,
                    identity_key=identity_key,
                )
                session.add(journey)
                session.flush()

            for page in supporting_pages:
                page.journey_id = journey.id
                session.add(page)
            for form in supporting_forms:
                form.journey_id = journey.id
                session.add(form)
            for endpoint in supporting_api_endpoints:
                endpoint.journey_id = journey.id
                session.add(endpoint)
            for component in supporting_components:
                component.journey_id = journey.id
                session.add(component)
            session.commit()

            journey_external_ids.append(str(journey.external_id))

            # AD-1/AD-9: no approval gate — start GenerationWorkflow
            # immediately, whether the Journey was just created or found from
            # a prior attempt. Temporal's duplicate-workflow-ID rejection
            # makes this naturally idempotent on retry.
            try:
                await temporal_client.start_workflow(
                    GenerationWorkflow.run,
                    id=f"generation-{journey.external_id}-1",
                    task_queue=GENERATION_TASK_QUEUE,
                )
            except WorkflowAlreadyStartedError:
                pass

        return journey_external_ids
