"""apps/api FastAPI entrypoint.

Story 1.1 added the health check and scaffold-probe proof-of-wiring
endpoints. Story 1.2 adds sign-in/sign-out and Organization scoping (AD-12).
Story 1.3 adds Application onboarding.
"""

import json
import os
import uuid
from datetime import UTC, datetime
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
    Scenario,
    TestAsset,
    TestDataEntry,
    TestSuite,
    aggregation_key,
)
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from secrets_client import VaultSecretsClient
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from temporalio.exceptions import WorkflowAlreadyStartedError
from workflows import GENERATION_TASK_QUEUE, GenerationWorkflow, SuiteGenerationWorkflow

from api.auth import (
    CurrentOrgIdDep,
    CurrentUserDep,
    clear_session_cookie,
    issue_session_cookie,
    verify_password,
)
from api.coverage_report import build_coverage_report
from api.db import get_session
from api.discovery import pause_discovery_run, resume_discovery_run, start_discovery_run
from api.temporal_client import get_temporal_client
from api.test_suite_export import (
    TestSuiteExportError,
    assemble_test_suite_project,
    find_login_page_evidence,
    sanitize_slug,
)

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
    login_url: str | None = Field(
        default=None,
        description="Explicit login page URL, if the login form isn't reachable "
        "from the Application URL alone. Optional — omit to let discovery find it "
        "itself. Never reachability-checked (a login endpoint can legitimately "
        "misbehave without prior session state).",
    )
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
    login_url: str | None
    environment: str
    auth_method: AuthMethod
    created_at: datetime
    discovery_run_id: uuid.UUID
    discovery_status: str
    discovery_stage: str | None
    discovery_failure_reason: str | None
    # Story 2.22 AC 2: `status` never travels alone — whenever it's
    # "complete", these counts ride along in the same response so a bare
    # "Complete" can't be misread as "the whole application was covered"
    # (AD-15 is deliberate, non-exhaustive sampling). `None` for every other
    # status, where the full report is more useful than a partial count.
    discovery_coverage_summary: dict[str, int] | None = None


def _coverage_counts(session: Session, discovery_run: DiscoveryRun) -> dict[str, int]:
    coverage = build_coverage_report(session, discovery_run)["coverage"]
    return {
        "reached_pages": coverage["reached"]["pages"],
        "reached_actions": coverage["reached"]["actions"],
        "reached_forms": coverage["reached"]["forms"],
        "blocked": len(coverage["blocked"]),
        "skipped_for_safety": len(coverage["skipped_for_safety"]),
        "unreached": len(coverage["unreached"]),
        "errored": len(coverage["errored"]["items"]),
    }


def _to_application_read(
    session: Session, application: Application, discovery_run: DiscoveryRun
) -> ApplicationRead:
    return ApplicationRead(
        id=application.external_id,
        name=application.name,
        url=application.url,
        login_url=application.login_url,
        environment=application.environment,
        auth_method=application.auth_method,  # type: ignore[arg-type]
        created_at=application.created_at,
        discovery_run_id=discovery_run.external_id,
        discovery_status=discovery_run.status,
        discovery_stage=discovery_run.stage,
        discovery_failure_reason=discovery_run.failure_reason,
        discovery_coverage_summary=(
            _coverage_counts(session, discovery_run) if discovery_run.status == "complete" else None
        ),
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
        login_url=payload.login_url,
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

    return _to_application_read(session, application, discovery_run)


def _latest_discovery_run(session: Session, application_id: uuid.UUID) -> DiscoveryRun | None:
    """Story 2.17: an Application can now have more than one `DiscoveryRun`
    (each pause/resume cycle starts a fresh one, AD-22) — always the most
    recent, never the DB's arbitrary insertion order."""
    return session.exec(
        select(DiscoveryRun)
        .where(DiscoveryRun.application_id == application_id)
        .order_by(DiscoveryRun.created_at.desc())  # type: ignore[arg-type]
    ).first()


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
    discovery_run = _latest_discovery_run(session, application.id)
    assert discovery_run is not None
    return _to_application_read(session, application, discovery_run)


@app.post("/applications/{external_id}/pause-discovery", response_model=ApplicationRead)
async def pause_discovery(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> ApplicationRead:
    """Story 2.17 Task 1 (AC 1)."""
    application = _get_org_application(session, organization_id, external_id)
    discovery_run = _latest_discovery_run(session, application.id)
    if discovery_run is None or discovery_run.status != "running":
        raise HTTPException(status_code=409, detail="discovery run is not running")
    discovery_run = await pause_discovery_run(session, discovery_run)
    return _to_application_read(session, application, discovery_run)


@app.post(
    "/applications/{external_id}/resume-discovery", response_model=ApplicationRead, status_code=201
)
async def resume_discovery(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> ApplicationRead:
    """Story 2.17 Task 2 (AC 2/3): starts a fresh `DiscoveryRun` — see
    `api.discovery.resume_discovery_run`'s own docstring for why that's the
    whole mechanism."""
    application = _get_org_application(session, organization_id, external_id)
    discovery_run = _latest_discovery_run(session, application.id)
    if discovery_run is None or discovery_run.status != "paused":
        raise HTTPException(status_code=409, detail="discovery run is not paused")
    discovery_run = await resume_discovery_run(session, application)
    return _to_application_read(session, application, discovery_run)


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
        # Story 2.22 AC 2: "Complete" never travels alone — the counts
        # already computed above ride along in the same summary line rather
        # than a bare status word (AD-15: sampling, not exhaustive coverage).
        captures.insert(
            0,
            CaptureRead(
                kind="status",
                summary=(
                    f"Crawling complete — {len(pages)} pages, {len(actions)} actions, "
                    f"{len(api_calls)} API calls reached. See the coverage report for "
                    "blocked/skipped/unreached/errored detail."
                ),
                created_at=completed_at,
            ),
        )

    return captures[:50]


@app.get("/discovery-runs/{external_id}/report")
def get_discovery_report(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> dict:
    """Story 2.22 AC 5: the structured coverage/diagnostics report, queryable
    independent of any screen — no `[GAP]` UI exists for this yet (Task 4's
    own disclosed scope), so this is the whole surface for now."""
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
    return build_coverage_report(session, discovery_run)


# --- Discover Journeys (Story 3.1) + Rename/Delete (Story 3.4) ---
# No confidence/risk/importance field appears on either read model below —
# UX-DR21 is a hard, repeatedly-reaffirmed product constraint, not a style
# choice to "helpfully" add to later (see story 3.1's Dev Notes).


class JourneyRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
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
        JourneyRead(
            id=j.external_id,
            name=j.name,
            description=j.description,
            step_count=step_counts.get(j.id, 0),
        )
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
    return JourneyRead(
        id=journey.external_id,
        name=journey.name,
        description=journey.description,
        step_count=step_count,
    )


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


# --- Test Data Pool (Story 2.20) ---
# `[GAP — needs UX pass]` No screen for this exists in the current 6-screen
# IA (DESIGN.md/EXPERIENCE.md) — this is backend + API only, independently
# useful on its own (seed via API, or by answering a Blocked Frontier item
# once Story 2.15 lands), same disclosed scope as Story 2.17/2.22's UI halves.
#
# `_POOL_WILDCARD_ROUTE_FAMILY`: Story 2.15's `aggregation_key` is (field
# name, input type, route family) — but a user seeding data before a crawl
# has ever run has no route family to give, and a value like "Policy Number"
# is usually meant to apply everywhere, not to one specific route. Rather
# than force a route family at seed time, entries are keyed under this
# wildcard by default; the Data Resolver (Story 2.13) tries the candidate's
# real route family first, then falls back to the wildcard. Still the same
# shared `aggregation_key` function either way — this is a choice of what
# value to pass for `route_family`, not a second normalizer.
_POOL_WILDCARD_ROUTE_FAMILY = "*"


class TestDataEntryCreate(BaseModel):
    label: str
    field_name: str
    input_type: str = "text"
    route_family: str = _POOL_WILDCARD_ROUTE_FAMILY
    value: str
    is_sensitive: bool = False


class TestDataEntryUpdate(BaseModel):
    label: str | None = None
    value: str | None = None
    is_sensitive: bool | None = None


class TestDataEntryRead(BaseModel):
    id: uuid.UUID
    label: str
    normalized_key: str
    is_sensitive: bool
    # AC 6: never the raw value for a sensitive entry, in any API response.
    value: str | None


def _mask(entry: TestDataEntry) -> str | None:
    if entry.is_sensitive:
        return None
    return entry.value


def _get_org_test_data_entry(
    session: Session, organization_id: uuid.UUID, external_id: uuid.UUID
) -> TestDataEntry:
    entry = session.exec(
        select(TestDataEntry).where(TestDataEntry.external_id == external_id)
    ).first()
    application = session.get(Application, entry.application_id) if entry else None
    if entry is None or application is None or application.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="test data entry not found")
    return entry


@app.get("/applications/{external_id}/test-data", response_model=list[TestDataEntryRead])
def list_test_data_entries(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> list[TestDataEntryRead]:
    application = _get_org_application(session, organization_id, external_id)
    entries = session.exec(
        select(TestDataEntry).where(TestDataEntry.application_id == application.id)
    ).all()
    return [
        TestDataEntryRead(
            id=e.external_id,
            label=e.label,
            normalized_key=e.normalized_key,
            is_sensitive=e.is_sensitive,
            value=_mask(e),
        )
        for e in entries
    ]


@app.post(
    "/applications/{external_id}/test-data", response_model=TestDataEntryRead, status_code=201
)
def create_test_data_entry(
    external_id: uuid.UUID,
    payload: TestDataEntryCreate,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> TestDataEntryRead:
    application = _get_org_application(session, organization_id, external_id)
    normalized_key = aggregation_key(payload.field_name, payload.input_type, payload.route_family)

    value: str | None = payload.value
    secret_ref: str | None = None
    if payload.is_sensitive:
        # AC 6: held via the existing Vault-backed client, not plain Postgres
        # storage — mirrors Application.secret_ref (create_application above).
        secret_ref = VaultSecretsClient().store(organization_id, payload.value.encode()).path
        value = None

    entry = TestDataEntry(
        application_id=application.id,
        label=payload.label,
        normalized_key=normalized_key,
        value=value,
        secret_ref=secret_ref,
        is_sensitive=payload.is_sensitive,
    )
    session.add(entry)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="a test data entry for this field already exists"
        ) from None
    session.refresh(entry)
    return TestDataEntryRead(
        id=entry.external_id,
        label=entry.label,
        normalized_key=entry.normalized_key,
        is_sensitive=entry.is_sensitive,
        value=_mask(entry),
    )


@app.patch("/test-data/{external_id}", response_model=TestDataEntryRead)
def update_test_data_entry(
    external_id: uuid.UUID,
    payload: TestDataEntryUpdate,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> TestDataEntryRead:
    entry = _get_org_test_data_entry(session, organization_id, external_id)
    if payload.label is not None:
        entry.label = payload.label
    is_sensitive = payload.is_sensitive if payload.is_sensitive is not None else entry.is_sensitive
    if payload.value is not None:
        if is_sensitive:
            # `organization_id` here is already confirmed (by
            # `_get_org_test_data_entry` above) to be this entry's own
            # Application's org — no need to re-fetch the Application row.
            entry.secret_ref = (
                VaultSecretsClient().store(organization_id, payload.value.encode()).path
            )
            entry.value = None
        else:
            entry.value = payload.value
            entry.secret_ref = None
    entry.is_sensitive = is_sensitive
    entry.updated_at = datetime.now(UTC)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return TestDataEntryRead(
        id=entry.external_id,
        label=entry.label,
        normalized_key=entry.normalized_key,
        is_sensitive=entry.is_sensitive,
        value=_mask(entry),
    )


@app.delete("/test-data/{external_id}", status_code=204)
def delete_test_data_entry(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> None:
    entry = _get_org_test_data_entry(session, organization_id, external_id)
    session.delete(entry)
    session.commit()


# --- Scenario generation + Review Scenarios (Story 4.1) ---
# `[CORRECTED 2026-07-21]` Scenario generation is button-triggered, not
# automatic at Journey-discovery time — see generate_scenarios below, the
# sole trigger for GenerationWorkflow/ScenarioGenerationActivity.


class ScenarioTestDataFieldRead(BaseModel):
    name: str
    mandatory: bool
    value: str | None


class ScenarioRead(BaseModel):
    id: uuid.UUID
    journey_id: uuid.UUID
    journey_name: str
    type: str
    name: str
    steps: list[str]
    expected_result: str
    test_data: list[ScenarioTestDataFieldRead]
    test_data_complete: bool


class ScenarioRenamePayload(BaseModel):
    name: str


class ScenarioTestDataUpdatePayload(BaseModel):
    name: str
    value: str


def _to_scenario_read(
    scenario: Scenario, journey_external_id: uuid.UUID, journey_name: str
) -> ScenarioRead:
    return ScenarioRead(
        id=scenario.external_id,
        journey_id=journey_external_id,
        journey_name=journey_name,
        type=scenario.type,
        name=scenario.name,
        steps=scenario.steps,
        expected_result=scenario.expected_result,
        test_data=[ScenarioTestDataFieldRead(**field) for field in scenario.test_data],
        test_data_complete=scenario.test_data_complete(),
    )


def _get_org_scenario(
    session: Session, organization_id: uuid.UUID, external_id: uuid.UUID
) -> tuple[Scenario, Journey]:
    scenario = session.exec(select(Scenario).where(Scenario.external_id == external_id)).first()
    journey = session.get(Journey, scenario.journey_id) if scenario else None
    application = session.get(Application, journey.application_id) if journey else None
    if (
        scenario is None
        or journey is None
        or application is None
        or application.organization_id != organization_id
    ):
        raise HTTPException(status_code=404, detail="scenario not found")
    return scenario, journey


@app.post("/applications/{external_id}/generate-scenarios", status_code=202)
async def generate_scenarios(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> dict[str, int]:
    application = _get_org_application(session, organization_id, external_id)
    journeys = session.exec(
        select(Journey).where(
            Journey.application_id == application.id,
            Journey.status == "candidate",
        )
    ).all()

    client = await get_temporal_client()
    triggered = 0
    for journey in journeys:
        # Idempotent: skip a Journey that already has Scenarios for its
        # current attempt — Temporal's WorkflowAlreadyStartedError below is
        # the second layer, covering the narrower race where the workflow
        # started but hasn't written its Scenario rows yet.
        already_generated = session.exec(
            select(Scenario).where(
                Scenario.journey_id == journey.id,
                Scenario.generation_run_id == journey.attempt,
            )
        ).first()
        if already_generated is not None:
            continue
        try:
            await client.start_workflow(
                GenerationWorkflow.run,
                str(journey.external_id),
                id=f"generation-{journey.external_id}-{journey.attempt}",
                task_queue=GENERATION_TASK_QUEUE,
            )
            triggered += 1
        except WorkflowAlreadyStartedError:
            pass

    return {"journeys_triggered": triggered}


@app.get("/applications/{external_id}/scenarios", response_model=list[ScenarioRead])
def list_scenarios(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> list[ScenarioRead]:
    application = _get_org_application(session, organization_id, external_id)
    journeys = session.exec(
        select(Journey).where(
            Journey.application_id == application.id,
            Journey.status == "candidate",
        )
    ).all()
    if not journeys:
        return []
    journeys_by_id = {j.id: j for j in journeys}
    scenarios = session.exec(
        select(Scenario).where(
            Scenario.journey_id.in_(journeys_by_id.keys()),  # type: ignore[attr-defined]
            Scenario.current.is_(True),  # type: ignore[attr-defined]
        )
    ).all()
    return [
        _to_scenario_read(
            s, journeys_by_id[s.journey_id].external_id, journeys_by_id[s.journey_id].name
        )
        for s in scenarios
    ]


@app.patch("/scenarios/{external_id}", response_model=ScenarioRead)
def rename_scenario(
    external_id: uuid.UUID,
    payload: ScenarioRenamePayload,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> ScenarioRead:
    scenario, journey = _get_org_scenario(session, organization_id, external_id)
    scenario.name = payload.name
    session.add(scenario)
    session.commit()
    session.refresh(scenario)
    return _to_scenario_read(scenario, journey.external_id, journey.name)


@app.delete("/scenarios/{external_id}", status_code=204)
def delete_scenario(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> None:
    scenario, _journey = _get_org_scenario(session, organization_id, external_id)
    session.delete(scenario)
    session.commit()


@app.patch("/scenarios/{external_id}/test-data", response_model=ScenarioRead)
def update_scenario_test_data(
    external_id: uuid.UUID,
    payload: ScenarioTestDataUpdatePayload,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> ScenarioRead:
    scenario, journey = _get_org_scenario(session, organization_id, external_id)
    updated_fields = [dict(field) for field in scenario.test_data]
    for field in updated_fields:
        if field["name"] == payload.name:
            field["value"] = payload.value
            break
    else:
        raise HTTPException(
            status_code=422, detail=f"unknown test data field {payload.name!r}"
        )
    scenario.test_data = updated_fields
    session.add(scenario)
    session.commit()
    session.refresh(scenario)
    return _to_scenario_read(scenario, journey.external_id, journey.name)


# --- Generate Suite (Story 4.2) ---
# One `SuiteGenerationWorkflow` per candidate Journey with current Scenarios
# — mirrors generate_scenarios' "one GenerationWorkflow per candidate
# Journey" pattern exactly. Journey-scoped, not Application-wide: the
# workflow-ID convention (`suite-{journey_id}-{attempt}`) mirrors
# `generation-{journey_id}-{attempt}`, so `journey.attempt` is what makes
# the double-click race safe to retry with no extra bookkeeping. (Story
# 4.3/FR-18 regeneration, which would have been the other caller bumping
# `attempt`, is cut in full — see sprint-change-proposal-2026-07-27.md.)


class TestCaseRead(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    code: str


class TestSuiteRead(BaseModel):
    id: uuid.UUID
    name: str
    journey_name: str
    test_cases: list[TestCaseRead]


@app.post("/applications/{external_id}/generate-suite", status_code=202)
async def generate_suite(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> dict[str, int]:
    application = _get_org_application(session, organization_id, external_id)
    journeys = session.exec(
        select(Journey).where(
            Journey.application_id == application.id,
            Journey.status == "candidate",
        )
    ).all()

    client = await get_temporal_client()
    triggered = 0
    for journey in journeys:
        has_current_scenarios = session.exec(
            select(Scenario).where(
                Scenario.journey_id == journey.id,
                Scenario.current.is_(True),  # type: ignore[attr-defined]
            )
        ).first()
        if has_current_scenarios is None:
            continue
        # Idempotent: skip a Journey that already has a TestSuite for its
        # current attempt — Temporal's WorkflowAlreadyStartedError below is
        # the second layer, covering the narrower race where the workflow
        # started but hasn't written its TestSuite row yet.
        already_generated = session.exec(
            select(TestSuite).where(
                TestSuite.journey_id == journey.id,
                TestSuite.generation_run_id == journey.attempt,
            )
        ).first()
        if already_generated is not None:
            continue
        try:
            await client.start_workflow(
                SuiteGenerationWorkflow.run,
                str(journey.external_id),
                id=f"suite-{journey.external_id}-{journey.attempt}",
                task_queue=GENERATION_TASK_QUEUE,
            )
            triggered += 1
        except WorkflowAlreadyStartedError:
            pass

    return {"suites_triggered": triggered}


@app.get("/applications/{external_id}/test-suites", response_model=list[TestSuiteRead])
def list_test_suites(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> list[TestSuiteRead]:
    application = _get_org_application(session, organization_id, external_id)
    journeys = session.exec(
        select(Journey).where(
            Journey.application_id == application.id,
            Journey.status == "candidate",
        )
    ).all()
    if not journeys:
        return []
    journeys_by_id = {j.id: j for j in journeys}

    test_suites = session.exec(
        select(TestSuite).where(
            TestSuite.journey_id.in_(journeys_by_id.keys()),  # type: ignore[attr-defined]
            TestSuite.current.is_(True),  # type: ignore[attr-defined]
        )
    ).all()
    if not test_suites:
        return []
    suite_ids = [ts.id for ts in test_suites]

    test_assets = session.exec(
        select(TestAsset).where(
            TestAsset.test_suite_id.in_(suite_ids),  # type: ignore[attr-defined]
            TestAsset.current.is_(True),  # type: ignore[attr-defined]
        )
    ).all()
    scenario_ids = {a.scenario_id for a in test_assets}
    scenarios_by_id = {
        s.id: s
        for s in (
            session.exec(select(Scenario).where(Scenario.id.in_(scenario_ids))).all()  # type: ignore[attr-defined]
            if scenario_ids
            else []
        )
    }

    assets_by_suite: dict[uuid.UUID, list[TestAsset]] = {}
    for asset in test_assets:
        assets_by_suite.setdefault(asset.test_suite_id, []).append(asset)

    result = []
    for test_suite in test_suites:
        journey = journeys_by_id[test_suite.journey_id]
        test_cases = []
        for asset in assets_by_suite.get(test_suite.id, []):
            scenario = scenarios_by_id.get(asset.scenario_id)
            if scenario is None:
                continue
            test_cases.append(
                TestCaseRead(
                    id=asset.external_id, name=scenario.name, type=scenario.type, code=asset.code
                )
            )
        result.append(
            TestSuiteRead(
                id=test_suite.external_id,
                name=test_suite.name,
                journey_name=journey.name,
                test_cases=test_cases,
            )
        )
    return result


@app.get("/applications/{external_id}/test-suites/download")
def download_test_suite_project(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> Response:
    # Same org-scoped lookup as every other Application endpoint (AD-12) —
    # never by external_id alone, or one Organization could download
    # another's generated tests (AC 6).
    application = _get_org_application(session, organization_id, external_id)

    journeys = session.exec(
        select(Journey).where(
            Journey.application_id == application.id,
            Journey.status == "candidate",
        )
    ).all()
    journeys_by_id = {j.id: j for j in journeys}

    test_suites = (
        session.exec(
            select(TestSuite).where(
                TestSuite.journey_id.in_(journeys_by_id.keys()),  # type: ignore[attr-defined]
                TestSuite.current.is_(True),  # type: ignore[attr-defined]
            )
        ).all()
        if journeys_by_id
        else []
    )
    if not test_suites:
        raise HTTPException(status_code=404, detail="no current test suites to export")
    suite_ids = [ts.id for ts in test_suites]

    test_assets = session.exec(
        select(TestAsset).where(
            TestAsset.test_suite_id.in_(suite_ids),  # type: ignore[attr-defined]
            TestAsset.current.is_(True),  # type: ignore[attr-defined]
        )
    ).all()
    assets_by_suite: dict[uuid.UUID, list[TestAsset]] = {}
    for asset in test_assets:
        assets_by_suite.setdefault(asset.test_suite_id, []).append(asset)

    scenario_ids = {a.scenario_id for a in test_assets}
    scenario_name_by_asset_id = {}
    if scenario_ids:
        scenarios_by_id = {
            s.id: s
            for s in session.exec(
                select(Scenario).where(Scenario.id.in_(scenario_ids))  # type: ignore[attr-defined]
            ).all()
        }
        for asset in test_assets:
            scenario = scenarios_by_id.get(asset.scenario_id)
            if scenario is not None:
                scenario_name_by_asset_id[asset.id] = scenario.name

    # Never resolves Application.secret_ref / calls SecretsClient — only
    # reads non-secret auth_method and (for standard_login) the non-secret
    # captured login-page evidence (AC 11-13).
    login_evidence = (
        find_login_page_evidence(session, application)
        if application.auth_method == "standard_login"
        else None
    )

    try:
        zip_bytes = assemble_test_suite_project(
            application,
            test_suites,
            journeys_by_id,
            assets_by_suite,
            scenario_name_by_asset_id,
            login_evidence,
        )
    except TestSuiteExportError as exc:
        # Fail closed (AC 9) — never a 200 with partial/corrupt zip bytes.
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    filename = sanitize_slug(application.name, fallback="application")
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}-tests.zip"'},
    )
