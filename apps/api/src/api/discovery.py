"""Discovery Run start-up (Story 2.1).

Not an independently user-triggered endpoint — Story 1.3's Connect App
submission is a single atomic Application creation with no separate
draft/ready status, so this is a function that onboarding calls directly in
the same request, not a route of its own.
"""

from domain import Application, DiscoveryRun
from sqlmodel import Session
from workflows import DISCOVERY_TASK_QUEUE, DiscoveryWorkflow

from api.temporal_client import get_temporal_client


async def start_discovery_run(session: Session, application: Application) -> DiscoveryRun:
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
        args=[str(discovery_run.external_id), str(application.external_id), application.secret_ref],
        id=f"discovery-{discovery_run.external_id}",
        task_queue=DISCOVERY_TASK_QUEUE,
    )
    return discovery_run
