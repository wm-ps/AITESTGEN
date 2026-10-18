"""Vantage Explorer API (`/explorer/...`) — standalone from the classic
discovery endpoints in main.py; mounted there with one include_router line.
See docs/vantage-explorer/PLAN.md."""

import base64
import html
import io
import json
import re
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Annotated, Any

from domain import Application, DiscoveryRun
from explorer_core import (
    ACTIVE_RUN_STATUSES,
    BRIEF_CONFIRMED_SIGNAL,
    EXPLORER_TASK_QUEUE,
    EXPLORER_WORKFLOW_NAME,
    ExplorerAccess,
    ExplorerEvent,
    ExplorerHealthIssue,
    ExplorerKnowledge,
    ExplorerMission,
    ExplorerQuestion,
    ExplorerRecording,
    ExplorerRole,
    ExplorerRun,
    ExplorerScreen,
    ExplorerShot,
    ExplorerTestCase,
    ExplorerTransition,
    explorer_workflow_id,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel
from secrets_client import SecretRef, VaultSecretsClient
from sqlalchemy import func
from sqlmodel import Session, col, select
from temporalio.client import WorkflowExecutionStatus
from temporalio.service import RPCError
from test_suite_assembler.assembler import (
    _ZipWriter,
    find_login_page_evidence,
    generic_login_evidence,
    write_project_scaffold,
)

from api.auth import CurrentOrgIdDep, CurrentUserDep
from api.db import get_session
from api.temporal_client import get_temporal_client, has_pollers

router = APIRouter(prefix="/explorer", tags=["explorer"])
SessionDep = Annotated[Session, Depends(get_session)]


class RunCounts(BaseModel):
    screens: int
    hidden_hints: int
    health_issues: int
    hidden_screens: int = 0
    possible_bugs: int = 0
    missions_total: int = 0
    missions_done: int = 0
    missions_running: int = 0
    tests_total: int = 0
    tests_proven: int = 0
    tests_known_bugs: int = 0
    tests_building: int = 0
    questions_open: int = 0


class RunRead(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    status: str
    headline: str
    health_score: int | None
    requirements_first: bool
    brief: dict[str, Any] | None
    brief_confirmed_at: datetime | None
    notes: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    counts: RunCounts


class EventRead(BaseModel):
    id: int
    kind: str
    title: str
    detail: str | None
    shot_id: uuid.UUID | None
    mission_id: uuid.UUID | None = None
    created_at: datetime


class ScreenRead(BaseModel):
    id: uuid.UUID
    name: str
    entity: str | None
    view_kind: str
    mode: str | None
    purpose: str | None
    url: str
    visits: int
    fields: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    hidden_hints: list[str]
    reached_by: str | None
    shot_id: uuid.UUID | None
    condition: str | None = None


class HealthIssueRead(BaseModel):
    id: uuid.UUID
    kind: str
    severity: str
    title: str
    detail: str | None
    url: str
    occurrences: int
    shot_id: uuid.UUID | None


class StartRunRequest(BaseModel):
    notes: str | None = None


class RecordingInfo(BaseModel):
    started_at: datetime
    duration_seconds: float


class MissionRead(BaseModel):
    id: uuid.UUID
    title: str
    goal: str
    kind: str
    why: str | None
    priority: int
    instructions: str | None
    condition: str | None
    expected: str | None
    status: str
    outcome: str | None
    matches_expected: bool | None
    steps: int
    new_screens: int
    added_by: str
    started_at: datetime | None
    finished_at: datetime | None
    recording: RecordingInfo | None


class AddMissionRequest(BaseModel):
    goal: str
    title: str | None = None


class MapEdge(BaseModel):
    from_id: uuid.UUID
    to_id: uuid.UUID
    action: str


class AppMapRead(BaseModel):
    screens: list[ScreenRead]
    edges: list[MapEdge]


def _owned_application(session: Session, external_id: uuid.UUID, org_id: uuid.UUID) -> Application:
    application = session.exec(
        select(Application).where(
            Application.external_id == external_id,
            Application.organization_id == org_id,
            Application.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    ).first()
    if application is None:
        raise HTTPException(status_code=404, detail="application not found")
    return application


def _owned_run(
    session: Session, external_id: uuid.UUID, org_id: uuid.UUID
) -> tuple[ExplorerRun, Application]:
    row = session.exec(
        select(ExplorerRun, Application)
        .join(Application, col(Application.id) == col(ExplorerRun.application_id))
        .where(ExplorerRun.external_id == external_id, Application.organization_id == org_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="explorer run not found")
    return row[0], row[1]


def _to_read(session: Session, run: ExplorerRun, application: Application) -> RunRead:
    screens = session.exec(
        select(ExplorerScreen.hidden_hints, ExplorerScreen.condition).where(
            ExplorerScreen.run_id == run.id
        )
    ).all()
    issue_kinds = session.exec(
        select(ExplorerHealthIssue.kind).where(ExplorerHealthIssue.run_id == run.id)
    ).all()
    mission_statuses = session.exec(
        select(ExplorerMission.status).where(ExplorerMission.run_id == run.id)
    ).all()
    test_statuses = session.exec(
        select(ExplorerTestCase.status).where(ExplorerTestCase.run_id == run.id)
    ).all()
    return RunRead(
        id=run.external_id,
        application_id=application.external_id,
        status=run.status,
        headline=run.headline,
        health_score=run.health_score,
        requirements_first=run.requirements_first,
        brief=run.brief,
        brief_confirmed_at=run.brief_confirmed_at,
        notes=run.notes,
        error=run.error,
        created_at=run.created_at,
        updated_at=run.updated_at,
        counts=RunCounts(
            screens=len(screens),
            hidden_hints=sum(len(hints) for hints, _ in screens),
            health_issues=len(issue_kinds),
            hidden_screens=sum(1 for _, condition in screens if condition),
            possible_bugs=sum(1 for kind in issue_kinds if kind == "looks_wrong"),
            missions_total=len(mission_statuses),
            missions_done=sum(1 for st in mission_statuses if st in ("done", "blocked", "failed")),
            missions_running=sum(1 for st in mission_statuses if st in ("running", "waiting")),
            questions_open=session.exec(
                select(func.count())
                .select_from(ExplorerQuestion)
                .where(ExplorerQuestion.run_id == run.id, ExplorerQuestion.status == "open")
            ).one(),
            tests_total=sum(1 for st in test_statuses if st != "dropped"),
            tests_proven=sum(1 for st in test_statuses if st == "proven"),
            tests_known_bugs=sum(1 for st in test_statuses if st == "known_bug"),
            tests_building=sum(1 for st in test_statuses if st in ("planned", "building")),
        ),
    )


@router.get("/applications/{application_id}/runs/latest", response_model=RunRead | None)
def latest_run(
    application_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep
) -> RunRead | None:
    application = _owned_application(session, application_id, org_id)
    run = session.exec(
        select(ExplorerRun)
        .where(ExplorerRun.application_id == application.id)
        .order_by(col(ExplorerRun.created_at).desc())
    ).first()
    return _to_read(session, run, application) if run else None


@router.post("/applications/{application_id}/runs", response_model=RunRead, status_code=201)
async def start_run(
    application_id: uuid.UUID,
    payload: StartRunRequest,
    session: SessionDep,
    org_id: CurrentOrgIdDep,
    user: CurrentUserDep,
) -> RunRead:
    application = _owned_application(session, application_id, org_id)
    run = await begin_run(session, application, payload.notes, started_by=user.id)
    return _to_read(session, run, application)


async def begin_run(
    session: Session,
    application: Application,
    notes: str | None,
    started_by: uuid.UUID | None = None,
) -> ExplorerRun:
    """Start an Explorer run (also what onboarding calls, now that Explorer is
    Vantage's discovery — PLAN.md Stage 8). The app's discovery record shows
    "running" until Explorer hands its results to Journeys."""
    active = session.exec(
        select(ExplorerRun).where(
            ExplorerRun.application_id == application.id,
            col(ExplorerRun.status).in_(ACTIVE_RUN_STATUSES),
        )
    ).first()
    if active is not None:
        raise HTTPException(
            status_code=409, detail="Explorer is already running for this application"
        )
    client = await get_temporal_client()
    if not await has_pollers(client, EXPLORER_TASK_QUEUE):
        raise HTTPException(status_code=503, detail="EXPLORER_UNAVAILABLE")
    run = ExplorerRun(
        application_id=application.id,
        notes=(notes or "").strip() or None,
        started_by_id=started_by,
    )
    session.add(run)
    # Notes (test data like a policy number) are remembered for later runs —
    # otherwise a run started without notes knows none of it.
    if (
        run.notes
        and not session.exec(
            select(ExplorerKnowledge.id).where(
                ExplorerKnowledge.application_id == application.id,
                ExplorerKnowledge.text == run.notes,
            )
        ).first()
    ):
        session.add(
            ExplorerKnowledge(
                application_id=application.id,
                kind="fact",
                text=run.notes[:4000],
                source="Run notes",
            )
        )
    discovery_run = session.exec(
        select(DiscoveryRun)
        .where(DiscoveryRun.application_id == application.id, DiscoveryRun.source == "crawler")
        .order_by(col(DiscoveryRun.created_at).desc())
    ).first()
    if discovery_run is None:
        discovery_run = DiscoveryRun(application_id=application.id)
    discovery_run.status, discovery_run.stage, discovery_run.failure_reason = (
        "running",
        "explorer",
        None,
    )
    session.add(discovery_run)
    session.commit()
    session.refresh(run)
    await client.start_workflow(
        EXPLORER_WORKFLOW_NAME,
        str(run.id),
        id=explorer_workflow_id(run.external_id),
        task_queue=EXPLORER_TASK_QUEUE,
    )
    return run


@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> RunRead:
    run, application = _owned_run(session, run_id, org_id)
    return _to_read(session, run, application)


@router.get("/runs/{run_id}/events", response_model=list[EventRead])
def list_events(
    run_id: uuid.UUID,
    session: SessionDep,
    org_id: CurrentOrgIdDep,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[EventRead]:
    run, _ = _owned_run(session, run_id, org_id)
    rows = session.exec(
        select(ExplorerEvent)
        .where(ExplorerEvent.run_id == run.id, col(ExplorerEvent.id) > after)
        .order_by(col(ExplorerEvent.id))
        .limit(limit)
    ).all()
    mission_ids = _mission_external_ids(session, run.id)
    return [
        EventRead(
            id=row.id or 0,
            kind=row.kind,
            title=row.title,
            detail=row.detail,
            shot_id=row.shot_id,
            mission_id=mission_ids.get(row.mission_id) if row.mission_id else None,
            created_at=row.created_at,
        )
        for row in rows
    ]


def _mission_external_ids(session: Session, run_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
    return {
        mid: ext
        for mid, ext in session.exec(
            select(ExplorerMission.id, ExplorerMission.external_id).where(
                ExplorerMission.run_id == run_id
            )
        ).all()
    }


@router.get("/runs/{run_id}/screens", response_model=list[ScreenRead])
def list_screens(
    run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep
) -> list[ScreenRead]:
    run, _ = _owned_run(session, run_id, org_id)
    rows = session.exec(
        select(ExplorerScreen)
        .where(ExplorerScreen.run_id == run.id)
        .order_by(col(ExplorerScreen.created_at))
    ).all()
    return [ScreenRead(**row.model_dump()) for row in rows]


@router.get("/runs/{run_id}/health", response_model=list[HealthIssueRead])
def list_health(
    run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep
) -> list[HealthIssueRead]:
    run, _ = _owned_run(session, run_id, org_id)
    rows = session.exec(
        select(ExplorerHealthIssue).where(ExplorerHealthIssue.run_id == run.id)
    ).all()
    rank = {"high": 0, "medium": 1, "low": 2}
    rows = sorted(rows, key=lambda r: (rank.get(r.severity, 3), -r.occurrences))
    return [HealthIssueRead(**row.model_dump()) for row in rows]


@router.get("/shots/{shot_id}")
def get_shot(shot_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> Response:
    row = session.exec(
        select(ExplorerShot.data)
        .join(ExplorerRun, col(ExplorerRun.id) == col(ExplorerShot.run_id))
        .join(Application, col(Application.id) == col(ExplorerRun.application_id))
        .where(ExplorerShot.id == shot_id, Application.organization_id == org_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="screenshot not found")
    # Immutable once written — let the browser cache it.
    return Response(
        row, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"}
    )


@router.put("/runs/{run_id}/brief", response_model=RunRead)
def update_brief(
    run_id: uuid.UUID, brief: dict[str, Any], session: SessionDep, org_id: CurrentOrgIdDep
) -> RunRead:
    run, application = _owned_run(session, run_id, org_id)
    if run.status != "awaiting_confirmation":
        raise HTTPException(
            status_code=409, detail="the App Summary can only be edited before it is confirmed"
        )
    run.brief = brief
    run.updated_at = datetime.now(UTC)
    session.add(run)
    session.commit()
    session.refresh(run)
    return _to_read(session, run, application)


@router.post("/runs/{run_id}/confirm", response_model=RunRead)
async def confirm_brief(run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> RunRead:
    run, application = _owned_run(session, run_id, org_id)
    if run.status != "awaiting_confirmation":
        raise HTTPException(status_code=409, detail="nothing to confirm right now")
    client = await get_temporal_client()
    await client.get_workflow_handle(explorer_workflow_id(run.external_id)).signal(
        BRIEF_CONFIRMED_SIGNAL
    )
    now = datetime.now(UTC)
    run.status, run.headline, run.brief_confirmed_at, run.updated_at = (
        "confirmed",
        "App Summary confirmed",
        now,
        now,
    )
    session.add(run)
    session.add(
        ExplorerEvent(
            run_id=run.id,
            kind="phase",
            title="App Summary confirmed",
            detail="Thanks — this is now what I'll test against.",
        )
    )
    # Your answers to the summary's questions become trusted knowledge.
    for item in (run.brief or {}).get("questions_for_you") or []:
        if isinstance(item, dict) and item.get("answer"):
            session.add(
                ExplorerKnowledge(
                    application_id=application.id,
                    kind="answer",
                    text=f"{item.get('question')} — {item['answer']}"[:4000],
                    source="App Summary",
                )
            )
    session.commit()
    session.refresh(run)
    return _to_read(session, run, application)


@router.post("/runs/{run_id}/stop", response_model=RunRead)
async def stop_run(run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> RunRead:
    run, application = _owned_run(session, run_id, org_id)
    if run.status not in ACTIVE_RUN_STATUSES:
        raise HTTPException(status_code=409, detail="this run is not running")
    run.status, run.headline, run.updated_at = "stopped", "Stopped", datetime.now(UTC)
    session.add(run)
    session.add(
        ExplorerEvent(
            run_id=run.id, kind="phase", title="Stopped", detail="Exploration was stopped."
        )
    )
    session.commit()
    session.refresh(run)
    try:
        client = await get_temporal_client()
        await client.get_workflow_handle(explorer_workflow_id(run.external_id)).cancel()
    except Exception:  # already finished — the status change above is what matters
        pass
    return _to_read(session, run, application)


async def _end_leftover_workflow(run: ExplorerRun, reason: str) -> None:
    """A run that is paused, stopped, failed or finished can still have its
    old workflow open (e.g. its highlight video waiting on a worker that
    restarted). Its state lives in the database, so end it rather than make
    the person wait before Resume or Regenerate can start a new one."""
    client = await get_temporal_client()
    handle = client.get_workflow_handle(explorer_workflow_id(run.external_id))
    try:
        if (await handle.describe()).status == WorkflowExecutionStatus.RUNNING:
            await handle.terminate(reason=reason)
    except RPCError:  # no workflow under this id, or it just closed
        pass


@router.post("/runs/{run_id}/pause", response_model=RunRead)
async def pause_run(run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> RunRead:
    """Like Stop, but meant to be picked up again with Resume."""
    run, application = _owned_run(session, run_id, org_id)
    if run.status not in ACTIVE_RUN_STATUSES:
        raise HTTPException(status_code=409, detail="this run is not running")
    run.status, run.headline, run.updated_at = "paused", "Paused", datetime.now(UTC)
    session.add(run)
    session.add(
        ExplorerEvent(
            run_id=run.id,
            kind="phase",
            title="Paused",
            detail="Press Resume to carry on from here. Nothing finished is lost.",
        )
    )
    session.commit()
    session.refresh(run)
    try:
        client = await get_temporal_client()
        await client.get_workflow_handle(explorer_workflow_id(run.external_id)).cancel()
    except Exception:  # already finished — the status change above is what matters
        pass
    return _to_read(session, run, application)


@router.post("/runs/{run_id}/resume", response_model=RunRead)
async def resume_run(run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> RunRead:
    """Carry on a paused, stopped or failed run (a server or worker problem
    included) from the step it reached; finished work is kept."""
    run, application = _owned_run(session, run_id, org_id)
    if run.status not in ("paused", "stopped", "failed"):
        raise HTTPException(
            status_code=409, detail="only a paused, stopped or failed run can resume"
        )
    other = session.exec(
        select(ExplorerRun).where(
            ExplorerRun.application_id == application.id,
            ExplorerRun.id != run.id,
            col(ExplorerRun.status).in_(ACTIVE_RUN_STATUSES),
        )
    ).first()
    if other is not None:
        raise HTTPException(status_code=409, detail="another Explorer run is going for this app")
    await _end_leftover_workflow(run, "Resumed by the user")
    run.status, run.headline, run.updated_at = "queued", "Resuming", datetime.now(UTC)
    session.add(run)
    session.commit()
    session.refresh(run)
    client = await get_temporal_client()
    await client.start_workflow(
        EXPLORER_WORKFLOW_NAME,
        args=[str(run.id), "resume"],
        id=explorer_workflow_id(run.external_id),
        task_queue=EXPLORER_TASK_QUEUE,
    )
    return _to_read(session, run, application)


# -- Stage 2: Mission Board, App Map, recordings ---------------------------


def _owned_mission(
    session: Session, external_id: uuid.UUID, org_id: uuid.UUID
) -> tuple[ExplorerMission, ExplorerRun]:
    row = session.exec(
        select(ExplorerMission, ExplorerRun)
        .join(ExplorerRun, col(ExplorerRun.id) == col(ExplorerMission.run_id))
        .join(Application, col(Application.id) == col(ExplorerRun.application_id))
        .where(ExplorerMission.external_id == external_id, Application.organization_id == org_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="mission not found")
    return row[0], row[1]


def _mission_read(mission: ExplorerMission, recording: RecordingInfo | None) -> MissionRead:
    return MissionRead(
        id=mission.external_id,
        title=mission.title,
        goal=mission.goal,
        kind=mission.kind,
        why=mission.why,
        priority=mission.priority,
        instructions=mission.instructions,
        condition=mission.condition,
        expected=mission.expected,
        status=mission.status,
        outcome=mission.outcome,
        matches_expected=mission.matches_expected,
        steps=mission.steps,
        new_screens=mission.new_screens,
        added_by=mission.added_by,
        started_at=mission.started_at,
        finished_at=mission.finished_at,
        recording=recording,
    )


@router.get("/runs/{run_id}/missions", response_model=list[MissionRead])
def list_missions(
    run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep
) -> list[MissionRead]:
    run, _ = _owned_run(session, run_id, org_id)
    missions = session.exec(
        select(ExplorerMission)
        .where(ExplorerMission.run_id == run.id)
        .order_by(col(ExplorerMission.priority).desc(), col(ExplorerMission.created_at))
    ).all()
    recordings = {
        mission_id: RecordingInfo(started_at=started_at, duration_seconds=duration)
        for mission_id, started_at, duration in session.exec(
            select(
                ExplorerRecording.mission_id,
                ExplorerRecording.started_at,
                ExplorerRecording.duration_seconds,
            ).where(ExplorerRecording.run_id == run.id)
        ).all()
    }
    return [_mission_read(m, recordings.get(m.id)) for m in missions]


@router.post("/runs/{run_id}/missions", response_model=MissionRead, status_code=201)
async def add_mission(
    run_id: uuid.UUID, payload: AddMissionRequest, session: SessionDep, org_id: CurrentOrgIdDep
) -> MissionRead:
    run, _ = _owned_run(session, run_id, org_id)
    goal = payload.goal.strip()
    if not goal:
        raise HTTPException(status_code=422, detail="describe the goal for the mission")
    if run.status not in ("exploring", "planning", "explored"):
        raise HTTPException(
            status_code=409, detail="missions can be added once the App Summary is confirmed"
        )
    mission = ExplorerMission(
        run_id=run.id,
        title=(payload.title or goal)[:200],
        goal=goal[:1000],
        kind="custom",
        why="Added by you",
        priority=5,
        added_by="user",
    )
    session.add(mission)
    session.add(
        ExplorerEvent(
            run_id=run.id, kind="phase", title=f"Mission added: {mission.title}", detail=goal
        )
    )
    restart = run.status == "explored"
    if restart:
        run.status, run.headline, run.updated_at = (
            "exploring",
            "Exploring your new mission",
            datetime.now(UTC),
        )
        session.add(run)
    session.commit()
    session.refresh(mission)
    if restart:
        # The earlier exploration's workflow has finished — start a fresh
        # execution that goes straight to the mission pool.
        client = await get_temporal_client()
        await client.start_workflow(
            EXPLORER_WORKFLOW_NAME,
            args=[str(run.id), "missions"],
            id=explorer_workflow_id(run.external_id),
            task_queue=EXPLORER_TASK_QUEUE,
        )
    return _mission_read(mission, None)


@router.post("/missions/{mission_id}/skip", response_model=MissionRead)
def skip_mission(
    mission_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep
) -> MissionRead:
    mission, run = _owned_mission(session, mission_id, org_id)
    if mission.status not in ("queued", "running"):
        raise HTTPException(status_code=409, detail="this mission has already finished")
    mission.status = "skipped"
    session.add(mission)
    session.add(
        ExplorerEvent(
            run_id=run.id, kind="phase", title=f"Mission skipped: {mission.title}", detail=None
        )
    )
    session.commit()
    session.refresh(mission)
    return _mission_read(mission, None)


@router.get("/missions/{mission_id}/recording")
def get_recording(mission_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> Response:
    mission, _ = _owned_mission(session, mission_id, org_id)
    data = session.exec(
        select(ExplorerRecording.data).where(ExplorerRecording.mission_id == mission.id)
    ).first()
    if data is None:
        raise HTTPException(status_code=404, detail="no recording for this mission")
    return Response(
        data, media_type="video/webm", headers={"Cache-Control": "private, max-age=86400"}
    )


@router.get("/runs/{run_id}/map", response_model=AppMapRead)
def app_map(run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> AppMapRead:
    run, _ = _owned_run(session, run_id, org_id)
    screens = session.exec(
        select(ExplorerScreen)
        .where(ExplorerScreen.run_id == run.id)
        .order_by(col(ExplorerScreen.created_at))
    ).all()
    edges = session.exec(
        select(ExplorerTransition).where(ExplorerTransition.run_id == run.id)
    ).all()
    return AppMapRead(
        screens=[ScreenRead(**s.model_dump()) for s in screens],
        edges=[
            MapEdge(from_id=e.from_screen_id, to_id=e.to_screen_id, action=e.action) for e in edges
        ],
    )


# -- Stage 5: proven test cases ----------------------------------------------


class TestCaseRead(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    purpose: str
    technique: str | None
    business_thing: str | None
    start_screen: str | None
    steps: list[str]
    expected: str
    trust: str
    observed: str | None
    check: dict[str, Any] | None
    status: str
    drop_reason: str | None
    proof_runs: int
    proof_passes: int
    catches_breakage: bool | None
    evidence_shot_id: uuid.UUID | None
    code: str | None
    has_proof_video: bool
    # Checklist item it covers ("L-07 Search match", "X-..." for Explorer's own).
    coverage: str | None = None
    linked_to: str | None = None


@router.get("/runs/{run_id}/tests", response_model=list[TestCaseRead])
def list_tests(
    run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep
) -> list[TestCaseRead]:
    run, _ = _owned_run(session, run_id, org_id)
    tests = session.exec(
        select(ExplorerTestCase)
        .where(ExplorerTestCase.run_id == run.id)
        .order_by(col(ExplorerTestCase.created_at))
    ).all()
    with_video = set(
        session.exec(
            select(ExplorerRecording.test_case_id).where(
                ExplorerRecording.run_id == run.id,
                col(ExplorerRecording.test_case_id).is_not(None),
            )
        ).all()
    )
    return [
        TestCaseRead(
            id=t.external_id,
            **t.model_dump(
                exclude={"id", "external_id", "run_id", "script", "created_at", "finished_at"}
            ),
            has_proof_video=t.id in with_video,
            coverage=((t.script or [{}])[0].get("coverage") or None),
            linked_to=((t.script or [{}])[0].get("linked_to") or None),
        )
        for t in tests
    ]


def _owned_test(session: Session, external_id: uuid.UUID, org_id: uuid.UUID) -> ExplorerTestCase:
    row = session.exec(
        select(ExplorerTestCase)
        .join(ExplorerRun, col(ExplorerRun.id) == col(ExplorerTestCase.run_id))
        .join(Application, col(Application.id) == col(ExplorerRun.application_id))
        .where(ExplorerTestCase.external_id == external_id, Application.organization_id == org_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="test case not found")
    return row


@router.get("/tests/{test_id}/proof")
def get_test_proof(test_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> Response:
    test = _owned_test(session, test_id, org_id)
    data = session.exec(
        select(ExplorerRecording.data).where(ExplorerRecording.test_case_id == test.id)
    ).first()
    if data is None:
        raise HTTPException(status_code=404, detail="no proof video for this test")
    return Response(
        data, media_type="video/webm", headers={"Cache-Control": "private, max-age=86400"}
    )


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "test"


@router.get("/runs/{run_id}/tests/download")
def download_tests(run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> Response:
    """All proven and known-bug tests as a ready-to-run Playwright project."""
    run, application = _owned_run(session, run_id, org_id)
    tests = session.exec(
        select(ExplorerTestCase).where(
            ExplorerTestCase.run_id == run.id,
            col(ExplorerTestCase.status).in_(("proven", "known_bug")),
            col(ExplorerTestCase.code).is_not(None),
        )
    ).all()
    if not tests:
        raise HTTPException(status_code=404, detail="no proven test cases yet")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        # Same scaffold as every exported Vantage project, so `@auth` tests
        # run signed in through the shared `tests/auth.setup.ts`.
        signed_in = any("@auth" in (test.code or "") for test in tests)
        login = find_login_page_evidence(session, application) or (
            generic_login_evidence(application) if signed_in else None
        )
        write_project_scaffold(_ZipWriter(archive), application, login)
        for test in tests:
            folder = test.kind.replace("_", "-")
            archive.writestr(f"tests/{folder}/{_slug(test.title)}.spec.ts", test.code or "")
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{_slug(application.name)}-explorer-tests.zip"'
        },
    )


@router.post("/runs/{run_id}/tests/regenerate", response_model=RunRead)
async def regenerate_tests(
    run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep
) -> RunRead:
    run, application = _owned_run(session, run_id, org_id)
    # A stopped run counts once its App Summary was confirmed (it explored).
    explored = run.status in ("explored", "tested") or (
        run.status == "stopped" and run.brief_confirmed_at is not None
    )
    if not explored:
        raise HTTPException(
            status_code=409, detail="tests can be written once exploring has finished"
        )
    await _end_leftover_workflow(run, "Scenarios regenerated by the user")
    for test in session.exec(
        select(ExplorerTestCase).where(ExplorerTestCase.run_id == run.id)
    ).all():
        session.delete(test)
    run.status, run.headline, run.updated_at = "testing", "Writing test cases", datetime.now(UTC)
    session.add(run)
    session.commit()
    session.refresh(run)
    client = await get_temporal_client()
    await client.start_workflow(
        EXPLORER_WORKFLOW_NAME,
        args=[str(run.id), "tests"],
        id=explorer_workflow_id(run.external_id),
        task_queue=EXPLORER_TASK_QUEUE,
    )
    return _to_read(session, run, application)


class VerdictRequest(BaseModel):
    verdict: str  # "not_a_bug" | "ignore"


# The known-bug wording Explorer writes into a test (testkit.playwright_code).
_KNOWN_BUG_LINE = re.compile(
    r"^\s*(// KNOWN BUG|// the app currently:|// The check below proves today|test\.fixme\(true,).*\n",
    re.MULTILINE,
)


@router.post("/tests/{test_id}/verdict", response_model=RunRead)
async def judge_possible_bug(
    test_id: uuid.UUID, payload: VerdictRequest, session: SessionDep, org_id: CurrentOrgIdDep
) -> RunRead:
    """Your answer to a possible bug. "Not a bug": the app is right, so the
    scenario becomes a normal test of what it does and goes to Test cases.
    "Ignore": it is left out. Test cases never hold bugs."""
    row = session.exec(
        select(ExplorerTestCase, ExplorerRun)
        .join(ExplorerRun, col(ExplorerRun.id) == col(ExplorerTestCase.run_id))
        .join(Application, col(Application.id) == col(ExplorerRun.application_id))
        .where(ExplorerTestCase.external_id == test_id, Application.organization_id == org_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    test, run = row
    if test.status != "known_bug":
        raise HTTPException(status_code=409, detail="only a possible bug can be answered")
    if payload.verdict == "ignore":
        test.status, test.drop_reason = "dropped", "Ignored by you"
    elif payload.verdict == "not_a_bug":
        test.status, test.trust = "proven", "confirmed"
        test.expected = (test.observed or test.expected)[:1000]
        test.observed = None
        test.code = _KNOWN_BUG_LINE.sub("", test.code or "") or None
        session.add(
            ExplorerKnowledge(
                application_id=run.application_id,
                kind="answer",
                text=f"Correct behaviour (confirmed by the user): {test.title}: {test.expected}"[:4000],
                source="your answer",
            )
        )
    else:
        raise HTTPException(status_code=422, detail="verdict must be not_a_bug or ignore")
    session.add(test)
    session.commit()
    application = session.get(Application, run.application_id)
    assert application is not None
    if payload.verdict == "not_a_bug":
        # Send the now-proven scenario on to Journeys / Test cases.
        client = await get_temporal_client()
        await client.start_workflow(
            EXPLORER_WORKFLOW_NAME,
            args=[str(run.id), "send"],
            id=f"{explorer_workflow_id(run.external_id)}-send-{uuid.uuid4()}",
            task_queue=EXPLORER_TASK_QUEUE,
        )
    return _to_read(session, run, application)


# -- Stage 4: questions and memory -------------------------------------------


class QuestionRead(BaseModel):
    id: uuid.UUID
    kind: str
    question: str
    why: str | None
    options: list[str]
    shot_id: uuid.UUID | None
    status: str
    answer: str | None
    answered_at: datetime | None
    created_at: datetime
    mission_title: str | None


class AnswerRequest(BaseModel):
    answer: str


class KnowledgeRead(BaseModel):
    id: uuid.UUID
    kind: str
    text: str
    source: str | None
    created_at: datetime


class AddFactRequest(BaseModel):
    text: str


def _question_read(q: ExplorerQuestion, mission_titles: dict[uuid.UUID, str]) -> QuestionRead:
    return QuestionRead(
        id=q.external_id,
        kind=q.kind,
        question=q.question,
        why=q.why,
        options=q.options,
        shot_id=q.shot_id,
        status=q.status,
        answer=q.answer,
        answered_at=q.answered_at,
        created_at=q.created_at,
        mission_title=mission_titles.get(q.mission_id) if q.mission_id else None,
    )


@router.get("/runs/{run_id}/questions", response_model=list[QuestionRead])
def list_questions(
    run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep
) -> list[QuestionRead]:
    run, _ = _owned_run(session, run_id, org_id)
    rows = session.exec(
        select(ExplorerQuestion)
        .where(ExplorerQuestion.run_id == run.id)
        .order_by(col(ExplorerQuestion.created_at).desc())
    ).all()
    titles = {
        mid: title
        for mid, title in session.exec(
            select(ExplorerMission.id, ExplorerMission.title).where(
                ExplorerMission.run_id == run.id
            )
        ).all()
    }
    return [_question_read(q, titles) for q in rows]


def _owned_question(
    session: Session, external_id: uuid.UUID, org_id: uuid.UUID
) -> tuple[ExplorerQuestion, ExplorerRun]:
    row = session.exec(
        select(ExplorerQuestion, ExplorerRun)
        .join(ExplorerRun, col(ExplorerRun.id) == col(ExplorerQuestion.run_id))
        .join(Application, col(Application.id) == col(ExplorerRun.application_id))
        .where(ExplorerQuestion.external_id == external_id, Application.organization_id == org_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="question not found")
    return row[0], row[1]


@router.post("/questions/{question_id}/answer", response_model=QuestionRead)
def answer_question(
    question_id: uuid.UUID, payload: AnswerRequest, session: SessionDep, org_id: CurrentOrgIdDep
) -> QuestionRead:
    question, run = _owned_question(session, question_id, org_id)
    answer = payload.answer.strip()
    if not answer:
        raise HTTPException(status_code=422, detail="write an answer or pick one of the options")
    if question.status != "open":
        raise HTTPException(status_code=409, detail="this question was already answered")
    question.status, question.answer, question.answered_at = (
        "answered",
        answer[:2000],
        datetime.now(UTC),
    )
    session.add(question)
    # Every answer becomes trusted knowledge for this app, for this and future runs.
    fact = f"{question.question} — {answer}"
    if question.kind == "rule" and question.issue_id:
        issue = session.get(ExplorerHealthIssue, question.issue_id)
        if issue is not None:
            if answer.lower().startswith("it's correct") or answer.lower().startswith("correct"):
                issue.kind = "accepted"  # not a bug: your answer is the rule now
                fact = f"Correct behaviour (confirmed by the user): {issue.detail or issue.title}"
            else:
                issue.severity = "high"
                fact = f"Confirmed bug (by the user): {issue.detail or issue.title}"
            session.add(issue)
    session.add(
        ExplorerKnowledge(
            application_id=run.application_id, kind="answer", text=fact[:4000], source="your answer"
        )
    )
    session.add(
        ExplorerEvent(
            run_id=run.id, kind="phase", title="You answered a question", detail=fact[:600]
        )
    )
    session.commit()
    session.refresh(question)
    return _question_read(question, {})


@router.post("/questions/{question_id}/dismiss", response_model=QuestionRead)
def dismiss_question(
    question_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep
) -> QuestionRead:
    question, _ = _owned_question(session, question_id, org_id)
    if question.status == "open":
        question.status = "dismissed"
        session.add(question)
        session.commit()
        session.refresh(question)
    return _question_read(question, {})


@router.get("/applications/{application_id}/knowledge", response_model=list[KnowledgeRead])
def list_knowledge(
    application_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep
) -> list[KnowledgeRead]:
    application = _owned_application(session, application_id, org_id)
    rows = session.exec(
        select(ExplorerKnowledge)
        .where(ExplorerKnowledge.application_id == application.id)
        .order_by(col(ExplorerKnowledge.created_at).desc())
    ).all()
    return [
        KnowledgeRead(
            id=r.external_id, kind=r.kind, text=r.text, source=r.source, created_at=r.created_at
        )
        for r in rows
    ]


@router.post(
    "/applications/{application_id}/knowledge", response_model=KnowledgeRead, status_code=201
)
def add_fact(
    application_id: uuid.UUID, payload: AddFactRequest, session: SessionDep, org_id: CurrentOrgIdDep
) -> KnowledgeRead:
    application = _owned_application(session, application_id, org_id)
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="write the fact Explorer should know")
    row = ExplorerKnowledge(
        application_id=application.id, kind="fact", text=text[:4000], source="added by you"
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return KnowledgeRead(
        id=row.external_id,
        kind=row.kind,
        text=row.text,
        source=row.source,
        created_at=row.created_at,
    )


@router.delete("/knowledge/{knowledge_id}", status_code=204)
def delete_knowledge(
    knowledge_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep
) -> Response:
    row = session.exec(
        select(ExplorerKnowledge)
        .join(Application, col(Application.id) == col(ExplorerKnowledge.application_id))
        .where(ExplorerKnowledge.external_id == knowledge_id, Application.organization_id == org_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    session.delete(row)
    session.commit()
    return Response(status_code=204)


_CHUNK = 1500
_MAX_CHUNKS = 40


def _document_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    if name.endswith(".docx"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", "ignore")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml)
    if name.endswith((".txt", ".md", ".csv")):
        return data.decode("utf-8", "ignore")
    raise HTTPException(status_code=422, detail="upload a PDF, Word (.docx), text or Markdown file")


@router.post(
    "/applications/{application_id}/knowledge/documents",
    response_model=list[KnowledgeRead],
    status_code=201,
)
async def upload_document(
    application_id: uuid.UUID,
    file: UploadFile,
    session: SessionDep,
    org_id: CurrentOrgIdDep,
) -> list[KnowledgeRead]:
    """Requirements, user stories, manuals: split into short passages that
    Explorer treats as trusted knowledge (PLAN.md §4.1, level 2)."""
    application = _owned_application(session, application_id, org_id)
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="the document is too large (15 MB maximum)")
    text = re.sub(r"[ \t]+", " ", _document_text(file.filename or "document", data))
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) > _CHUNK and current:
            chunks.append(current)
            current = ""
        current = f"{current}\n{paragraph}".strip()
    if current:
        chunks.append(current)
    if not chunks:
        raise HTTPException(status_code=422, detail="no readable text found in the document")
    rows = [
        ExplorerKnowledge(
            application_id=application.id,
            kind="doc",
            text=chunk[:4000],
            source=file.filename or "document",
        )
        for chunk in chunks[:_MAX_CHUNKS]
    ]
    session.add_all(rows)
    session.commit()
    return [
        KnowledgeRead(
            id=r.external_id, kind=r.kind, text=r.text, source=r.source, created_at=r.created_at
        )
        for r in rows
    ]


# -- Stage 6: other kinds of users ----------------------------------------------


class RoleRead(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime


class AddRoleRequest(BaseModel):
    name: str
    username: str
    password: str


@router.get("/applications/{application_id}/roles", response_model=list[RoleRead])
def list_roles(
    application_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep
) -> list[RoleRead]:
    application = _owned_application(session, application_id, org_id)
    rows = session.exec(
        select(ExplorerRole).where(ExplorerRole.application_id == application.id)
    ).all()
    return [RoleRead(id=r.external_id, name=r.name, created_at=r.created_at) for r in rows]


@router.post("/applications/{application_id}/roles", response_model=RoleRead, status_code=201)
def add_role(
    application_id: uuid.UUID, payload: AddRoleRequest, session: SessionDep, org_id: CurrentOrgIdDep
) -> RoleRead:
    application = _owned_application(session, application_id, org_id)
    name = payload.name.strip()
    if not name or not payload.username.strip() or not payload.password:
        raise HTTPException(
            status_code=422, detail="enter the user type, its username and its password"
        )
    # The login goes to the secrets store; only the reference is kept.
    ref = VaultSecretsClient().store(
        org_id,
        json.dumps({"username": payload.username.strip(), "password": payload.password}).encode(),
    )
    row = ExplorerRole(application_id=application.id, name=name[:80], secret_ref=ref.path)
    session.add(row)
    session.commit()
    session.refresh(row)
    return RoleRead(id=row.external_id, name=row.name, created_at=row.created_at)


@router.delete("/roles/{role_id}", status_code=204)
def delete_role(role_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> Response:
    row = session.exec(
        select(ExplorerRole)
        .join(Application, col(Application.id) == col(ExplorerRole.application_id))
        .where(ExplorerRole.external_id == role_id, Application.organization_id == org_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    try:
        VaultSecretsClient().delete(SecretRef(path=row.secret_ref))
    except Exception:  # already gone — removing the row is what matters
        pass
    session.delete(row)
    session.commit()
    return Response(status_code=204)


# -- Stage 7: the report ---------------------------------------------------------


class AccessCell(BaseModel):
    role: str
    screen_id: uuid.UUID
    allowed: bool
    note: str | None


class ReportRead(BaseModel):
    run: RunRead
    application_name: str
    hidden_screens: list[ScreenRead]
    possible_bugs: list[HealthIssueRead]
    known_bug_tests: list[TestCaseRead]
    tests_by_kind: dict[str, dict[str, int]]
    missions: list[MissionRead]
    access: list[AccessCell]
    access_screens: list[ScreenRead]
    insights: dict[str, Any]
    has_reel: bool


@router.get("/runs/{run_id}/report", response_model=ReportRead)
def report(run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> ReportRead:
    run, application = _owned_run(session, run_id, org_id)
    screens = session.exec(select(ExplorerScreen).where(ExplorerScreen.run_id == run.id)).all()
    by_id = {s.id: s for s in screens}
    issues = session.exec(
        select(ExplorerHealthIssue).where(
            ExplorerHealthIssue.run_id == run.id, ExplorerHealthIssue.kind == "looks_wrong"
        )
    ).all()
    tests = list_tests(run_id, session, org_id)
    kinds: dict[str, dict[str, int]] = {}
    for t in tests:
        cell = kinds.setdefault(t.kind, {"proven": 0, "known_bug": 0, "dropped": 0})
        if t.status in cell:
            cell[t.status] += 1
    access = session.exec(select(ExplorerAccess).where(ExplorerAccess.run_id == run.id)).all()
    has_reel = (
        session.exec(
            select(ExplorerRecording.id).where(
                ExplorerRecording.run_id == run.id, ExplorerRecording.kind == "reel"
            )
        ).first()
        is not None
    )
    return ReportRead(
        run=_to_read(session, run, application),
        application_name=application.name,
        hidden_screens=[ScreenRead(**s.model_dump()) for s in screens if s.condition],
        possible_bugs=[HealthIssueRead(**i.model_dump()) for i in issues],
        known_bug_tests=[t for t in tests if t.status == "known_bug"],
        tests_by_kind=kinds,
        missions=list_missions(run_id, session, org_id),
        access=[
            AccessCell(role=a.role, screen_id=a.screen_id, allowed=a.allowed, note=a.note)
            for a in access
        ],
        access_screens=[
            ScreenRead(**by_id[sid].model_dump())
            for sid in dict.fromkeys(a.screen_id for a in access)
            if sid in by_id
        ],
        insights=run.insights or {},
        has_reel=has_reel,
    )


@router.get("/runs/{run_id}/reel")
def get_reel(run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> Response:
    run, application = _owned_run(session, run_id, org_id)
    data = session.exec(
        select(ExplorerRecording.data).where(
            ExplorerRecording.run_id == run.id, ExplorerRecording.kind == "reel"
        )
    ).first()
    if data is None:
        raise HTTPException(status_code=404, detail="no highlight video yet")
    return Response(
        data,
        media_type="video/mp4",
        headers={
            "Cache-Control": "private, max-age=600",
            "Content-Disposition": f'inline; filename="{_slug(application.name)}-highlights.mp4"',
        },
    )


@router.get("/runs/{run_id}/report/download")
def download_report(run_id: uuid.UUID, session: SessionDep, org_id: CurrentOrgIdDep) -> Response:
    """One self-contained HTML page a client can open anywhere: summary,
    hidden screens, possible bugs, test coverage and access chart."""
    data = report(run_id, session, org_id)
    run = data.run
    brief = run.brief or {}

    def esc(value: object) -> str:
        return html.escape(str(value or ""))

    def shot(shot_id: uuid.UUID | None) -> str:
        if shot_id is None:
            return ""
        row = session.get(ExplorerShot, shot_id)
        if row is None:
            return ""
        return f'<img src="data:image/jpeg;base64,{base64.b64encode(row.data).decode()}" alt="">'

    hidden = "".join(
        f"<div class='card'>{shot(s.shot_id)}<h4>{esc(s.name)}</h4><p class='cond'>Only appears when {esc(s.condition)}</p></div>"
        for s in data.hidden_screens[:24]
    )
    bugs = "".join(
        f"<li><b>{esc(i.title)}</b><br><span>{esc(i.detail)}</span></li>"
        for i in data.possible_bugs
    ) + "".join(
        f"<li><b>Known bug: {esc(t.title)}</b><br><span>Should: {esc(t.expected)} — the app instead: {esc(t.observed)}</span></li>"
        for t in data.known_bug_tests
    )
    kinds = "".join(
        f"<tr><td>{esc(k.replace('_', ' ').title())}</td><td>{v['proven']}</td><td>{v['known_bug']}</td></tr>"
        for k, v in data.tests_by_kind.items()
    )
    roles = sorted({a.role for a in data.access})
    access_rows = "".join(
        "<tr><td>"
        + esc(s.name)
        + "</td>"
        + "".join(
            "<td>"
            + (
                "✓"
                if any(a.allowed for a in data.access if a.role == r and a.screen_id == s.id)
                else "✕"
            )
            + "</td>"
            for r in roles
        )
        + "</tr>"
        for s in data.access_screens
    )
    coverage = (data.insights or {}).get("coverage") or {}
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>{esc(data.application_name)} — Vantage Explorer report</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f5f6f7;color:#232329}}
header{{background:#0D6B64;color:white;padding:32px 48px}}main{{padding:24px 48px;max-width:1200px}}
.nums{{display:flex;gap:16px;flex-wrap:wrap;margin-top:16px}}.num{{background:rgba(255,255,255,.12);border-radius:12px;padding:12px 18px}}
.num b{{font-size:26px;display:block}}section{{background:white;border-radius:14px;padding:20px 24px;margin:18px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}}.card{{border:2px dashed #2F5FB3;border-radius:10px;overflow:hidden}}
.card img{{width:100%;height:150px;object-fit:cover;object-position:top}}.card h4{{margin:8px 10px 2px}}.cond{{margin:0 10px 10px;color:#2F5FB3;font-size:13px}}
li{{margin:8px 0}}li span{{color:#555;font-size:14px}}table{{border-collapse:collapse}}td,th{{border-bottom:1px solid #eee;padding:6px 14px;text-align:left}}</style></head>
<body><header><h1 style="margin:0">{esc(data.application_name)}</h1><p style="margin:6px 0 0;font-size:17px">{esc(brief.get("one_liner"))}</p>
<div class="nums"><div class="num"><b>{run.counts.screens}</b>screens understood</div><div class="num"><b>{run.counts.hidden_screens}</b>hidden screens</div>
<div class="num"><b>{run.counts.tests_proven}</b>proven tests</div><div class="num"><b>{run.counts.possible_bugs + run.counts.tests_known_bugs}</b>possible bugs</div>
<div class="num"><b>{run.health_score if run.health_score is not None else "–"}</b>health score</div>{f'<div class="num"><b>{coverage.get("percent")}%</b>of the code exercised</div>' if coverage.get("functions") else ""}</div></header>
<main><section><h2>Hidden screens found</h2><div class="grid">{hidden or "<p>None found.</p>"}</div></section>
<section><h2>Possible bugs</h2><ul>{bugs or "<li>None.</li>"}</ul></section>
<section><h2>Proven test cases</h2><table><tr><th>Kind</th><th>Proven</th><th>Known bugs</th></tr>{kinds}</table></section>
{"<section><h2>Who can see what</h2><table><tr><th>Screen</th>" + "".join(f"<th>{esc(r)}</th>" for r in roles) + f"</tr>{access_rows}</table></section>" if roles else ""}
<p style="color:#888;font-size:12px">Generated by Vantage Explorer · {datetime.now(UTC):%d %b %Y}</p></main></body></html>"""
    return Response(
        page,
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="{_slug(data.application_name)}-explorer-report.html"'
        },
    )
