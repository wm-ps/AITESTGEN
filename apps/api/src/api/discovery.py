"""Discovery Run start-up (Story 2.1) and pause/resume (Story 2.17).

`start_discovery_run` is not an independently user-triggered endpoint —
Story 1.3's Connect App submission is a single atomic Application creation
with no separate draft/ready status, so this is a function that onboarding
calls directly in the same request, not a route of its own. `pause_discovery_run`/
`resume_discovery_run` *are* user-triggered (via `main.py`'s
`/applications/{id}/pause-discovery`/`resume-discovery` endpoints).
"""

import logging

from domain import Application, DiscoveryRun
from sqlmodel import Session
from workflows import DISCOVERY_TASK_QUEUE, DiscoveryWorkflow

from api.temporal_client import get_temporal_client

logger = logging.getLogger(__name__)


async def start_discovery_run(
    session: Session, application: Application, *, resume: bool = False
) -> DiscoveryRun:
    discovery_run = DiscoveryRun(
        application_id=application.id, status="running", stage="initializing"
    )
    session.add(discovery_run)
    session.commit()
    session.refresh(application)
    session.refresh(discovery_run)

    client = await get_temporal_client()
    await client.start_workflow(
        DiscoveryWorkflow.run,
        args=[
            str(discovery_run.external_id),
            str(application.external_id),
            application.secret_ref,
            resume,
        ],
        id=f"discovery-{discovery_run.external_id}",
        task_queue=DISCOVERY_TASK_QUEUE,
    )
    return discovery_run


async def pause_discovery_run(session: Session, discovery_run: DiscoveryRun) -> DiscoveryRun:
    """Story 2.17 Task 1 (AC 1): `status="paused"` — no other table is
    touched, everything resume needs (the confirmed Application Model, open
    `BlockedTask`s, typed-row capture progress) is already durable via
    Stories 2.2/2.10/2.15's own real-time writes (AD-22). The DB write is
    what actually matters for durability; cancelling the underlying
    Temporal workflow (best-effort) stops the in-flight crawl from later
    overwriting `paused` with its own terminal `complete`/`failed` write —
    a cancelled Activity raises `CancelledError` (not caught by
    `discovery_activity`'s `except Exception`), so that write never
    happens."""
    discovery_run.status = "paused"
    session.add(discovery_run)
    session.commit()
    session.refresh(discovery_run)

    try:
        client = await get_temporal_client()
        await client.get_workflow_handle(f"discovery-{discovery_run.external_id}").cancel()
    except Exception:
        logger.exception(
            "pause_discovery_run: could not cancel the underlying workflow for "
            "discovery_run=%s — status is already durable regardless",
            discovery_run.external_id,
        )
    return discovery_run


async def resume_discovery_run(session: Session, application: Application) -> DiscoveryRun:
    """Story 2.17 Task 2 (AC 2/3): resuming is starting a fresh
    `DiscoveryRun` the normal way (Story 2.1's `start_discovery_run`) — a
    fresh browser session is always established regardless (Story 2.2's
    `establish_session` never assumes a prior session survived), and
    `discovery_activity`'s canonical-Page seeding (extended by this story to
    skip already-confirmed states entirely, not merely avoid re-persisting
    them — see `activities.py`'s `_seed_resume_frontier`) is what actually
    satisfies "does not re-explore any already-canonical state". No second
    orchestration path, no new persistence mechanism — every read/write
    involved is already scoped by `application_id` (AD-22). `resume=True` is
    what actually tells `discovery_activity` to skip already-confirmed
    states rather than re-crawl and reclassify them (Story 2.10's normal
    fresh-run behaviour is otherwise unchanged for a plain new run)."""
    return await start_discovery_run(session, application, resume=True)
