"""apps/api FastAPI entrypoint.

Story 1.1 added the health check and scaffold-probe proof-of-wiring
endpoints. Story 1.2 adds sign-in/sign-out and Organization scoping (AD-12).
Story 1.3 adds Application onboarding.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Annotated

import httpx
from domain import (
    Action,
    ApiEndpoint,
    Application,
    AuthMethod,
    Component,
    DiscoveryRun,
    Form,
    Journey,
    JourneyStep,
    Page,
    PlatformUser,
)
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from secrets_client import VaultSecretsClient
from sqlalchemy import func
from sqlmodel import Session, select

from api.auth import (
    CurrentOrgIdDep,
    CurrentUserDep,
    clear_session_cookie,
    issue_session_cookie,
    verify_password,
)
from api.db import get_session
from api.discovery import start_discovery_run

app = FastAPI(title="Application Intelligence Platform API")

# Allowed browser origins for the SPA. Overridable via CORS_ALLOWED_ORIGINS
# (comma-separated) so each environment (dev/staging/prod) can set its own
# without touching code; defaults cover both dev-server hostnames Vite may
# be reached on (localhost and 127.0.0.1). Never combine "*" with
# allow_credentials=True — the session cookie (Story 1.2) requires
# credentialed CORS, which browsers reject if the origin is a wildcard.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_allowed_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class LoginRequest(BaseModel):
    email: str
    password: str


class UserRead(BaseModel):
    name: str
    email: str


@app.post("/auth/login", response_model=UserRead)
def login(payload: LoginRequest, response: Response, session: SessionDep) -> UserRead:
    user = session.exec(select(PlatformUser).where(PlatformUser.email == payload.email)).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="invalid email or password")
    issue_session_cookie(response, user.id)
    return UserRead(name=user.name, email=user.email)


@app.post("/auth/logout")
def logout(response: Response) -> dict[str, str]:
    clear_session_cookie(response)
    return {"status": "ok"}


@app.get("/auth/me", response_model=UserRead)
def me(user: CurrentUserDep) -> UserRead:
    return UserRead(name=user.name, email=user.email)


class ApplicationCreate(BaseModel):
    name: str
    url: str
    environment: str
    auth_method: AuthMethod = "standard_login"
    username: str | None = Field(
        default=None,
        description="Dedicated Test Account username — not a real end-user identity. "
        "Required when auth_method is 'standard_login'.",
    )
    password: str | None = Field(
        default=None,
        description="Dedicated Test Account password — not a real end-user identity. "
        "Required when auth_method is 'standard_login'.",
    )
    session_state: str | None = Field(
        default=None,
        description="A previously-authenticated session the customer already produced "
        "(e.g. Playwright storageState.json contents), pasted as-is. Required when "
        "auth_method is 'sso_session_reuse'. The platform never performs the SSO/MFA "
        "handshake itself — it only reuses a session the customer supplies.",
    )

    @model_validator(mode="after")
    def _credentials_match_auth_method(self) -> ApplicationCreate:
        if self.auth_method == "standard_login" and not (self.username and self.password):
            raise ValueError("username and password are required for standard_login")
        if self.auth_method == "sso_session_reuse" and not self.session_state:
            raise ValueError("session_state is required for sso_session_reuse")
        return self


class ApplicationRead(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    environment: str
    auth_method: AuthMethod
    created_at: datetime
    discovery_run_id: uuid.UUID
    discovery_status: str
    discovery_stage: str | None
    discovery_failure_reason: str | None


def _to_application_read(application: Application, discovery_run: DiscoveryRun) -> ApplicationRead:
    return ApplicationRead(
        id=application.external_id,
        name=application.name,
        url=application.url,
        environment=application.environment,
        auth_method=application.auth_method,  # type: ignore[arg-type]
        created_at=application.created_at,
        discovery_run_id=discovery_run.external_id,
        discovery_status=discovery_run.status,
        discovery_stage=discovery_run.stage,
        discovery_failure_reason=discovery_run.failure_reason,
    )


_UNREACHABLE_DETAIL = (
    "Base URL did not respond — confirm it's deployed and accessible before connecting."
)


async def _check_reachable(client: httpx.AsyncClient, url: str) -> None:
    """FR-31 (CR-3): gates Application creation on the Base URL actually
    responding, 2xx/3xx — the same tolerance FR-6(f) already uses for a live
    discovery-time destination. Raises HTTPException(422) otherwise."""
    try:
        response = await client.head(url)
        if response.status_code >= 400:
            response = await client.get(url)
    except httpx.RequestError:
        try:
            response = await client.get(url)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=422, detail=_UNREACHABLE_DETAIL) from exc
    if not (200 <= response.status_code < 400):
        raise HTTPException(status_code=422, detail=_UNREACHABLE_DETAIL)


@app.post("/applications", response_model=ApplicationRead, status_code=201)
async def create_application(
    payload: ApplicationCreate,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> ApplicationRead:
    # FR-31 (CR-3): fail fast before any write if the Base URL isn't reachable.
    async with httpx.AsyncClient(follow_redirects=True, timeout=5.0) as client:
        await _check_reachable(client, payload.url)

    # Credentials are written via SecretsClient immediately; the Application
    # row below stores only the returned opaque SecretRef.path (AD-5/NFR-1).
    # Exactly one of the two credential shapes is stored, matching the
    # Authentication method select's "one selected at a time" rule (Story 1.4).
    if payload.auth_method == "standard_login":
        creds = {"username": payload.username, "password": payload.password}
        credential = json.dumps(creds).encode()
    else:
        credential = payload.session_state.encode()  # type: ignore[union-attr]
    secret_ref = VaultSecretsClient().store(organization_id, credential)

    application = Application(
        organization_id=organization_id,
        name=payload.name,
        url=payload.url,
        environment=payload.environment,
        auth_method=payload.auth_method,
        secret_ref=secret_ref.path,
    )
    session.add(application)
    session.flush()

    # Absorbed from removed Story 1.5: start a DiscoveryRun immediately, in
    # the same request — no separate "start discovery" action (AC 4). The
    # DiscoveryRun-creation logic itself is Story 2.1's (api.discovery).
    discovery_run = await start_discovery_run(session, application)

    return _to_application_read(application, discovery_run)


def _get_org_application(
    session: Session, organization_id: uuid.UUID, external_id: uuid.UUID
) -> Application:
    application = session.exec(
        select(Application).where(
            Application.external_id == external_id,
            Application.organization_id == organization_id,
        )
    ).first()
    if application is None:
        raise HTTPException(status_code=404, detail="application not found")
    return application


@app.get("/applications/{external_id}", response_model=ApplicationRead)
def get_application(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> ApplicationRead:
    application = _get_org_application(session, organization_id, external_id)
    discovery_run = session.exec(
        select(DiscoveryRun).where(DiscoveryRun.application_id == application.id)
    ).first()
    assert discovery_run is not None
    return _to_application_read(application, discovery_run)


class CaptureRead(BaseModel):
    kind: str
    summary: str
    created_at: datetime


@app.get("/discovery-runs/{external_id}/captures", response_model=list[CaptureRead])
def list_captures(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> list[CaptureRead]:
    discovery_run = session.exec(
        select(DiscoveryRun).where(DiscoveryRun.external_id == external_id)
    ).first()
    application = session.get(Application, discovery_run.application_id) if discovery_run else None
    if (
        discovery_run is None
        or application is None
        or application.organization_id != organization_id
    ):
        raise HTTPException(status_code=404, detail="discovery run not found")

    # There is no single "capture" table (Story 2.2 rework, no generic
    # Evidence) — the live feed is a union across the typed capture tables,
    # ordered by created_at across all of them, not any one table's own feed.
    pages = session.exec(select(Page).where(Page.discovery_run_id == discovery_run.id)).all()
    actions = session.exec(select(Action).where(Action.discovery_run_id == discovery_run.id)).all()
    api_calls = session.exec(
        select(ApiEndpoint).where(ApiEndpoint.discovery_run_id == discovery_run.id)
    ).all()

    captures = (
        [
            CaptureRead(kind="page", summary=f"{p.title} ({p.url})", created_at=p.created_at)
            for p in pages
        ]
        + [
            CaptureRead(kind="action", summary=a.description, created_at=a.created_at)
            for a in actions
        ]
        + [
            CaptureRead(kind="api_call", summary=f"{e.method} {e.path}", created_at=e.created_at)
            for e in api_calls
        ]
    )
    captures.sort(key=lambda c: c.created_at, reverse=True)

    # Self-explanatory terminal marker: the workflow keeps running past this
    # point (Story 2.5's model builder, formerly 2.6's inference), so without
    # this the feed just goes quiet with no signal that crawling itself is
    # actually done.
    if discovery_run.status == "complete":
        completed_at = captures[0].created_at if captures else discovery_run.created_at
        captures.insert(
            0, CaptureRead(kind="status", summary="Crawling complete", created_at=completed_at)
        )

    return captures[:50]


# --- Discover Journeys (Story 3.1) + Rename/Delete (Story 3.4) ---
# No confidence/risk/importance field appears on either read model below —
# UX-DR21 is a hard, repeatedly-reaffirmed product constraint, not a style
# choice to "helpfully" add to later (see story 3.1's Dev Notes).


class JourneyRead(BaseModel):
    id: uuid.UUID
    name: str
    step_count: int


class JourneyStepRead(BaseModel):
    step_order: int
    stage_label: str
    route: str
    method: str


class JourneyRenamePayload(BaseModel):
    name: str


def _get_org_journey(
    session: Session, organization_id: uuid.UUID, external_id: uuid.UUID
) -> Journey:
    journey = session.exec(select(Journey).where(Journey.external_id == external_id)).first()
    application = session.get(Application, journey.application_id) if journey else None
    if journey is None or application is None or application.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="journey not found")
    return journey


def _journey_step_route_and_method(
    step: JourneyStep,
    pages: dict[uuid.UUID, Page],
    forms: dict[uuid.UUID, Form],
    api_endpoints: dict[uuid.UUID, ApiEndpoint],
    components: dict[uuid.UUID, Component],
) -> tuple[str, str]:
    # Exactly one of these is set per row (DB CHECK constraint) — every real
    # `JourneyStep` today only ever sets `page_id` (Story 2.6's
    # InferenceActivity), but the schema allows all four typed targets, so
    # this resolves all of them rather than assuming page-only.
    if step.page_id is not None:
        return pages[step.page_id].url, "GET"
    if step.form_id is not None:
        form = forms[step.form_id]
        return form.action_url, form.method
    if step.api_endpoint_id is not None:
        endpoint = api_endpoints[step.api_endpoint_id]
        return endpoint.path, endpoint.method
    assert step.component_id is not None
    component = components[step.component_id]
    return pages[component.page_id].url, "GET"


@app.get("/applications/{external_id}/journeys", response_model=list[JourneyRead])
def list_journeys(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> list[JourneyRead]:
    application = _get_org_application(session, organization_id, external_id)
    journeys = session.exec(
        select(Journey).where(
            Journey.application_id == application.id,
            Journey.status == "candidate",
        )
    ).all()
    step_counts: dict[uuid.UUID, int] = {}
    if journeys:
        step_counts = dict(
            session.exec(
                select(JourneyStep.journey_id, func.count())
                .where(JourneyStep.journey_id.in_([j.id for j in journeys]))  # type: ignore[attr-defined]
                .group_by(JourneyStep.journey_id)  # type: ignore[arg-type]
            ).all()
        )
    return [
        JourneyRead(id=j.external_id, name=j.name, step_count=step_counts.get(j.id, 0))
        for j in journeys
    ]


@app.get("/journeys/{external_id}/steps", response_model=list[JourneyStepRead])
def list_journey_steps(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> list[JourneyStepRead]:
    journey = _get_org_journey(session, organization_id, external_id)
    steps = session.exec(
        select(JourneyStep)
        .where(JourneyStep.journey_id == journey.id)
        .order_by(JourneyStep.step_order)  # type: ignore[arg-type]
    ).all()

    component_ids = {s.component_id for s in steps if s.component_id}
    components = {
        c.id: c
        for c in (
            session.exec(
                select(Component).where(Component.id.in_(component_ids))  # type: ignore[attr-defined]
            ).all()
            if component_ids
            else []
        )
    }
    page_ids = {s.page_id for s in steps if s.page_id} | {c.page_id for c in components.values()}
    form_ids = {s.form_id for s in steps if s.form_id}
    api_endpoint_ids = {s.api_endpoint_id for s in steps if s.api_endpoint_id}

    pages = {
        p.id: p
        for p in (
            session.exec(select(Page).where(Page.id.in_(page_ids))).all()  # type: ignore[attr-defined]
            if page_ids
            else []
        )
    }
    forms = {
        f.id: f
        for f in (
            session.exec(select(Form).where(Form.id.in_(form_ids))).all()  # type: ignore[attr-defined]
            if form_ids
            else []
        )
    }
    api_endpoints = {
        e.id: e
        for e in (
            session.exec(
                select(ApiEndpoint).where(
                    ApiEndpoint.id.in_(api_endpoint_ids)  # type: ignore[attr-defined]
                )
            ).all()
            if api_endpoint_ids
            else []
        )
    }

    result = []
    for step in steps:
        route, method = _journey_step_route_and_method(
            step, pages, forms, api_endpoints, components
        )
        result.append(
            JourneyStepRead(
                step_order=step.step_order, stage_label=step.stage_label, route=route, method=method
            )
        )
    return result


@app.patch("/journeys/{external_id}", response_model=JourneyRead)
def rename_journey(
    external_id: uuid.UUID,
    payload: JourneyRenamePayload,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> JourneyRead:
    journey = _get_org_journey(session, organization_id, external_id)
    if journey.status != "candidate":
        raise HTTPException(status_code=409, detail="journey already deleted")
    journey.name = payload.name
    session.add(journey)
    session.commit()
    session.refresh(journey)
    step_count = session.exec(
        select(func.count()).select_from(JourneyStep).where(JourneyStep.journey_id == journey.id)
    ).one()
    return JourneyRead(id=journey.external_id, name=journey.name, step_count=step_count)


@app.delete("/journeys/{external_id}", status_code=204)
def delete_journey(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> None:
    journey = _get_org_journey(session, organization_id, external_id)
    if journey.status != "candidate":
        raise HTTPException(status_code=409, detail="journey already deleted")
    journey.status = "deleted"
    session.add(journey)
    session.commit()
