"""DiscoveryActivity / InferenceActivity — the I/O boundary DiscoveryWorkflow
dispatches to (AD-2).

Story 2.1 proved the dispatch path only. Story 2.2 replaces that stub with
real behavior: establish a session using the Application's stored
credentials (via `SecretsClient`), autonomously explore the entire
Application, and write each captured page/action/form/API call as an
`Evidence` row tagged with `discovery_run_id` (never `journey_id` —
`InferenceActivity`, Story 2.5, is the sole writer of that column). Story 2.3
adds the `complete` transition; Story 2.4 adds the `failed`/`session_expired`
distinction (AD-11) and a catch-all for any other crash. Story 2.5 adds
`InferenceActivity`: raw Evidence -> candidate Journey/Capability rows, plus
starting `GenerationWorkflow` per candidate (no approval gate, AD-1/AD-9).
"""

import uuid

from ai_provider.hosted import HostedAIProvider
from domain import Application, Capability, DiscoveryRun, Evidence, Journey
from playwright.async_api import async_playwright
from secrets_client.vault_client import SecretRef, VaultSecretsClient
from sqlmodel import Session, select
from temporalio import activity
from temporalio.exceptions import WorkflowAlreadyStartedError
from workflows import (
    GENERATION_TASK_QUEUE,
    DiscoveryActivityInput,
    DiscoveryActivityOutput,
    GenerationWorkflow,
    InferenceActivityInput,
)

from discovery_worker.crawler import CrawlResult, run_discovery_crawl
from discovery_worker.db import engine
from discovery_worker.identity_key import compute_identity_key
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
        # object — Evidence is persisted as it's captured (`_persist`), not
        # batched to the end, so a crawl that outlives an Activity attempt
        # (a real site with no traversal cap, Story 2.3) never loses what it
        # already found, and the live feed (Story 2.2, AC 3) actually has
        # something to show while discovery is still running.
        discovery_run_pk = discovery_run.id

        def _persist(item) -> None:
            session.add(
                Evidence(
                    discovery_run_id=discovery_run_pk,
                    type=item.type,
                    details=item.details,
                    object_storage_key=item.object_storage_key,
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
                    on_evidence=_persist,
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

        return DiscoveryActivityOutput(
            status=discovery_run.status, evidence_count=len(result.evidence)
        )


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

        evidence_rows = list(
            session.exec(
                select(Evidence).where(Evidence.discovery_run_id == discovery_run.id)
            ).all()
        )

        candidates = HostedAIProvider().infer_journeys(evidence_rows)

        journey_external_ids: list[str] = []
        temporal_client = await get_temporal_client()

        for candidate in candidates:
            supporting_evidence = [
                row
                for row in evidence_rows
                if str(row.external_id) in candidate.evidence_external_ids
            ]
            identity_key = compute_identity_key(supporting_evidence)

            # AD-13/AD-9: a retry that finds a matching identity_key already on
            # this Application skips re-creating the Journey row.
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

            for row in supporting_evidence:
                row.journey_id = journey.id
                session.add(row)
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
