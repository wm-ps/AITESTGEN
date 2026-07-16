"""apps/api FastAPI entrypoint.

Story 1.1 added the health check and scaffold-probe proof-of-wiring
endpoints. Story 1.2 adds sign-in/sign-out and Organization scoping (AD-12).
Story 1.3 adds Application onboarding.
"""

import json
import uuid
from datetime import datetime
from typing import Annotated

from domain import Application, DiscoveryRun, PlatformUser
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from secrets_client import VaultSecretsClient
from sqlmodel import Session, select
from workflows import DISCOVERY_TASK_QUEUE, DiscoveryWorkflow

from api.auth import (
    CurrentOrgIdDep,
    CurrentUserDep,
    clear_session_cookie,
    issue_session_cookie,
    verify_password,
)
from api.db import get_session
from api.temporal_client import get_temporal_client

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
    username: str = Field(
        description="Dedicated Test Account username — not a real end-user identity."
    )
    password: str = Field(
        description="Dedicated Test Account password — not a real end-user identity."
    )


class ApplicationRead(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    environment: str
    created_at: datetime
    discovery_run_id: uuid.UUID
    discovery_status: str


def _to_application_read(application: Application, discovery_run: DiscoveryRun) -> ApplicationRead:
    return ApplicationRead(
        id=application.external_id,
        name=application.name,
        url=application.url,
        environment=application.environment,
        created_at=application.created_at,
        discovery_run_id=discovery_run.external_id,
        discovery_status=discovery_run.status,
    )


@app.post("/applications", response_model=ApplicationRead, status_code=201)
async def create_application(
    payload: ApplicationCreate,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> ApplicationRead:
    # Credentials are written via SecretsClient immediately; the Application
    # row below stores only the returned opaque SecretRef.path (AD-5/NFR-1).
    credential = json.dumps({"username": payload.username, "password": payload.password}).encode()
    secret_ref = VaultSecretsClient().store(organization_id, credential)

    application = Application(
        organization_id=organization_id,
        name=payload.name,
        url=payload.url,
        environment=payload.environment,
        secret_ref=secret_ref.path,
    )
    session.add(application)
    session.flush()

    # Absorbed from removed Story 1.5: start a DiscoveryRun immediately, in
    # the same request — no separate "start discovery" action (AC 4).
    discovery_run = DiscoveryRun(application_id=application.id, status="running")
    session.add(discovery_run)
    session.commit()
    session.refresh(application)
    session.refresh(discovery_run)

    client = await get_temporal_client()
    await client.start_workflow(
        DiscoveryWorkflow.run,
        str(application.external_id),
        id=f"discovery-{discovery_run.external_id}",
        task_queue=DISCOVERY_TASK_QUEUE,
    )

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
