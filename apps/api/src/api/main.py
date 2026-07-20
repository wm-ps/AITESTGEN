"""apps/api FastAPI entrypoint.

Story 1.1 added the health check and scaffold-probe proof-of-wiring
endpoints. Story 1.2 adds sign-in/sign-out and Organization scoping (AD-12).
Story 1.3 adds Application onboarding.
"""

import json
import uuid
from datetime import datetime
from typing import Annotated

from domain import Action, ApiEndpoint, Application, AuthMethod, DiscoveryRun, Page, PlatformUser
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from secrets_client import VaultSecretsClient
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

# Dev-only: allow the Vite dev server to call this API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,  # the session cookie (Story 1.2) requires this
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
        discovery_failure_reason=discovery_run.failure_reason,
    )


@app.post("/applications", response_model=ApplicationRead, status_code=201)
async def create_application(
    payload: ApplicationCreate,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> ApplicationRead:
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


@app.get("/applications/{external_id}", response_model=ApplicationRead)
def get_application(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> ApplicationRead:
    application = session.exec(
        select(Application).where(
            Application.external_id == external_id,
            Application.organization_id == organization_id,
        )
    ).first()
    if application is None:
        raise HTTPException(status_code=404, detail="application not found")
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
