"""Authoring (`/explorer/applications/{id}/author`): test cases from a user's
request, carried out by the existing Explorer on its own path
(explorer_worker.authoring). The run shows on the Explorer screen like any
Explorer run; it never touches the app's discovery record."""

import uuid

from domain import Journey
from explorer_core import (
    ACTIVE_RUN_STATUSES,
    AUTHORING_WORKFLOW_NAME,
    EXPLORER_TASK_QUEUE,
    ExplorerRun,
    explorer_workflow_id,
)
from explorer_core.limits import snapshot as limits_snapshot
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import col, func, select

from api.auth import CurrentOrgIdDep, CurrentUserDep
from api.explorer import RunRead, SessionDep, _owned_application, _to_read
from api.temporal_client import get_temporal_client, has_pollers

router = APIRouter(prefix="/explorer", tags=["authoring"])


class AuthorRequest(BaseModel):
    prompt: str
    # Where the test cases go: an existing Journey, or a new Journey by this
    # name. Neither (older clients): the request gets a Journey of its own.
    journey_id: uuid.UUID | None = None
    journey_name: str | None = None


@router.post("/applications/{application_id}/author", response_model=RunRead, status_code=201)
async def start_authoring(
    application_id: uuid.UUID,
    payload: AuthorRequest,
    session: SessionDep,
    org_id: CurrentOrgIdDep,
    user: CurrentUserDep,
) -> RunRead:
    application = _owned_application(session, application_id, org_id)
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="Describe the test cases you want")
    journey_name = (payload.journey_name or "").strip()[:200] or None
    if payload.journey_id is not None and journey_name is not None:
        raise HTTPException(
            status_code=422, detail="Select an existing journey or enter a new journey name."
        )
    journeys = select(Journey).where(Journey.application_id == application.id)
    if (
        payload.journey_id is not None
        and session.exec(journeys.where(Journey.external_id == payload.journey_id)).first() is None
    ):
        raise HTTPException(status_code=404, detail="JOURNEY_NOT_FOUND")
    if (
        journey_name is not None
        and session.exec(
            journeys.where(
                Journey.status == "candidate", func.lower(Journey.name) == journey_name.lower()
            )
        ).first()
    ):
        raise HTTPException(
            status_code=409,
            detail="A journey with this name already exists. Select it from the list instead.",
        )
    active = session.exec(
        select(ExplorerRun).where(
            ExplorerRun.application_id == application.id,
            col(ExplorerRun.status).in_(ACTIVE_RUN_STATUSES),
        )
    ).first()
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail="Explorer is already running for this application — wait for it to finish",
        )
    client = await get_temporal_client()
    if not await has_pollers(client, EXPLORER_TASK_QUEUE):
        raise HTTPException(status_code=503, detail="EXPLORER_UNAVAILABLE")
    run = ExplorerRun(
        application_id=application.id,
        prompt=prompt[:8000],
        started_by_id=user.id,
        # As of now, but each scenario is tried once and never replayed:
        # replays must not decide which test cases the user gets.
        limits={**limits_snapshot(session), "proof_replays": 0},
        insights=(
            {"journey": {"id": str(payload.journey_id)}}
            if payload.journey_id
            else {"journey": {"name": journey_name}}
            if journey_name
            else {}
        ),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    await client.start_workflow(
        AUTHORING_WORKFLOW_NAME,
        str(run.id),
        id=explorer_workflow_id(run.external_id),
        task_queue=EXPLORER_TASK_QUEUE,
    )
    return _to_read(session, run, application)
