"""apps/api FastAPI entrypoint.

Story 1.1 added the health check and scaffold-probe proof-of-wiring
endpoints. Story 1.2 adds sign-in/sign-out and Organization scoping (AD-12).
Story 1.3 adds Application onboarding.
"""

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

import httpx
from domain import (
    Action,
    ApiEndpoint,
    Application,
    AuthMethod,
    Component,
    DiscoveryRun,
    DiscoverySettings,
    ExecutionPolicy,
    Form,
    InteractionLevel,
    Invite,
    Journey,
    JourneyStep,
    Page,
    PlatformUser,
    RetentionPeriod,
    Scenario,
    Schedule,
    TestAsset,
    TestDataEntry,
    TestResult,
    TestResultArtifact,
    TestRun,
    TestSuite,
    aggregation_key,
)
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from object_store import ObjectStore
from pydantic import BaseModel, Field, field_validator, model_validator
from secrets_client import SecretRef, VaultSecretsClient
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from temporalio.client import Client as TemporalClient
from temporalio.client import Schedule as TemporalSchedule
from temporalio.client import (
    ScheduleActionStartWorkflow,
    ScheduleUpdateInput,
)
from temporalio.client import ScheduleUpdate as TemporalScheduleUpdate
from temporalio.client import WorkflowExecutionStatus
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode
from workflows import (
    AUTO_HEAL_ATTEMPT_CAP,
    DISCOVERY_TASK_QUEUE,
    EXECUTION_TASK_QUEUE,
    GENERATION_TASK_QUEUE,
    HEAL_CLAIM_STALE_AFTER,
    HEALABLE_STATUSES,
    AddTestCaseWorkflow,
    AddTestCaseWorkflowInput,
    ApplicationTestExecutionWorkflow,
    CleanupWorkflow,
    ExecutionWorkflowInput,
    GenerationWorkflow,
    HealTestActivityInput,
    HealTestExecutionWorkflow,
    ScheduledExecutionWorkflow,
    ScheduledExecutionWorkflowInput,
    SuiteGenerationWorkflow,
)

from api.auth import (
    CurrentAdminDep,
    CurrentOrgIdDep,
    CurrentUserDep,
    clear_session_cookie,
    issue_session_cookie,
    verify_password,
)
from api.coverage_report import build_coverage_report
from api.db import get_session
from api.discovery import pause_discovery_run, resume_discovery_run, start_discovery_run
from api.invites import InviteAcceptError, accept_invite, create_invite, send_invite_email
from api.password_reset import (
    PasswordResetError,
    get_reset_target,
    request_password_reset,
    reset_password,
)
from api.schedule_spec import (
    ScheduleSpecError,
    build_cadence_label,
    build_schedule_policy,
    build_schedule_spec,
    validate_cadence,
)
from api.temporal_client import get_temporal_client, has_pollers
from api.test_suite_export import (
    TestSuiteExportError,
    assemble_test_suite_project,
    find_login_page_evidence,
    sanitize_slug,
)

logger = logging.getLogger(__name__)

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
    role: str


def _to_user_read(user: PlatformUser) -> UserRead:
    return UserRead(name=user.name, email=user.email, role=user.role)


@app.post("/auth/login", response_model=UserRead)
def login(payload: LoginRequest, response: Response, session: SessionDep) -> UserRead:
    user = session.exec(select(PlatformUser).where(PlatformUser.email == payload.email)).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="invalid email or password")
    issue_session_cookie(response, user.id)
    return _to_user_read(user)


@app.post("/auth/logout")
def logout(response: Response) -> dict[str, str]:
    clear_session_cookie(response)
    return {"status": "ok"}


@app.get("/auth/me", response_model=UserRead)
def me(user: CurrentUserDep) -> UserRead:
    return _to_user_read(user)


# --- Invite-only Sign-up ---
# No open self-service registration — an admin sends an Invite (email +
# role), the invitee accepts it via a one-time token link and sets their own
# password. Always joins the inviting admin's existing Organization; there
# is no "create a new org" flow (single-tenant-per-deployment, though the
# schema itself is multi-tenant per AD-12).


class InviteCreate(BaseModel):
    email: str
    role: str = "member"

    @model_validator(mode="after")
    def _valid_role(self) -> InviteCreate:
        if self.role not in ("admin", "member"):
            raise ValueError("role must be 'admin' or 'member'")
        return self


class InviteRead(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime


@app.post("/invites", response_model=InviteRead, status_code=201)
def send_invite(
    payload: InviteCreate,
    session: SessionDep,
    admin: CurrentAdminDep,
    organization_id: CurrentOrgIdDep,
) -> InviteRead:
    existing = session.exec(
        select(PlatformUser).where(PlatformUser.email == payload.email)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="a user with this email already exists")

    invite, token = create_invite(session, organization_id, admin.id, payload.email, payload.role)
    send_invite_email(payload.email, token)
    return InviteRead(
        id=invite.external_id, email=invite.email, role=invite.role, expires_at=invite.expires_at
    )


@app.get("/invites", response_model=list[InviteRead])
def list_pending_invites(
    session: SessionDep,
    admin: CurrentAdminDep,
    organization_id: CurrentOrgIdDep,
) -> list[InviteRead]:
    invites = session.exec(
        select(Invite).where(
            Invite.organization_id == organization_id,
            Invite.used_at.is_(None),  # type: ignore[attr-defined]
        )
    ).all()
    return [
        InviteRead(id=i.external_id, email=i.email, role=i.role, expires_at=i.expires_at)
        for i in invites
    ]


@app.delete("/invites/{external_id}", status_code=204)
def revoke_invite(
    external_id: uuid.UUID,
    session: SessionDep,
    admin: CurrentAdminDep,
    organization_id: CurrentOrgIdDep,
) -> None:
    invite = session.exec(
        select(Invite).where(
            Invite.external_id == external_id, Invite.organization_id == organization_id
        )
    ).first()
    if invite is None:
        raise HTTPException(status_code=404, detail="invite not found")
    session.delete(invite)
    session.commit()


class AcceptInviteRequest(BaseModel):
    token: str
    name: str
    password: str = Field(min_length=8)


@app.post("/invites/accept", response_model=UserRead)
def accept_invite_route(
    payload: AcceptInviteRequest, response: Response, session: SessionDep
) -> UserRead:
    try:
        user = accept_invite(session, payload.token, payload.name, payload.password)
    except InviteAcceptError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    issue_session_cookie(response, user.id)
    return _to_user_read(user)


# --- Forgot password ---
# Public (no session required) — a user enters their email, and if it
# belongs to an account gets a one-time reset link. The response never
# differs based on whether the email exists (no account-enumeration via
# this endpoint), same non-distinguishing rationale as Invite's accept flow.


class ForgotPasswordRequest(BaseModel):
    email: str


@app.post("/auth/forgot-password", status_code=202)
def forgot_password(payload: ForgotPasswordRequest, session: SessionDep) -> dict[str, str]:
    request_password_reset(session, payload.email)
    return {"status": "ok"}


class ResetPasswordTarget(BaseModel):
    name: str
    email: str


@app.get("/auth/reset-password", response_model=ResetPasswordTarget)
def reset_password_target(token: str, session: SessionDep) -> ResetPasswordTarget:
    try:
        user = get_reset_target(session, token)
    except PasswordResetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResetPasswordTarget(name=user.name, email=user.email)


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)


@app.post("/auth/reset-password", response_model=UserRead)
def reset_password_route(payload: ResetPasswordRequest, session: SessionDep) -> UserRead:
    try:
        user = reset_password(session, payload.token, payload.password)
    except PasswordResetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_user_read(user)


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

    @field_validator("username", "password", mode="before")
    @classmethod
    def _strip_credential_whitespace(cls, value: str | None) -> str | None:
        # A stray leading/trailing space (copy-paste artifact) silently
        # breaks login at the target app with no useful error anywhere
        # downstream — strip it here, at the one place these get persisted.
        # Only leading/trailing: an internal space could be a real part of
        # the credential, never touch that.
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _credentials_match_auth_method(self) -> ApplicationCreate:
        if self.auth_method == "standard_login" and not (self.username and self.password):
            raise ValueError("username and password are required for standard_login")
        if self.auth_method == "sso_session_reuse" and not self.session_state:
            raise ValueError("session_state is required for sso_session_reuse")
        return self


class ApplicationRenamePayload(BaseModel):
    name: str


class ApplicationCredentialsUpdatePayload(BaseModel):
    username: str
    password: str

    @field_validator("username", "password", mode="before")
    @classmethod
    def _strip_credential_whitespace(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


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


class HealthRead(BaseModel):
    tier: str
    headline: str


# Single source for the healthy/needs_attention/critical vocabulary — the
# Home card, the per-run badge (TestRunRead.health) and the Overview tab
# (get_overview) all call this instead of each re-deriving the 90%/70%
# cutoffs.
def _health_tier(pass_rate: float | None) -> HealthRead:
    if pass_rate is None:
        return HealthRead(tier="needs_attention", headline="No tests have run yet")
    if pass_rate >= 0.90:
        return HealthRead(tier="healthy", headline=f"{pass_rate:.0%} of tests are passing")
    if pass_rate >= 0.70:
        return HealthRead(tier="needs_attention", headline=f"{pass_rate:.0%} of tests are passing")
    return HealthRead(tier="critical", headline=f"{pass_rate:.0%} of tests are passing")


class HomeApplicationRead(ApplicationRead):
    journey_count: int
    scenario_count: int
    # Dashboard scenario stat: `scenario_count` alone grows mid-generation
    # (GenerationWorkflow runs one per Journey, writing a variable number of
    # Scenarios) — this is `journey_count`'s counterpart so the card can hide
    # the count until every Journey is covered, same as ReviewScenarios.tsx.
    scenario_journeys_covered: int
    # Home card "Running"/"Last run"/pass-rate signals — the most recent
    # TestRun for this application, if one has ever been started. `None`
    # fields mean no run yet, not a zero-value run.
    last_test_run_status: str | None
    last_test_run_created_at: datetime | None
    last_test_run_pass_rate: float | None
    # Only meaningful once `last_test_run_status == "completed"` — mirrors
    # TestRunRead.health so the card's post-execution badge and the Runs tab
    # badge for the same run never disagree.
    last_test_run_health: HealthRead
    # Home row's Executions/Trend columns — total run count (all-time) and
    # the last 8 runs' pass rates, oldest first (same convention as
    # `get_overview`'s `reversed(recent_runs)` trend).
    test_run_count: int
    recent_pass_rates: list[float | None]
    suite_count: int
    test_case_count: int
    # Dashboard "generating" vs "generated" pill: `test_case_count <
    # scenario_count` looked like the right gate (mirrors TestSuiteResults.tsx's
    # count-based check) but a Scenario that's permanently skipped (over the
    # max_test_cases_per_application cap) or failed all its wave retries
    # never contributes a TestAsset — the count then never catches up and the
    # pill reads "Generating test cases" forever after the workflow already
    # finished. This is the same suite.status-based signal TestSuiteResults.tsx's
    # `isComplete` was fixed to use: a suite still mid-run, not a count.
    suites_generating_count: int


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

MAX_ACTIVE_PROJECTS = 4
_PROJECT_LIMIT_DETAIL = f"Maximum of {MAX_ACTIVE_PROJECTS} active projects reached — delete one before adding another."


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
    active_count = len(
        session.exec(
            select(Application).where(
                Application.organization_id == organization_id,
                Application.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        ).all()
    )
    if active_count >= MAX_ACTIVE_PROJECTS:
        raise HTTPException(status_code=409, detail=_PROJECT_LIMIT_DETAIL)

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
            Application.deleted_at.is_(None),  # type: ignore[attr-defined]
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


@app.get("/applications", response_model=list[ApplicationRead])
def list_applications(
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> list[ApplicationRead]:
    applications = session.exec(
        select(Application)
        .where(
            Application.organization_id == organization_id,
            Application.deleted_at.is_(None),  # type: ignore[attr-defined]
        )
        .order_by(Application.created_at.desc())  # type: ignore[arg-type]
    ).all()
    result = []
    for application in applications:
        discovery_run = _latest_discovery_run(session, application.id)
        assert discovery_run is not None
        result.append(_to_application_read(session, application, discovery_run))
    return result


@app.get("/home", response_model=list[HomeApplicationRead])
def get_home(
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> list[HomeApplicationRead]:
    """Home screen used to poll `/applications` plus journeys/scenarios/
    test-suites per application (1+3N calls every tick). One aggregate
    query set instead — the cards only ever needed counts, never the items."""
    applications = session.exec(
        select(Application)
        .where(
            Application.organization_id == organization_id,
            Application.deleted_at.is_(None),  # type: ignore[attr-defined]
        )
        .order_by(Application.created_at.desc())  # type: ignore[arg-type]
    ).all()
    if not applications:
        return []
    app_ids = [a.id for a in applications]

    # Batched in place of the N _latest_discovery_run() calls list_applications makes.
    latest_run_by_app: dict[uuid.UUID, DiscoveryRun] = {}
    for run in session.exec(
        select(DiscoveryRun)
        .where(DiscoveryRun.application_id.in_(app_ids))  # type: ignore[attr-defined]
        .order_by(DiscoveryRun.created_at.desc())  # type: ignore[arg-type]
    ).all():
        latest_run_by_app.setdefault(run.application_id, run)

    # Every TestRun per app (org has at most MAX_ACTIVE_PROJECTS applications,
    # so this stays cheap) — newest first, backs "Running"/"Last run"/
    # pass-rate, the Executions count, and the Trend sparkline all from one
    # query.
    test_runs_by_app: dict[uuid.UUID, list[TestRun]] = {}
    for test_run in session.exec(
        select(TestRun)
        .where(TestRun.application_id.in_(app_ids))  # type: ignore[attr-defined]
        .order_by(TestRun.created_at.desc())  # type: ignore[arg-type]
    ).all():
        test_runs_by_app.setdefault(test_run.application_id, []).append(test_run)

    journey_counts = dict(
        session.exec(
            select(Journey.application_id, func.count())
            .where(
                Journey.application_id.in_(app_ids),  # type: ignore[attr-defined]
                Journey.status == "candidate",
            )
            .group_by(Journey.application_id)  # type: ignore[arg-type]
        ).all()
    )

    app_id_by_journey_id = dict(
        session.exec(
            select(Journey.id, Journey.application_id).where(
                Journey.application_id.in_(app_ids),  # type: ignore[attr-defined]
                Journey.status == "candidate",
            )
        ).all()
    )
    journey_ids = list(app_id_by_journey_id.keys())

    scenario_counts: dict[uuid.UUID, int] = {}
    scenario_journeys_covered: dict[uuid.UUID, int] = {}
    suite_counts: dict[uuid.UUID, int] = {}
    test_case_counts: dict[uuid.UUID, int] = {}
    suites_generating_counts: dict[uuid.UUID, int] = {}
    if journey_ids:
        for journey_id, count in session.exec(
            select(Scenario.journey_id, func.count())
            .where(
                Scenario.journey_id.in_(journey_ids),  # type: ignore[attr-defined]
                Scenario.current.is_(True),  # type: ignore[attr-defined]
            )
            .group_by(Scenario.journey_id)  # type: ignore[arg-type]
        ).all():
            app_id = app_id_by_journey_id[journey_id]
            scenario_counts[app_id] = scenario_counts.get(app_id, 0) + count
            # Grouped by journey_id, so each row here is one Journey that has
            # >=1 current Scenario — same "journeys covered" signal
            # ReviewScenarios.tsx uses to gate its own isComplete.
            scenario_journeys_covered[app_id] = scenario_journeys_covered.get(app_id, 0) + 1
        for journey_id, count in session.exec(
            select(TestSuite.journey_id, func.count())
            .where(
                TestSuite.journey_id.in_(journey_ids),  # type: ignore[attr-defined]
                TestSuite.current.is_(True),  # type: ignore[attr-defined]
            )
            .group_by(TestSuite.journey_id)  # type: ignore[arg-type]
        ).all():
            app_id = app_id_by_journey_id[journey_id]
            suite_counts[app_id] = suite_counts.get(app_id, 0) + count
        for journey_id, count in session.exec(
            select(TestSuite.journey_id, func.count())
            .where(
                TestSuite.journey_id.in_(journey_ids),  # type: ignore[attr-defined]
                TestSuite.current.is_(True),  # type: ignore[attr-defined]
                TestSuite.status == "generating",
            )
            .group_by(TestSuite.journey_id)  # type: ignore[arg-type]
        ).all():
            app_id = app_id_by_journey_id[journey_id]
            suites_generating_counts[app_id] = suites_generating_counts.get(app_id, 0) + count
        for journey_id, count in session.exec(
            select(TestSuite.journey_id, func.count(TestAsset.id))  # type: ignore[arg-type]
            .join(TestAsset, TestAsset.test_suite_id == TestSuite.id)  # type: ignore[arg-type]
            .where(
                TestSuite.journey_id.in_(journey_ids),  # type: ignore[attr-defined]
                TestSuite.current.is_(True),  # type: ignore[attr-defined]
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
            .group_by(TestSuite.journey_id)  # type: ignore[arg-type]
        ).all():
            app_id = app_id_by_journey_id[journey_id]
            test_case_counts[app_id] = test_case_counts.get(app_id, 0) + count

    result = []
    for application in applications:
        discovery_run = latest_run_by_app.get(application.id)
        assert discovery_run is not None
        base = _to_application_read(session, application, discovery_run)
        runs = test_runs_by_app.get(application.id, [])
        last_test_run = runs[0] if runs else None
        last_test_run_pass_rate = (
            last_test_run.passed_count / last_test_run.total_count
            if last_test_run and last_test_run.total_count
            else None
        )
        result.append(
            HomeApplicationRead(
                **base.model_dump(),
                journey_count=journey_counts.get(application.id, 0),
                scenario_count=scenario_counts.get(application.id, 0),
                scenario_journeys_covered=scenario_journeys_covered.get(application.id, 0),
                suite_count=suite_counts.get(application.id, 0),
                test_case_count=test_case_counts.get(application.id, 0),
                suites_generating_count=suites_generating_counts.get(application.id, 0),
                last_test_run_status=last_test_run.status if last_test_run else None,
                last_test_run_created_at=last_test_run.created_at if last_test_run else None,
                last_test_run_pass_rate=last_test_run_pass_rate,
                last_test_run_health=_health_tier(last_test_run_pass_rate),
                test_run_count=len(runs),
                recent_pass_rates=[
                    (r.passed_count / r.total_count) if r.total_count else None
                    for r in reversed(runs[:8])
                ],
            )
        )
    return result


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


# `start_discovery_run` only checks `has_pollers` before starting (same
# staleness-window gap `generation-status` closes for generation) — a worker
# that crashes right after leaves `discovery_status="running"` with nothing
# to explain why it's never going to move. Only meaningful while running;
# any other status already has its own terminal reason.
@app.get("/applications/{external_id}/discovery-status")
async def discovery_status(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> dict[str, bool | int]:
    application = _get_org_application(session, organization_id, external_id)
    discovery_run = _latest_discovery_run(session, application.id)
    if discovery_run is None or discovery_run.status != "running":
        return {"available": True, "retry_count": 0}
    client = await get_temporal_client()
    available = await has_pollers(client, DISCOVERY_TASK_QUEUE)

    # DISC-001 is the "Temporal restarted this run after a crash" diagnostic
    # (activities.py's `is_temporal_retry` branch) — already written to the
    # DB, previously only surfaced after the fact in the coverage report.
    # Reusing that same row here is what lets the polling UI tell the user
    # "recovered from a worker restart" live instead of silently retrying.
    from domain import DiscoveryError

    last_retry = session.exec(
        select(DiscoveryError)
        .where(
            DiscoveryError.discovery_run_id == discovery_run.id,
            DiscoveryError.error_code == "DISC-001",
        )
        .order_by(DiscoveryError.created_at.desc())  # type: ignore[attr-defined]
        .limit(1)
    ).first()
    return {"available": available, "retry_count": last_retry.retry_count if last_retry else 0}


@app.patch("/applications/{external_id}", response_model=ApplicationRead)
def rename_application(
    external_id: uuid.UUID,
    payload: ApplicationRenamePayload,
    session: SessionDep,
    _admin: CurrentAdminDep,
    organization_id: CurrentOrgIdDep,
) -> ApplicationRead:
    application = _get_org_application(session, organization_id, external_id)
    application.name = payload.name
    session.add(application)
    session.commit()
    discovery_run = _latest_discovery_run(session, application.id)
    assert discovery_run is not None
    return _to_application_read(session, application, discovery_run)


@app.patch("/applications/{external_id}/credentials", response_model=ApplicationRead)
def update_application_credentials(
    external_id: uuid.UUID,
    payload: ApplicationCredentialsUpdatePayload,
    session: SessionDep,
    _admin: CurrentAdminDep,
    organization_id: CurrentOrgIdDep,
) -> ApplicationRead:
    """Rotates a standard_login Application's stored credential in place —
    overwrites the same Vault path (secret_ref never changes) rather than
    minting a new one, no login validation before saving. sso_session_reuse
    apps aren't supported here (a session_state blob, not a username/
    password, isn't what this form collects)."""
    application = _get_org_application(session, organization_id, external_id)
    if application.auth_method != "standard_login":
        raise HTTPException(
            status_code=422, detail="credential update is only supported for standard_login"
        )
    creds = {"username": payload.username, "password": payload.password}
    VaultSecretsClient().update(SecretRef(path=application.secret_ref), json.dumps(creds).encode())
    discovery_run = _latest_discovery_run(session, application.id)
    assert discovery_run is not None
    return _to_application_read(session, application, discovery_run)


@app.delete("/applications/{external_id}", status_code=204)
async def delete_application(
    external_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentAdminDep,
    organization_id: CurrentOrgIdDep,
) -> None:
    """Soft delete only (AD-15 disclosed scope) — child rows (discovery_run,
    journey, page, ...) and the Vault secret are deliberately left behind;
    nothing purges them yet. Blocked while discovery is running so a live
    crawler doesn't keep writing rows for an application that just
    disappeared from Home.

    Schedules feature: also pauses every live Temporal Schedule for this
    Application, so no future scheduled occurrence gets created. Best
    effort — a soft-delete must never be blocked by Temporal being
    unreachable, and `check_schedule_gate_activity`'s own
    Application-active check is the backstop that makes a missed pause
    harmless (see that activity's docstring). In-progress executions this
    schedule already fired are deliberately NOT cancelled."""
    application = _get_org_application(session, organization_id, external_id)
    discovery_run = _latest_discovery_run(session, application.id)
    if discovery_run is not None and discovery_run.status == "running":
        raise HTTPException(status_code=409, detail="discovery run is still in progress")
    application.deleted_at = datetime.now(UTC)
    session.add(application)

    schedules = session.exec(
        select(Schedule).where(
            Schedule.application_id == application.id,
            Schedule.deleted_at.is_(None),  # type: ignore[attr-defined]
        )
    ).all()
    if schedules:
        try:
            client = await get_temporal_client()
            for schedule in schedules:
                try:
                    await client.get_schedule_handle(schedule.temporal_schedule_id).pause(
                        note="application deleted"
                    )
                    schedule.enabled = False
                    session.add(schedule)
                except RPCError as exc:
                    if exc.status != RPCStatusCode.NOT_FOUND:
                        logger.warning(
                            "could not pause Temporal schedule %s during application delete",
                            schedule.temporal_schedule_id,
                        )
        except RuntimeError:
            logger.warning(
                "Temporal unreachable during application delete — schedules left unpaused; "
                "the fire-time gate will skip them via the Application-active check"
            )

    session.commit()


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
    screenshot_url: str | None = None


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


# Journeys are created in navigation-cluster/batch order (InferenceActivity),
# not app-flow order, so display order sorts by when each journey's entry
# step's target was first discovered by the crawl instead — that puts login
# (visited first) ahead of the modules behind it. Shared by list_journeys and
# list_scenarios so both screens agree on the same order.
def _order_journeys_by_app_flow(session: Session, journeys: list[Journey]) -> list[Journey]:
    if not journeys:
        return journeys
    entry_steps = {
        s.journey_id: s
        for s in session.exec(
            select(JourneyStep).where(
                JourneyStep.journey_id.in_([j.id for j in journeys]),  # type: ignore[attr-defined]
                JourneyStep.step_order == 1,
            )
        ).all()
    }
    component_ids = {s.component_id for s in entry_steps.values() if s.component_id}
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
    page_ids = {s.page_id for s in entry_steps.values() if s.page_id} | {
        c.page_id for c in components.values()
    }
    form_ids = {s.form_id for s in entry_steps.values() if s.form_id}
    api_endpoint_ids = {s.api_endpoint_id for s in entry_steps.values() if s.api_endpoint_id}
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

    def _entry_discovered_at(journey: Journey) -> datetime:
        step = entry_steps.get(journey.id)
        if step is None:
            return journey.created_at
        target = (
            pages.get(step.page_id)
            if step.page_id
            else forms.get(step.form_id)
            if step.form_id
            else api_endpoints.get(step.api_endpoint_id)
            if step.api_endpoint_id
            else pages.get(components[step.component_id].page_id)
            if step.component_id and step.component_id in components
            else None
        )
        return target.created_at if target is not None else journey.created_at

    return sorted(journeys, key=_entry_discovered_at)


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

    journeys = _order_journeys_by_app_flow(session, journeys)

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

    # Only the final step gets a screenshot (product decision — not every
    # step, just the journey's end state). Form/API-endpoint steps have no
    # associated Page, so no screenshot is available for those.
    if result:
        last_step = steps[-1]
        last_page = (
            pages.get(last_step.page_id)
            if last_step.page_id
            else pages.get(components[last_step.component_id].page_id)
            if last_step.component_id
            else None
        )
        if last_page is not None and last_page.object_storage_key:
            result[-1].screenshot_url = ObjectStore().presigned_get_url(
                last_page.object_storage_key,
                response_content_type="image/png",
                filename="screenshot.png",
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
    # Starting a workflow succeeds regardless of whether a worker is polling
    # the queue — check up front so a dead generation worker pod surfaces as
    # a real error instead of a silent no-op the frontend can't distinguish
    # from "still generating".
    if not await has_pollers(client, GENERATION_TASK_QUEUE):
        raise HTTPException(status_code=503, detail="GENERATION_UNAVAILABLE")
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
                # `already_generated` above is checked, then this call races
                # against any other in-flight trigger for the same Journey/
                # attempt (e.g. a double-submitted "Continue to Scenarios"
                # request) — the default reuse policy lets a second start
                # succeed once the first run has already CLOSED, silently
                # re-running ScenarioGenerationActivity and duplicating every
                # Scenario it wrote. Rejecting outright makes the same-
                # attempt workflow id truly once-only; a genuine retry still
                # works because `journey.attempt` increments into a new id.
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
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

    # Same app-flow order as list_journeys, so scenarios group under login's
    # journey first, then the next module's, etc. — matching how the user
    # sees journeys ordered on the previous screen.
    journey_order = {j.id: i for i, j in enumerate(_order_journeys_by_app_flow(session, journeys))}
    scenarios = sorted(scenarios, key=lambda s: journey_order.get(s.journey_id, len(journey_order)))

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
    description: str
    code: str
    # NLM "Add Test Case" feature — 'discovery' (normal Discovery -> Journey
    # -> Scenario pipeline) or 'nlm' (created ad hoc from a plain-English
    # request). Every pre-existing Scenario is 'discovery' (migration
    # 584191e291e5's server_default) — never relabeled.
    source: str


class TestSuiteRead(BaseModel):
    id: uuid.UUID
    name: str
    journey_name: str
    status: str
    test_cases: list[TestCaseRead]


class TestCaseCreate(BaseModel):
    # Everything is prompt-based — no separate test-data field. Any concrete
    # value the user wants used (e.g. "using promo code EXPIRED10") is
    # extracted from `prompt` itself by AnalyzePromptActivity; anything not
    # mentioned is resolved from the existing Test Data Pool or synthesized
    # by PlaywrightGenerationActivity's own existing default-value logic,
    # exactly like every normal-flow Scenario.
    prompt: str


class TestCaseGenerationResultRead(BaseModel):
    """One Scenario's own outcome — a single prompt can decompose into
    several (Multiple Test Cases), each independently PASS/FAIL."""

    status: str  # complete | failed
    journey_name: str | None = None
    scenario_name: str | None = None
    test_result_status: str | None = None
    error_message: str | None = None
    # True when this Scenario already existed and was matched/reused as-is —
    # never (re)generated or re-run. Lets the UI distinguish "matched to an
    # existing test case" from "newly generated".
    already_existed: bool = False
    # True only for a genuinely new Journey this request created — lets the
    # UI say which Journey was newly created, not just name it like any
    # other (New Journey grouping is a success, never a failure by itself).
    is_new_journey: bool = False
    # NLM Matching and Creation Rules — True for a brand-new Scenario
    # (existing Journey or one just created for it); False for a genuine
    # `reuse_scenario` match. Meaningless once `already_existed` or
    # `is_new_journey` is True — the UI checks those first.
    is_new_scenario: bool = False
    # Set only for `status="failed"` — names which step actually blocked
    # creation (e.g. "Scenario match", "Code generation").
    stage: str | None = None


class TestCaseRequestStatusRead(BaseModel):
    request_id: str
    status: str  # analyzing | generating | complete | failed | rejected — overall
    functionality_summary: str = ""
    rejection_reason: str | None = None
    error_message: str | None = None
    # How many Scenarios were identified once analysis finishes — lets the UI
    # say "Building 3 test cases…" instead of looking identical to a
    # single-Scenario request while it runs.
    scenario_count: int = 0
    results: list[TestCaseGenerationResultRead] = Field(default_factory=list)


def _add_test_case_workflow_id(application_external_id: uuid.UUID, request_id: uuid.UUID) -> str:
    return f"add-test-case-{application_external_id}-{request_id}"


# NLM "Add Test Case" feature — no DB table backs the request itself (see
# `AddTestCaseWorkflow`'s own docstring): the workflow's `@workflow.query`
# ("still running") and its own return value (`.result()`, once terminal) are
# the only record of a request's status. `request_id` is a fresh `uuid4()`
# minted here, not a DB id.
@app.post("/applications/{external_id}/test-cases", status_code=202)
async def create_test_case(
    external_id: uuid.UUID,
    payload: TestCaseCreate,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> dict[str, str]:
    application = _get_org_application(session, organization_id, external_id)

    # Add Test Case Tab: server-side mirror of the frontend's own "show only
    # once a TestSuite exists" gate.
    has_suite = session.exec(
        select(TestSuite)
        .join(Journey, Journey.id == TestSuite.journey_id)  # type: ignore[arg-type]
        .where(Journey.application_id == application.id)
        .limit(1)
    ).first()
    if has_suite is None:
        raise HTTPException(status_code=400, detail="NO_TEST_SUITE")

    client = await get_temporal_client()
    if not await has_pollers(client, GENERATION_TASK_QUEUE):
        raise HTTPException(status_code=503, detail="GENERATION_UNAVAILABLE")

    request_id = uuid.uuid4()
    await client.start_workflow(
        AddTestCaseWorkflow.run,
        AddTestCaseWorkflowInput(
            application_id=str(external_id),
            prompt=payload.prompt,
        ),
        id=_add_test_case_workflow_id(external_id, request_id),
        task_queue=GENERATION_TASK_QUEUE,
    )
    return {"request_id": str(request_id)}


@app.get("/applications/{external_id}/test-cases/requests/{request_id}")
async def get_test_case_request(
    external_id: uuid.UUID,
    request_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> TestCaseRequestStatusRead:
    _get_org_application(session, organization_id, external_id)
    client = await get_temporal_client()
    handle = client.get_workflow_handle_for(
        AddTestCaseWorkflow.run, _add_test_case_workflow_id(external_id, request_id)
    )
    try:
        desc = await handle.describe()
    except Exception as exc:
        raise HTTPException(status_code=404, detail="TEST_CASE_REQUEST_NOT_FOUND") from exc

    if desc.status == WorkflowExecutionStatus.RUNNING:
        status = await handle.query(AddTestCaseWorkflow.get_status)
        return TestCaseRequestStatusRead(
            request_id=str(request_id),
            status=status.status,
            functionality_summary=status.functionality_summary,
            rejection_reason=status.rejection_reason,
            scenario_count=status.scenario_count,
        )

    if desc.status == WorkflowExecutionStatus.COMPLETED:
        result = await handle.result()
        return TestCaseRequestStatusRead(
            request_id=str(request_id),
            status=result.status,
            rejection_reason=result.rejection_reason,
            error_message=result.error_message,
            scenario_count=len(result.results),
            results=[
                TestCaseGenerationResultRead(
                    status=r.status,
                    journey_name=r.journey_name,
                    scenario_name=r.scenario_name,
                    test_result_status=r.test_result_status,
                    error_message=r.error_message,
                    already_existed=r.already_existed,
                    is_new_journey=r.is_new_journey,
                    is_new_scenario=r.is_new_scenario,
                    stage=r.stage,
                )
                for r in result.results
            ],
        )

    # A genuine Temporal-level failure (exhausted an Activity's own retries
    # past what the workflow itself catches, worker crash mid-execution,
    # etc.) — the workflow's own try/except already turns ordinary Activity
    # failures into a `status="failed"` *result* (still COMPLETED above);
    # only reaching here means something the workflow couldn't catch at all.
    return TestCaseRequestStatusRead(
        request_id=str(request_id),
        status="failed",
        error_message=f"the request did not finish normally (workflow status: {desc.status.name})",
    )


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
    if not await has_pollers(client, GENERATION_TASK_QUEUE):
        raise HTTPException(status_code=503, detail="GENERATION_UNAVAILABLE")
    triggered = 0
    for journey in journeys:
        current_scenarios = session.exec(
            select(Scenario).where(
                Scenario.journey_id == journey.id,
                Scenario.current.is_(True),  # type: ignore[attr-defined]
            )
        ).all()
        if not current_scenarios:
            # Scenario generation itself can permanently fail a Journey
            # (GenerationWorkflow has no per-scenario fault isolation, unlike
            # SuiteGenerationWorkflow) — it stays "candidate" with 0 current
            # Scenarios forever. Without a same-shape terminal TestSuite row
            # here, that Journey counts toward the frontend's expected-journey
            # total but never contributes a suite row, so the results screen's
            # `isComplete` check can never pass and the loader spins forever.
            existing = session.exec(
                select(TestSuite).where(
                    TestSuite.journey_id == journey.id,
                    TestSuite.generation_run_id == journey.attempt,
                )
            ).first()
            if existing is None:
                session.add(
                    TestSuite(
                        journey_id=journey.id,
                        name=f"{journey.name} Test Suite",
                        generation_run_id=journey.attempt,
                        current=True,
                        status="incomplete",
                    )
                )
                session.commit()
            continue
        # Idempotent, but scoped to "every current Scenario already has a
        # TestAsset" rather than "a TestSuite row exists" — SuiteGeneration-
        # Workflow's own fault isolation (one Scenario's PlaywrightGeneration
        # failing all 3 retries doesn't fail the Journey) means a TestSuite
        # can exist with some Scenarios never getting a TestAsset. Checking
        # TestSuite existence alone made that permanent: re-clicking Generate
        # Suite skipped the Journey forever, no way to resume. Re-running is
        # safe either way — EnsureTestSuiteActivity/PlaywrightGenerationActivity
        # are both idempotent per Journey/Scenario.
        suites = session.exec(
            select(TestSuite).where(
                TestSuite.journey_id == journey.id,
                TestSuite.generation_run_id == journey.attempt,
            )
        ).all()
        # A user explicitly closed this Journey's incomplete suite out
        # (`terminate_test_suite`) — that decision must stick; re-clicking
        # Generate Suite must not silently start retrying it again.
        if any(ts.status == "terminated" for ts in suites):
            continue
        suite_ids = [ts.id for ts in suites]
        covered_scenario_ids = (
            set(
                session.exec(
                    select(TestAsset.scenario_id).where(
                        TestAsset.test_suite_id.in_(suite_ids),  # type: ignore[attr-defined]
                        TestAsset.current.is_(True),  # type: ignore[attr-defined]
                    )
                ).all()
            )
            if suite_ids
            else set()
        )
        if all(s.id in covered_scenario_ids for s in current_scenarios):
            continue
        # Flip back to "generating" so the frontend's existing loader/
        # polling reappears for this retry instead of the screen staying on
        # the (stale) terminal status until this new attempt also finishes.
        for ts in suites:
            if ts.status != "terminated":
                ts.status = "generating"
                session.add(ts)
        if suites:
            session.commit()
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


# `has_pollers` at submit time can't catch a worker that crashes right after
# (its own docstring: a crashed poller stays "seen" for Temporal's staleness
# window, a few minutes) — the Test Suite Results screen polls this
# separately so it can stop spinning once that window clears and the worker
# is confirmed gone, instead of waiting on a generation that will never move.
@app.get("/applications/{external_id}/generation-status")
async def generation_status(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> dict[str, bool]:
    _get_org_application(session, organization_id, external_id)
    client = await get_temporal_client()
    return {"available": await has_pollers(client, GENERATION_TASK_QUEUE)}


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
    # `Scenario.current` matters here: a superseded Scenario (edited/
    # regenerated, old row flipped non-current) can still have a TestAsset
    # that was never invalidated. Without this filter that stale asset counts
    # as a live test case here even though list_scenarios (Scenario.current
    # only) already dropped it — the exact source of the two screens'
    # counts drifting apart.
    scenarios_by_id = {
        s.id: s
        for s in (
            session.exec(
                select(Scenario).where(
                    Scenario.id.in_(scenario_ids),  # type: ignore[attr-defined]
                    Scenario.current.is_(True),  # type: ignore[attr-defined]
                )
            ).all()
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
                    id=asset.external_id,
                    name=scenario.name,
                    type=scenario.type,
                    description=scenario.expected_result,
                    code=asset.code,
                    source=scenario.source,
                )
            )
        result.append(
            TestSuiteRead(
                id=test_suite.external_id,
                name=test_suite.name,
                journey_name=journey.name,
                status=test_suite.status,
                test_cases=test_cases,
            )
        )
    return result


@app.post("/applications/{external_id}/test-suites/{suite_id}/terminate", response_model=TestSuiteRead)
def terminate_test_suite(
    external_id: uuid.UUID,
    suite_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> TestSuiteRead:
    """User-triggered alternative to re-clicking Generate Suite forever
    (`generate_suite`'s own comment: a TestSuite left 'incomplete' is
    otherwise silently re-triggerable, with no way to just call it done).
    Only valid from 'incomplete' — a 'generating' suite is still legitimately
    in flight, and a 'complete'/already-'terminated' one has nothing to
    terminate."""
    application = _get_org_application(session, organization_id, external_id)
    test_suite = session.exec(
        select(TestSuite).where(TestSuite.external_id == suite_id)
    ).first()
    if test_suite is None:
        raise HTTPException(status_code=404, detail="test suite not found")
    journey = session.get(Journey, test_suite.journey_id)
    if journey is None or journey.application_id != application.id:
        raise HTTPException(status_code=404, detail="test suite not found")
    if test_suite.status != "incomplete":
        raise HTTPException(
            status_code=409, detail=f"cannot terminate a suite with status {test_suite.status!r}"
        )

    test_suite.status = "terminated"
    session.add(test_suite)
    session.commit()
    session.refresh(test_suite)

    test_cases = [
        TestCaseRead(
            id=asset.external_id,
            name=scenario.name,
            type=scenario.type,
            description=scenario.expected_result,
            code=asset.code,
            source=scenario.source,
        )
        for asset in session.exec(
            select(TestAsset).where(
                TestAsset.test_suite_id == test_suite.id,
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).all()
        if (scenario := session.get(Scenario, asset.scenario_id)) is not None
    ]
    return TestSuiteRead(
        id=test_suite.external_id,
        name=test_suite.name,
        journey_name=journey.name,
        status=test_suite.status,
        test_cases=test_cases,
    )


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
        # See list_test_suites for why Scenario.current is required here too.
        scenarios_by_id = {
            s.id: s
            for s in session.exec(
                select(Scenario).where(
                    Scenario.id.in_(scenario_ids),  # type: ignore[attr-defined]
                    Scenario.current.is_(True),  # type: ignore[attr-defined]
                )
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


class ExecutionPolicyRead(BaseModel):
    execution_enabled: bool
    allowed_base_urls: list[str]
    destructive_actions_permitted: bool
    video_capture_enabled: bool
    version: int


class ExecutionPolicyUpdate(BaseModel):
    execution_enabled: bool | None = None
    allowed_base_urls: list[str] | None = None
    destructive_actions_permitted: bool | None = None
    video_capture_enabled: bool | None = None


def _to_execution_policy_read(policy: ExecutionPolicy) -> ExecutionPolicyRead:
    return ExecutionPolicyRead(
        execution_enabled=policy.execution_enabled,
        allowed_base_urls=policy.allowed_base_urls,
        destructive_actions_permitted=policy.destructive_actions_permitted,
        video_capture_enabled=policy.video_capture_enabled,
        version=policy.version,
    )


@app.get(
    "/applications/{external_id}/execution-policy",
    response_model=ExecutionPolicyRead,
)
def get_execution_policy(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> ExecutionPolicyRead:
    application = _get_org_application(session, organization_id, external_id)
    policy = session.exec(
        select(ExecutionPolicy).where(ExecutionPolicy.application_id == application.id)
    ).first()
    if policy is None:
        raise HTTPException(status_code=404, detail="no execution policy configured yet")
    return _to_execution_policy_read(policy)


@app.put(
    "/applications/{external_id}/execution-policy",
    response_model=ExecutionPolicyRead,
)
def update_execution_policy(
    external_id: uuid.UUID,
    payload: ExecutionPolicyUpdate,
    session: SessionDep,
    _admin: CurrentAdminDep,
    organization_id: CurrentOrgIdDep,
) -> ExecutionPolicyRead:
    """Upsert — without this, "Run All Tests" has nothing to validate a run
    against and can never be clickable (decision from the grill-me design
    review). `version` is bumped on every field change, never on a no-op
    PUT, so a `TestRun`'s `execution_policy_version` snapshot stays a
    meaningful "was this the policy in effect" marker."""
    application = _get_org_application(session, organization_id, external_id)
    policy = session.exec(
        select(ExecutionPolicy).where(ExecutionPolicy.application_id == application.id)
    ).first()
    is_new = policy is None
    if policy is None:
        policy = ExecutionPolicy(application_id=application.id)

    changed = False
    for field_name in (
        "execution_enabled",
        "allowed_base_urls",
        "destructive_actions_permitted",
        "video_capture_enabled",
    ):
        value = getattr(payload, field_name)
        if value is not None and value != getattr(policy, field_name):
            setattr(policy, field_name, value)
            changed = True

    if changed and not is_new:
        policy.version += 1
    policy.updated_at = datetime.now(UTC)
    session.add(policy)
    session.commit()
    session.refresh(policy)
    return _to_execution_policy_read(policy)


class TestResultRead(BaseModel):
    id: uuid.UUID
    scenario_name: str
    status: str
    duration_ms: int | None
    error_message: str | None
    stack_trace: str | None
    blocked_reason: str | None
    # Two independent budgets, never combined — see TestResult's own
    # comment (packages/domain/src/domain/test_result.py). auto_* is spent
    # only by automatic healing, capped at auto_heal_attempt_cap (the fixed
    # AUTO_HEAL_ATTEMPT_CAP constant); manual_* is spent only by the
    # "Retry with self-healing" endpoint, capped at max_heal_attempts.
    auto_heal_attempt_count: int
    manual_heal_attempt_count: int
    healed_test_asset_id: uuid.UUID | None
    auto_heal_attempt_cap: int
    # The current DiscoverySettings.max_heal_attempts, read alongside every
    # TestResult rather than requiring a second call to admin-only
    # GET /settings — RunsTab (any authenticated org member) needs this to
    # render self-heal button/messaging state correctly.
    max_heal_attempts: int


class TestRunRead(BaseModel):
    id: uuid.UUID
    run_number: int
    status: str
    trigger: str
    pass_rate: float | None
    # Same 3-tier vocabulary as the Overview health badge (`_health_tier`) —
    # one source of truth reused here rather than a 4th place hardcoding the
    # 90%/70% cutoffs (Home.tsx and RunsTab.tsx's border color already did).
    health: HealthRead
    total_count: int
    passed_count: int
    failed_count: int
    timed_out_count: int
    errored_count: int
    blocked_count: int
    blocked_reason: str | None
    environment_snapshot: str
    target_base_url_snapshot: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    results: list[TestResultRead] | None = None


class TestResultArtifactRead(BaseModel):
    id: uuid.UUID
    artifact_type: str
    content_type: str
    size_bytes: int
    url: str


def _trigger_label(test_run: TestRun) -> str:
    """One formatted "trigger" string, shared by `TestRunRead.trigger` and
    the Overview tab's `LatestRunSummaryRead.trigger` (see that field's own
    docstring) — one place that knows the format, not two drifting copies.

    Schedules feature: `schedule_id is not None` means this run was started
    by `ScheduledExecutionWorkflow`, not a human click — `triggered_by_name`
    already holds the schedule's *name at fire time* in that case (a
    snapshot, same principle as `environment_snapshot`), so no join is
    needed here."""
    if test_run.schedule_id is not None and test_run.triggered_by_name:
        return f"Scheduled run — {test_run.triggered_by_name}"
    if test_run.triggered_by_name:
        return f"Manual run by {test_run.triggered_by_name}"
    return "Manual run"


def _to_test_run_read(
    test_run: TestRun, *, results: list[TestResultRead] | None
) -> TestRunRead:
    pass_rate = (
        test_run.passed_count / test_run.total_count if test_run.total_count else None
    )
    return TestRunRead(
        id=test_run.external_id,
        run_number=test_run.run_number,
        status=test_run.status,
        trigger=_trigger_label(test_run),
        pass_rate=pass_rate,
        health=_health_tier(pass_rate),
        total_count=test_run.total_count,
        passed_count=test_run.passed_count,
        failed_count=test_run.failed_count,
        timed_out_count=test_run.timed_out_count,
        errored_count=test_run.errored_count,
        blocked_count=test_run.blocked_count,
        blocked_reason=test_run.blocked_reason,
        environment_snapshot=test_run.environment_snapshot,
        target_base_url_snapshot=test_run.target_base_url_snapshot,
        created_at=test_run.created_at,
        started_at=test_run.started_at,
        completed_at=test_run.completed_at,
        results=results,
    )


@app.post("/applications/{external_id}/test-runs", status_code=202)
async def trigger_test_run(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
    user: CurrentUserDep,
) -> dict[str, bool]:
    """No body — every "Run All Tests" click is a fresh, full-scope run
    covering every current TestAsset for the application (no rerun-scoped
    mode). `PrepareTestRunActivity` creates the actual `TestRun` row
    asynchronously, so the very first `GET .../test-runs` poll may briefly
    see nothing yet — the same gap `TestSuiteResults.tsx`'s existing poll
    loop already tolerates for generation.

    ponytail: no `ExecutionPolicy` precondition check here anymore —
    removed per explicit request so this never needs setup before it can
    be clicked. `GET`/`PUT .../execution-policy` below still exist; nothing
    on this path reads them. To restore the original gate: re-add a
    `select(ExecutionPolicy)...` lookup and 409 when it's missing (see git
    history for the removed version)."""
    application = _get_org_application(session, organization_id, external_id)

    client = await get_temporal_client()
    if not await has_pollers(client, EXECUTION_TASK_QUEUE):
        raise HTTPException(status_code=503, detail="EXECUTION_UNAVAILABLE")
    await client.start_workflow(
        ApplicationTestExecutionWorkflow.run,
        ExecutionWorkflowInput(
            application_id=str(application.external_id), triggered_by_name=user.name
        ),
        # Every run is a genuinely new TestRun (no rerun/idempotency key the
        # way suite-{journey_id}-{attempt} has) — the id only needs to be
        # unique, never deterministic/replayable.
        id=f"execution-{application.external_id}-{uuid.uuid4()}",
        task_queue=EXECUTION_TASK_QUEUE,
    )
    return {"started": True}


@app.post("/admin/cleanup/run", status_code=202)
async def trigger_cleanup(admin: CurrentAdminDep) -> dict[str, bool]:
    """Manual purge trigger — same CleanupWorkflow the daily 06:00 IST
    Schedule (`api/scripts/create_cleanup_schedule.py`) runs, folded onto
    execution-worker's task queue (no dedicated maintenance worker/deployment;
    see that worker's registered workflows). Unique per-call id (not the
    Schedule's fixed `cleanup-deleted-applications` id) so a manual run never
    collides with a same-day scheduled run."""
    client = await get_temporal_client()
    if not await has_pollers(client, EXECUTION_TASK_QUEUE):
        raise HTTPException(status_code=503, detail="EXECUTION_UNAVAILABLE")
    await client.start_workflow(
        CleanupWorkflow.run,
        id=f"cleanup-manual-{uuid.uuid4()}",
        task_queue=EXECUTION_TASK_QUEUE,
    )
    return {"started": True}


# `has_pollers` above is only checked before starting the workflow — a
# worker that crashes right after leaves the TestRun sitting at "running"
# with nothing to explain why (same staleness-window gap `generation-status`/
# `discovery-status` close for their own workers). Polled separately so
# RunsTab can stop spinning once the worker is confirmed gone.
@app.get("/applications/{external_id}/execution-status")
async def execution_status(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> dict[str, bool]:
    _get_org_application(session, organization_id, external_id)
    client = await get_temporal_client()
    return {"available": await has_pollers(client, EXECUTION_TASK_QUEUE)}


# --------------------------------------------------------------------------
# Schedules feature — user-created recurring triggers for "Run All Tests".
#
# Source of truth split: Postgres owns what the user authored (name,
# cadence fields); Temporal owns whether it's firing (`Schedule.enabled` is
# a cached projection of `ScheduleState.paused`). Every mutation calls
# Temporal first, then commits Postgres — an ahead-of-Temporal-only residue
# is a harmless no-op (the fire-time gate returns `schedule_unavailable`);
# the reverse order's residue would be an invisible, permanently-non-firing
# DB row. See `list_schedules` (below) for the reconciliation read and
# `create_schedule`/`update_schedule` for the compensating actions on a
# post-Temporal-success Postgres commit failure.
#
# Accepted v1 limitation: no custom worker-down timeout is set on the
# Schedule's action (`_build_schedule_action`) — if the execution worker is
# offline at fire time, Temporal creates the workflow and its first task
# simply stays pending until a worker polls it. Because the schedule's own
# `overlap=SKIP` policy treats that stuck-open occurrence as "still
# running," every occurrence that would fire during the outage is skipped,
# not queued or backfired — only the first occurrence that fired at
# outage-start ever actually runs, once a worker returns. See
# `schedule_spec.build_schedule_policy`'s docstring for the full mechanism.
# --------------------------------------------------------------------------


class ScheduleCreate(BaseModel):
    name: str
    cadence_type: str
    hour: int | None = None
    minute: int | None = None
    days_of_week: list[int] = []
    day_of_month: int | None = None
    cron_expression: str | None = None
    time_zone: str


class ScheduleUpdate(BaseModel):
    """Every field optional — PATCH-merge, only non-None values applied,
    same convention as TestDataEntryUpdate. The merged result is then
    re-validated as a whole by `validate_cadence` (never just the supplied
    fields), so switching cadence_type without supplying the fields the new
    cadence needs is a clean 422 rather than a half-migrated row. No
    optimistic concurrency control (no version/ETag) — concurrent PATCHes
    are last-`commit()`-wins, an accepted low-severity v1 race."""

    name: str | None = None
    cadence_type: str | None = None
    hour: int | None = None
    minute: int | None = None
    days_of_week: list[int] | None = None
    day_of_month: int | None = None
    cron_expression: str | None = None
    time_zone: str | None = None


class ScheduleRead(BaseModel):
    id: uuid.UUID
    name: str
    cadence_type: str
    hour: int | None
    minute: int | None
    days_of_week: list[int]
    day_of_month: int | None
    cron_expression: str | None
    time_zone: str
    enabled: bool
    cadence_label: str
    next_run_at: datetime | None
    created_by_name: str | None
    created_at: datetime


def _to_schedule_read(
    schedule: Schedule, *, enabled: bool, next_run_at: datetime | None
) -> ScheduleRead:
    return ScheduleRead(
        id=schedule.external_id,
        name=schedule.name,
        cadence_type=schedule.cadence_type,
        hour=schedule.hour,
        minute=schedule.minute,
        days_of_week=schedule.days_of_week,
        day_of_month=schedule.day_of_month,
        cron_expression=schedule.cron_expression,
        time_zone=schedule.time_zone,
        enabled=enabled,
        cadence_label=build_cadence_label(schedule),
        next_run_at=next_run_at,
        created_by_name=schedule.created_by_name,
        created_at=schedule.created_at,
    )


def _get_org_schedule(
    session: Session, organization_id: uuid.UUID, external_id: uuid.UUID
) -> Schedule:
    """Same two-hop org check `_get_org_application`'s siblings use for a
    child row that carries no organization_id of its own."""
    schedule = session.exec(
        select(Schedule).where(
            Schedule.external_id == external_id,
            Schedule.deleted_at.is_(None),  # type: ignore[attr-defined]
        )
    ).first()
    application = session.get(Application, schedule.application_id) if schedule else None
    if (
        schedule is None
        or application is None
        or application.organization_id != organization_id
        or application.deleted_at is not None
    ):
        raise HTTPException(status_code=404, detail="schedule not found")
    return schedule


def _build_schedule_action(
    schedule: Schedule, application_external_id: uuid.UUID
) -> ScheduleActionStartWorkflow:
    """The Temporal action for a schedule. Rebuilt on every update, not
    just create — the workflow args carry the schedule's *name*, which
    becomes the run's `triggered_by_name` snapshot, so a rename has to
    propagate. No execution_timeout/run_timeout set — see this module's own
    accepted-limitation note above."""
    return ScheduleActionStartWorkflow(
        ScheduledExecutionWorkflow.run,
        ScheduledExecutionWorkflowInput(
            application_id=str(application_external_id),
            schedule_id=str(schedule.external_id),
            schedule_name=schedule.name,
        ),
        # Temporal appends the scheduled time to this id, so each occurrence
        # gets a distinct, meaningful workflow id without a uuid here.
        id=f"scheduled-execution-{schedule.external_id}",
        task_queue=EXECUTION_TASK_QUEUE,
    )


async def _list_temporal_schedule_states(
    client: TemporalClient,
) -> dict[str, tuple[bool, datetime | None] | None] | None:
    """{temporal_schedule_id: (enabled, next_run_at)} for every schedule
    Temporal knows about, via one `list_schedules()` call — confirmed
    working on this deployment (verified directly: `ScheduleListInfo.
    next_action_times` and `ScheduleListSchedule.state.paused` both come
    back fully populated), so this is a single RPC rather than one
    `describe()` per row.

    A value of `None` for a *present* key means the schedule exists but its
    `info`/`schedule` sub-objects came back empty (the SDK types both
    optional, for servers without advanced visibility) — deliberately NOT
    the same as the key being *absent* entirely, which is what the caller's
    NOT_FOUND-as-proof-of-deletion logic keys off. Conflating the two would
    auto-delete a schedule that still exists just because one round of
    visibility data happened to be incomplete for it.

    Returns `None` (the whole dict) if Temporal itself is unreachable, so
    the caller can degrade the entire response to cached values instead of
    500ing."""
    try:
        states: dict[str, tuple[bool, datetime | None] | None] = {}
        async for entry in await client.list_schedules():
            if entry.info is None or entry.schedule is None:
                states[entry.id] = None
                continue
            next_times = entry.info.next_action_times
            states[entry.id] = (
                not entry.schedule.state.paused,
                next_times[0] if next_times else None,
            )
        return states
    except (RPCError, RuntimeError):
        logger.warning("could not list Temporal schedules — falling back to cached values")
        return None


async def _describe_schedule_state(
    client: TemporalClient, schedule: Schedule
) -> tuple[bool, datetime | None]:
    """(enabled, next_run_at) straight from Temporal for a single schedule
    — used right after create/update/enable/disable, where only one row is
    affected so a single `describe()` RPC is cheap (the list endpoint above
    uses `list_schedules()` instead, precisely to avoid N of these).
    Degrades to the cached column rather than failing the whole response;
    the fallback value is never written back to the DB."""
    try:
        description = await client.get_schedule_handle(schedule.temporal_schedule_id).describe()
    except (RPCError, RuntimeError):
        logger.warning(
            "could not describe Temporal schedule %s — falling back to the cached "
            "`enabled` value",
            schedule.temporal_schedule_id,
        )
        return schedule.enabled, None
    next_times = description.info.next_action_times
    return (not description.schedule.state.paused), (next_times[0] if next_times else None)


@app.get("/applications/{external_id}/schedules", response_model=list[ScheduleRead])
async def list_schedules(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> list[ScheduleRead]:
    application = _get_org_application(session, organization_id, external_id)
    schedules = session.exec(
        select(Schedule)
        .where(
            Schedule.application_id == application.id,
            Schedule.deleted_at.is_(None),  # type: ignore[attr-defined]
        )
        .order_by(Schedule.created_at.desc())  # type: ignore[arg-type]
    ).all()
    if not schedules:
        return []

    client = await get_temporal_client()
    states = await _list_temporal_schedule_states(client)

    results: list[ScheduleRead] = []
    dirty = False
    for schedule in schedules:
        if states is None:
            results.append(_to_schedule_read(schedule, enabled=schedule.enabled, next_run_at=None))
            continue
        if schedule.temporal_schedule_id not in states:
            # NOT_FOUND-as-proof-of-deletion: the *key itself* is absent,
            # meaning Temporal genuinely has no schedule with this id
            # (deleted directly in Temporal, or residue from a failed
            # Delete's Postgres commit) — soft-delete it as a side effect
            # of observing this, same unified policy every mutation
            # endpoint below uses. Not the same as the key being present
            # with a `None` value (see `_list_temporal_schedule_states`).
            schedule.deleted_at = datetime.now(UTC)
            session.add(schedule)
            dirty = True
            continue
        state = states[schedule.temporal_schedule_id]
        if state is None:
            # Exists, but this round's visibility data was incomplete —
            # degrade this one row to its cached value, not a deletion.
            results.append(_to_schedule_read(schedule, enabled=schedule.enabled, next_run_at=None))
            continue
        enabled, next_run_at = state
        if schedule.enabled != enabled:
            schedule.enabled = enabled
            session.add(schedule)
            dirty = True
        results.append(_to_schedule_read(schedule, enabled=enabled, next_run_at=next_run_at))
    if dirty:
        session.commit()
    return results


@app.post(
    "/applications/{external_id}/schedules", response_model=ScheduleRead, status_code=201
)
async def create_schedule(
    external_id: uuid.UUID,
    payload: ScheduleCreate,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
    user: CurrentUserDep,
) -> ScheduleRead:
    """Deliberately does NOT `has_pollers` check (unlike `trigger_test_run`/
    `trigger_schedule_now`): a schedule created now to fire at 2am has no
    business failing because the execution worker happens to be restarting
    right now — see this module's accepted-limitation note above."""
    application = _get_org_application(session, organization_id, external_id)

    try:
        validate_cadence(
            cadence_type=payload.cadence_type,
            hour=payload.hour,
            minute=payload.minute,
            days_of_week=payload.days_of_week,
            day_of_month=payload.day_of_month,
            cron_expression=payload.cron_expression,
            time_zone=payload.time_zone,
        )
    except ScheduleSpecError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    schedule = Schedule(
        application_id=application.id,
        name=payload.name,
        cadence_type=payload.cadence_type,
        hour=payload.hour,
        minute=payload.minute,
        days_of_week=payload.days_of_week,
        day_of_month=payload.day_of_month,
        cron_expression=payload.cron_expression,
        time_zone=payload.time_zone,
        enabled=True,
        temporal_schedule_id="",  # set below, derived from external_id
        created_by_name=user.name,
    )
    schedule.temporal_schedule_id = f"app-schedule-{schedule.external_id}"
    session.add(schedule)
    try:
        # Flush (not commit): surfaces the partial-unique-index violation on
        # (application_id, name) before anything is created in Temporal.
        # Postgres's row lock on the pending insert is also what makes two
        # concurrent same-name creates safe — the second request blocks
        # here, before it ever reaches `create_schedule` below, so no
        # duplicate Temporal Schedule can be created this way.
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="a schedule with this name already exists"
        ) from None

    client = await get_temporal_client()
    try:
        await client.create_schedule(
            schedule.temporal_schedule_id,
            TemporalSchedule(
                action=_build_schedule_action(schedule, application.external_id),
                spec=build_schedule_spec(schedule),
                policy=build_schedule_policy(),
            ),
        )
    except (RPCError, RuntimeError) as exc:
        session.rollback()
        raise HTTPException(status_code=502, detail="SCHEDULE_BACKEND_UNAVAILABLE") from exc

    try:
        session.commit()
    except Exception:
        # Temporal succeeded but the Postgres commit failed — best-effort
        # compensating cleanup using the deterministic id (no ambiguity
        # about which Temporal object to remove). If this also fails, the
        # orphan is swept later by `purge_orphan_schedules.py` (confirmed
        # viable — see the migration/spike notes); the log line is the
        # immediate operator-visible signal either way.
        try:
            await client.get_schedule_handle(schedule.temporal_schedule_id).delete()
        except (RPCError, RuntimeError):
            logger.error(
                "orphaned Temporal schedule %s: create's Postgres commit failed and "
                "the compensating delete also failed",
                schedule.temporal_schedule_id,
            )
        raise

    session.refresh(schedule)
    enabled, next_run_at = await _describe_schedule_state(client, schedule)
    return _to_schedule_read(schedule, enabled=enabled, next_run_at=next_run_at)


@app.patch("/schedules/{external_id}", response_model=ScheduleRead)
async def update_schedule(
    external_id: uuid.UUID,
    payload: ScheduleUpdate,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> ScheduleRead:
    schedule = _get_org_schedule(session, organization_id, external_id)
    application = session.get(Application, schedule.application_id)
    assert application is not None

    # Captured before mutating — needed to revert Temporal if the Postgres
    # commit below fails after Temporal already accepted the new spec.
    previous_action = _build_schedule_action(schedule, application.external_id)
    previous_spec = build_schedule_spec(schedule)
    previous_policy = build_schedule_policy()

    for field_name in (
        "name",
        "cadence_type",
        "hour",
        "minute",
        "days_of_week",
        "day_of_month",
        "cron_expression",
        "time_zone",
    ):
        value = getattr(payload, field_name)
        if value is not None:
            setattr(schedule, field_name, value)
    # Clear the fields the (possibly new) cadence type doesn't use, so a
    # daily schedule edited from a weekly one doesn't keep stale days.
    if schedule.cadence_type != "weekly":
        schedule.days_of_week = []
    if schedule.cadence_type != "monthly":
        schedule.day_of_month = None
    if schedule.cadence_type != "custom_cron":
        schedule.cron_expression = None
    else:
        schedule.hour = None
        schedule.minute = None

    try:
        # Validates the *merged* row, never just the supplied fields — see
        # ScheduleUpdate's own docstring.
        validate_cadence(
            cadence_type=schedule.cadence_type,
            hour=schedule.hour,
            minute=schedule.minute,
            days_of_week=schedule.days_of_week,
            day_of_month=schedule.day_of_month,
            cron_expression=schedule.cron_expression,
            time_zone=schedule.time_zone,
        )
    except ScheduleSpecError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from None

    schedule.updated_at = datetime.now(UTC)
    session.add(schedule)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="a schedule with this name already exists"
        ) from None

    new_action = _build_schedule_action(schedule, application.external_id)
    new_spec = build_schedule_spec(schedule)
    new_policy = build_schedule_policy()

    def _updater(input: ScheduleUpdateInput) -> TemporalScheduleUpdate:
        # `state` is carried over from Temporal's *live* description at the
        # moment this callback runs, never rebuilt — Temporal owns
        # paused-ness (see this module's source-of-truth note), so editing a
        # disabled schedule's time must not silently re-enable it. This also
        # means a concurrent enable/disable can never be undone by a racing
        # PATCH: whichever pause state is current when this callback
        # executes is what gets preserved.
        return TemporalScheduleUpdate(
            schedule=TemporalSchedule(
                action=new_action,
                spec=new_spec,
                policy=new_policy,
                state=input.description.schedule.state,
            )
        )

    client = await get_temporal_client()
    try:
        await client.get_schedule_handle(schedule.temporal_schedule_id).update(_updater)
    except RPCError as exc:
        session.rollback()
        if exc.status == RPCStatusCode.NOT_FOUND:
            # Disappeared between read and write (raced with a DELETE) —
            # soft-delete the row as a side effect of observing this, same
            # unified NOT_FOUND policy as the GET reconciliation above.
            schedule.deleted_at = datetime.now(UTC)
            session.add(schedule)
            session.commit()
            raise HTTPException(status_code=404, detail="schedule not found") from None
        raise HTTPException(status_code=502, detail="SCHEDULE_BACKEND_UNAVAILABLE") from exc
    except RuntimeError as exc:
        session.rollback()
        raise HTTPException(status_code=502, detail="SCHEDULE_BACKEND_UNAVAILABLE") from exc

    try:
        session.commit()
    except Exception:
        try:

            def _revert(input: ScheduleUpdateInput) -> TemporalScheduleUpdate:
                return TemporalScheduleUpdate(
                    schedule=TemporalSchedule(
                        action=previous_action,
                        spec=previous_spec,
                        policy=previous_policy,
                        state=input.description.schedule.state,
                    )
                )

            await client.get_schedule_handle(schedule.temporal_schedule_id).update(_revert)
        except (RPCError, RuntimeError):
            logger.error(
                "Temporal schedule %s diverged from Postgres: update's Postgres commit "
                "failed and the compensating revert also failed — needs manual "
                "reconciliation",
                schedule.temporal_schedule_id,
            )
        raise

    session.refresh(schedule)
    enabled, next_run_at = await _describe_schedule_state(client, schedule)
    return _to_schedule_read(schedule, enabled=enabled, next_run_at=next_run_at)


@app.delete("/schedules/{external_id}", status_code=204)
async def delete_schedule(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> None:
    """Idempotent: a second DELETE against an already-deleted (or
    already-auto-healed) schedule still returns 204 — `RPCError` NOT_FOUND
    from `handle.delete()` is treated the same as success, not an error
    (mirrors `create_cleanup_schedule.py`'s ALREADY_EXISTS tolerance for
    create). This is what makes retrying a timed-out DELETE actually safe.

    Hard-deletes the *Temporal* Schedule (it's the live object, nothing
    historical about it) while soft-deleting the Postgres row (history — a
    TestRun.schedule_id FK may point here). An in-progress execution that
    this schedule already fired is untouched either way — it's a fully
    decoupled child workflow by the time it's running."""
    schedule = _get_org_schedule(session, organization_id, external_id)

    client = await get_temporal_client()
    try:
        await client.get_schedule_handle(schedule.temporal_schedule_id).delete()
    except RPCError as exc:
        if exc.status != RPCStatusCode.NOT_FOUND:
            raise HTTPException(status_code=502, detail="SCHEDULE_BACKEND_UNAVAILABLE") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="SCHEDULE_BACKEND_UNAVAILABLE") from exc

    schedule.deleted_at = datetime.now(UTC)
    session.add(schedule)
    session.commit()


@app.post("/schedules/{external_id}/enable", response_model=ScheduleRead)
async def enable_schedule(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> ScheduleRead:
    schedule = _get_org_schedule(session, organization_id, external_id)
    client = await get_temporal_client()
    try:
        await client.get_schedule_handle(schedule.temporal_schedule_id).unpause()
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            schedule.deleted_at = datetime.now(UTC)
            session.add(schedule)
            session.commit()
            raise HTTPException(status_code=404, detail="schedule not found") from None
        raise HTTPException(status_code=502, detail="SCHEDULE_BACKEND_UNAVAILABLE") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="SCHEDULE_BACKEND_UNAVAILABLE") from exc

    schedule.enabled = True
    session.add(schedule)
    # If this commit fails, the next GET's list_schedules() reconciliation
    # self-heals the cached column back to the true (now unpaused) state.
    session.commit()
    session.refresh(schedule)
    enabled, next_run_at = await _describe_schedule_state(client, schedule)
    return _to_schedule_read(schedule, enabled=enabled, next_run_at=next_run_at)


@app.post("/schedules/{external_id}/disable", response_model=ScheduleRead)
async def disable_schedule(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> ScheduleRead:
    schedule = _get_org_schedule(session, organization_id, external_id)
    client = await get_temporal_client()
    try:
        await client.get_schedule_handle(schedule.temporal_schedule_id).pause()
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            schedule.deleted_at = datetime.now(UTC)
            session.add(schedule)
            session.commit()
            raise HTTPException(status_code=404, detail="schedule not found") from None
        raise HTTPException(status_code=502, detail="SCHEDULE_BACKEND_UNAVAILABLE") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="SCHEDULE_BACKEND_UNAVAILABLE") from exc

    schedule.enabled = False
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    enabled, next_run_at = await _describe_schedule_state(client, schedule)
    return _to_schedule_read(schedule, enabled=enabled, next_run_at=next_run_at)


# The statuses that mean "an execution is in flight for this Application" —
# same vocabulary check_schedule_gate_activity uses.
#
# ponytail: duplicated here rather than imported, since the gate lives in
# the execution worker (apps/workers/execution), which this API process
# doesn't depend on. A fuller version would move this tuple + the query
# into packages/domain and have both call it.
_IN_PROGRESS_TEST_RUN_STATUSES = ("pending", "running")


@app.post("/schedules/{external_id}/run-now", status_code=202)
async def trigger_schedule_now(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> dict[str, bool]:
    """Goes through `handle.trigger()`, not `client.start_workflow` — so a
    "Run now" takes the exact same gated path a real occurrence takes, gets
    counted in the schedule's own recent_actions, and obeys the same SKIP
    overlap policy. One path, not two.

    A `202` here is never a guarantee an execution actually starts:
    `ScheduledExecutionWorkflow`'s own fire-time gate is the sole authority,
    and it runs *after* this returns. The in-progress check below is
    advisory UX only (so the button doesn't silently no-op when the
    Application is already busy) — another execution can start in the
    window between this check and the gate's own re-check, in which case
    the gate skips it, same as any other scheduled-vs-manual overlap."""
    schedule = _get_org_schedule(session, organization_id, external_id)
    active = session.exec(
        select(TestRun.id)
        .where(
            TestRun.application_id == schedule.application_id,
            TestRun.status.in_(_IN_PROGRESS_TEST_RUN_STATUSES),  # type: ignore[attr-defined]
        )
        .limit(1)
    ).first()
    if active is not None:
        raise HTTPException(status_code=409, detail="EXECUTION_IN_PROGRESS")

    client = await get_temporal_client()
    if not await has_pollers(client, EXECUTION_TASK_QUEUE):
        raise HTTPException(status_code=503, detail="EXECUTION_UNAVAILABLE")

    try:
        await client.get_schedule_handle(schedule.temporal_schedule_id).trigger()
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            schedule.deleted_at = datetime.now(UTC)
            session.add(schedule)
            session.commit()
            raise HTTPException(status_code=404, detail="schedule not found") from None
        raise HTTPException(status_code=502, detail="SCHEDULE_BACKEND_UNAVAILABLE") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="SCHEDULE_BACKEND_UNAVAILABLE") from exc

    return {"started": True}


class TestRunCursorPageRead(BaseModel):
    items: list[TestRunRead]
    next_cursor: str | None


@app.get("/applications/{external_id}/test-runs", response_model=TestRunCursorPageRead)
def list_test_runs(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
    cursor: uuid.UUID | None = None,
    limit: int = 10,
) -> TestRunCursorPageRead:
    """Keyset-paginated on the `id` PK (Application Workspace feature's Runs
    tab) — every run for an Application is kept forever (immutable history)
    and this list is polled every 1.5s while new runs land, so an
    OFFSET-based page could duplicate/skip rows as they shift underneath a
    poll; a keyset cursor can't, since it's anchored to a specific row
    rather than a position. `id` (not `created_at`) is the keyset column
    because it's a uuid7 — already time-sortable by construction (see
    `TestRun.id`'s `uuidv7()` default) — and unique, so no tiebreaker is
    needed for rows created in the same instant. The frontend keeps its own
    stack of previously-seen cursors for "Previous" rather than this
    endpoint supporting a reverse direction."""
    application = _get_org_application(session, organization_id, external_id)
    query = select(TestRun).where(TestRun.application_id == application.id)
    if cursor is not None:
        query = query.where(TestRun.id < cursor)  # type: ignore[arg-type]
    test_runs = session.exec(
        query.order_by(TestRun.id.desc()).limit(limit)  # type: ignore[arg-type]
    ).all()
    next_cursor = str(test_runs[-1].id) if len(test_runs) == limit else None
    return TestRunCursorPageRead(
        items=[_to_test_run_read(tr, results=None) for tr in test_runs],
        next_cursor=next_cursor,
    )


@app.get(
    "/applications/{external_id}/test-runs/{test_run_external_id}",
    response_model=TestRunRead,
)
def get_test_run(
    external_id: uuid.UUID,
    test_run_external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> TestRunRead:
    """The endpoint the frontend polls while a run is in flight (mirrors
    `list_test_suites`'s shape)."""
    application = _get_org_application(session, organization_id, external_id)
    test_run = session.exec(
        select(TestRun).where(
            TestRun.external_id == test_run_external_id,
            TestRun.application_id == application.id,
        )
    ).first()
    if test_run is None:
        raise HTTPException(status_code=404, detail="test run not found")

    results = session.exec(
        select(TestResult).where(TestResult.test_run_id == test_run.id)
    ).all()
    scenario_ids = {r.scenario_id for r in results}
    scenarios_by_id = (
        {
            s.id: s
            for s in session.exec(
                select(Scenario).where(Scenario.id.in_(scenario_ids))  # type: ignore[attr-defined]
            ).all()
        }
        if scenario_ids
        else {}
    )
    max_heal_attempts = session.exec(select(DiscoverySettings)).one().max_heal_attempts
    result_reads = [
        TestResultRead(
            id=r.external_id,
            scenario_name=scenarios_by_id[r.scenario_id].name
            if r.scenario_id in scenarios_by_id
            else "",
            status=r.status,
            duration_ms=r.duration_ms,
            error_message=r.error_message,
            stack_trace=r.stack_trace,
            blocked_reason=r.blocked_reason,
            auto_heal_attempt_count=r.auto_heal_attempt_count,
            manual_heal_attempt_count=r.manual_heal_attempt_count,
            healed_test_asset_id=r.healed_test_asset_id,
            auto_heal_attempt_cap=AUTO_HEAL_ATTEMPT_CAP,
            max_heal_attempts=max_heal_attempts,
        )
        for r in results
    ]
    return _to_test_run_read(test_run, results=result_reads)


@app.get(
    "/test-results/{external_id}/artifacts",
    response_model=list[TestResultArtifactRead],
)
def list_test_result_artifacts(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> list[TestResultArtifactRead]:
    """Presigned URLs (mirrors the existing screenshot-URL pattern used
    elsewhere in this file) — never proxies the blob itself through this
    API."""
    test_result = session.exec(
        select(TestResult).where(TestResult.external_id == external_id)
    ).first()
    test_run = (
        session.get(TestRun, test_result.test_run_id) if test_result is not None else None
    )
    application = (
        session.get(Application, test_run.application_id) if test_run is not None else None
    )
    if (
        test_result is None
        or test_run is None
        or application is None
        or application.organization_id != organization_id
    ):
        raise HTTPException(status_code=404, detail="test result not found")

    artifacts = session.exec(
        select(TestResultArtifact).where(TestResultArtifact.test_result_id == test_result.id)
    ).all()
    object_store = ObjectStore()
    return [
        TestResultArtifactRead(
            id=a.external_id,
            artifact_type=a.artifact_type,
            content_type=a.content_type,
            size_bytes=a.size_bytes,
            url=object_store.presigned_get_url(
                a.object_store_key,
                response_content_type=a.content_type,
                filename=f"{a.artifact_type}.{'zip' if a.artifact_type == 'trace' else 'png'}",
            ),
        )
        for a in artifacts
    ]


@app.post("/test-results/{external_id}/heal", status_code=202)
async def heal_test_result(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
) -> dict[str, bool]:
    """Manual "Retry with self-heal" — starts the same HealTestActivity the
    automatic path runs (inside ApplicationTestExecutionWorkflow.run_one),
    via HealTestExecutionWorkflow with triggered_manually=True, drawing from
    its own independent manual_heal_attempt_count budget — entirely
    unaffected by how many automatic attempts (auto_heal_attempt_count)
    already ran against this same TestResult. The eligibility checks below
    mirror `heal_test_activity`'s own no-op condition and claim guard
    exactly (same HEALABLE_STATUSES, same DiscoverySettings.max_heal_attempts
    against manual_heal_attempt_count specifically, same
    HEAL_CLAIM_STALE_AFTER staleness window) so this endpoint's 409s and the
    activity's own behavior never disagree."""
    test_result = session.exec(
        select(TestResult).where(TestResult.external_id == external_id)
    ).first()
    test_run = (
        session.get(TestRun, test_result.test_run_id) if test_result is not None else None
    )
    application = (
        session.get(Application, test_run.application_id) if test_run is not None else None
    )
    if (
        test_result is None
        or test_run is None
        or application is None
        or application.organization_id != organization_id
    ):
        raise HTTPException(status_code=404, detail="test result not found")

    discovery_settings = session.exec(select(DiscoverySettings)).one()
    if test_result.status not in HEALABLE_STATUSES:
        raise HTTPException(status_code=409, detail="test result is not in a healable state")
    if test_result.manual_heal_attempt_count >= discovery_settings.max_heal_attempts:
        raise HTTPException(status_code=409, detail="self-heal attempt budget already spent")
    if (
        test_result.heal_started_at is not None
        and test_result.heal_started_at >= datetime.now(UTC) - HEAL_CLAIM_STALE_AFTER
    ):
        raise HTTPException(status_code=409, detail="a self-heal attempt is already in progress")

    client = await get_temporal_client()
    if not await has_pollers(client, EXECUTION_TASK_QUEUE):
        raise HTTPException(status_code=503, detail="EXECUTION_UNAVAILABLE")
    try:
        await client.start_workflow(
            HealTestExecutionWorkflow.run,
            HealTestActivityInput(
                application_id=str(application.external_id),
                test_run_id=str(test_run.external_id),
                test_result_id=str(test_result.external_id),
                triggered_manually=True,
            ),
            # Deterministic — a duplicate/rapid double-click naturally
            # rejects via WorkflowAlreadyStartedError below, same
            # idempotency convention SuiteGenerationWorkflow's
            # `suite-{journey_id}-{attempt}` already uses.
            id=f"heal-{test_result.external_id}",
            task_queue=EXECUTION_TASK_QUEUE,
        )
    except WorkflowAlreadyStartedError:
        pass  # already in progress — not an error
    return {"started": True}


def _current_test_assets_for_application(
    session: Session, application: Application
) -> tuple[list[TestAsset], dict[uuid.UUID, Scenario]]:
    """The same `Journey(candidate) -> TestSuite(current) -> TestAsset(current)`
    join `list_test_suites` and `_prepare_test_run_sync`
    (`execution_worker/activities.py`) already use — factored out here so
    the Application Workspace's Suite-tab and Overview endpoints don't each
    duplicate it. Returns every current `TestAsset` plus a
    `Scenario.id -> Scenario` map (for name/type/steps)."""
    journeys = session.exec(
        select(Journey).where(
            Journey.application_id == application.id,
            Journey.status == "candidate",
        )
    ).all()
    if not journeys:
        return [], {}
    journey_ids = [j.id for j in journeys]

    test_suites = session.exec(
        select(TestSuite).where(
            TestSuite.journey_id.in_(journey_ids),  # type: ignore[attr-defined]
            TestSuite.current.is_(True),  # type: ignore[attr-defined]
        )
    ).all()
    if not test_suites:
        return [], {}
    suite_ids = [ts.id for ts in test_suites]

    test_assets = session.exec(
        select(TestAsset).where(
            TestAsset.test_suite_id.in_(suite_ids),  # type: ignore[attr-defined]
            TestAsset.current.is_(True),  # type: ignore[attr-defined]
        )
    ).all()
    scenario_ids = {a.scenario_id for a in test_assets}
    # See list_test_suites for why Scenario.current is required here too.
    scenarios_by_id = {
        s.id: s
        for s in (
            session.exec(
                select(Scenario).where(
                    Scenario.id.in_(scenario_ids),  # type: ignore[attr-defined]
                    Scenario.current.is_(True),  # type: ignore[attr-defined]
                )
            ).all()
            if scenario_ids
            else []
        )
    }
    return test_assets, scenarios_by_id


def _latest_result_by_scenario(
    session: Session, application: Application, scenario_ids: list[uuid.UUID]
) -> dict[uuid.UUID, TestResult]:
    """The most recent `TestResult` per `Scenario`, across every `TestRun`
    the Application has ever had — no window function exists elsewhere in
    this codebase, so this uses the same order-by-desc + `setdefault` idiom
    already established for "most recent X" lookups (mirrors
    `_latest_discovery_run` above, just keyed per-scenario instead of
    per-application).

    Keyed by `scenario_id`, not `test_asset_id`: `HealTestActivity`
    (`execution_worker/activities.py`) supersedes a healed scenario's
    `TestAsset` onto a brand-new row (`supersede_test_asset`) but every
    `TestResult` keeps pointing at whichever `TestAsset` was current when it
    ran — a scenario's post-heal `TestResult`s would otherwise sit under an
    id no longer in `asset_ids`, invisible to a caller that only asks about
    the *current* asset, so the row reads "Not Run" for a test that just
    passed (its `TestRun.passed_count` tally already counts it correctly —
    that's the mismatch this fixes). `scenario_id` is stable across a heal
    supersede, so this survives it. A scenario with no key in the returned
    dict has never been executed at all ("Not Run")."""
    if not scenario_ids:
        return {}
    results = session.exec(
        select(TestResult)
        .join(TestRun, TestResult.test_run_id == TestRun.id)  # type: ignore[arg-type]
        .where(
            TestRun.application_id == application.id,
            TestResult.scenario_id.in_(scenario_ids),  # type: ignore[attr-defined]
        )
        .order_by(TestResult.created_at.desc())  # type: ignore[arg-type]
    ).all()
    latest_by_scenario: dict[uuid.UUID, TestResult] = {}
    for result in results:
        latest_by_scenario.setdefault(result.scenario_id, result)
    return latest_by_scenario


def _collapse_to_suite_row_status(result: TestResult | None) -> str:
    """The Suite tab shows exactly 3 buckets (Passed/Failed/Not Run) —
    narrower than `TestResultStatus`'s full vocabulary. `timed_out`/
    `errored`/`blocked` all read as "Failed" here: an attempted-and-didn't-pass
    test is a more honest reading for a suite-health table than lumping it
    with never-attempted. The Runs tab's per-result detail view still shows
    the full status via `StatusPill`, so nothing is lost overall — only in
    this one summary."""
    if result is None or result.status == "pending":
        return "not_run"
    if result.status == "passed":
        return "passed"
    return "failed"


def _get_org_test_asset(
    session: Session, organization_id: uuid.UUID, external_id: uuid.UUID
) -> TestAsset:
    test_asset = session.exec(
        select(TestAsset).where(TestAsset.external_id == external_id)
    ).first()
    test_suite = session.get(TestSuite, test_asset.test_suite_id) if test_asset else None
    journey = session.get(Journey, test_suite.journey_id) if test_suite else None
    application = session.get(Application, journey.application_id) if journey else None
    if (
        test_asset is None
        or test_suite is None
        or journey is None
        or application is None
        or application.organization_id != organization_id
    ):
        raise HTTPException(status_code=404, detail="test asset not found")
    return test_asset


class TestAssetStatusRead(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    steps: list[str]
    status: str
    last_run_at: datetime | None
    duration_ms: int | None
    error_message: str | None
    latest_test_result_id: uuid.UUID | None
    # NLM "Add Test Case" feature — see TestCaseRead's own comment.
    source: str


class TestAssetStatusPageRead(BaseModel):
    items: list[TestAssetStatusRead]
    page: int
    page_size: int
    total: int


@app.get(
    "/applications/{external_id}/test-suite-status",
    response_model=TestAssetStatusPageRead,
)
def get_test_suite_status(
    external_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
    page: int = 1,
    page_size: int = 10,
) -> TestAssetStatusPageRead:
    """Application Workspace's Test Suite tab — one row per current
    TestAsset, showing its most recent result (or "not_run" if it's never
    been executed) across every TestRun, not just the latest one."""
    application = _get_org_application(session, organization_id, external_id)
    test_assets, scenarios_by_id = _current_test_assets_for_application(session, application)

    def _scenario_name(asset: TestAsset) -> str:
        scenario = scenarios_by_id.get(asset.scenario_id)
        return scenario.name if scenario else ""

    test_assets = sorted(test_assets, key=_scenario_name)
    total = len(test_assets)
    page_assets = test_assets[(page - 1) * page_size : (page - 1) * page_size + page_size]

    latest_by_scenario = _latest_result_by_scenario(
        session, application, [a.scenario_id for a in page_assets]
    )

    items = []
    for asset in page_assets:
        scenario = scenarios_by_id.get(asset.scenario_id)
        result = latest_by_scenario.get(asset.scenario_id)
        items.append(
            TestAssetStatusRead(
                id=asset.external_id,
                name=scenario.name if scenario else "",
                type=scenario.type if scenario else "happy",
                steps=scenario.steps if scenario else [],
                status=_collapse_to_suite_row_status(result),
                last_run_at=result.completed_at if result else None,
                duration_ms=result.duration_ms if result else None,
                error_message=result.error_message if result else None,
                latest_test_result_id=result.external_id if result else None,
                source=scenario.source if scenario else "discovery",
            )
        )
    return TestAssetStatusPageRead(items=items, page=page, page_size=page_size, total=total)


class TestAssetCodeRead(BaseModel):
    code: str


@app.get("/test-assets/{external_id}/code", response_model=TestAssetCodeRead)
def get_test_asset_code(
    external_id: uuid.UUID, session: SessionDep, organization_id: CurrentOrgIdDep
) -> TestAssetCodeRead:
    """Lazy code fetch for the Suite tab's "View Code" button — keeps the
    (large, rarely-viewed) source text out of `get_test_suite_status`'s
    paginated rows."""
    test_asset = _get_org_test_asset(session, organization_id, external_id)
    return TestAssetCodeRead(code=test_asset.code)


class RunTrendPointRead(BaseModel):
    run_id: uuid.UUID
    pass_rate: float | None
    created_at: datetime


class LatestRunSummaryRead(BaseModel):
    id: uuid.UUID
    created_at: datetime
    passed_count: int
    failed_count: int
    blocked_count: int
    duration_ms: int | None
    # Same format as TestRunRead.trigger (both built by `_trigger_label`) —
    # kept as one formatted string rather than a separate `triggered_by_name`
    # field so the frontend has one parser (`parseTrigger`) for both the
    # Runs tab and this Overview tile.
    trigger: str


class OverviewRead(BaseModel):
    health: HealthRead
    total_tests: int
    passed: int
    failed: int
    not_run: int
    pass_rate: float | None
    trend: list[RunTrendPointRead]
    latest_run: LatestRunSummaryRead | None
    # `DiscoveryRun` has no completion timestamp (only `created_at`, i.e.
    # start time, and `status`) — this is honestly the most recent
    # *completed* run's start time, not when it finished.
    last_discovery_started_at: datetime | None
    # Candidate journeys found by the most recent discovery — same
    # `Journey.status == "candidate"` count `get_home` computes per
    # application, just scoped to this one application instead of batched.
    journey_count: int


_OVERVIEW_TREND_RUN_COUNT = 10


@app.get("/applications/{external_id}/overview", response_model=OverviewRead)
def get_overview(
    external_id: uuid.UUID, session: SessionDep, organization_id: CurrentOrgIdDep
) -> OverviewRead:
    """Application Workspace's Overview tab — one bundled endpoint (health,
    stat counts, recent-run trend, latest run, last discovery) rather than
    several, mirroring `get_home`'s own "aggregate once, don't reintroduce a
    polling waterfall" rationale."""
    application = _get_org_application(session, organization_id, external_id)
    test_assets, scenarios_by_id = _current_test_assets_for_application(session, application)
    scenario_ids = [a.scenario_id for a in test_assets]
    latest_by_scenario = _latest_result_by_scenario(session, application, scenario_ids)

    total_tests = len(test_assets)
    passed = sum(
        1
        for a in test_assets
        if _collapse_to_suite_row_status(latest_by_scenario.get(a.scenario_id)) == "passed"
    )
    failed = sum(
        1
        for a in test_assets
        if _collapse_to_suite_row_status(latest_by_scenario.get(a.scenario_id)) == "failed"
    )
    not_run = total_tests - passed - failed
    pass_rate = (passed / total_tests) if total_tests else None

    recent_runs = session.exec(
        select(TestRun)
        .where(TestRun.application_id == application.id)
        .order_by(TestRun.created_at.desc())  # type: ignore[arg-type]
        .limit(_OVERVIEW_TREND_RUN_COUNT)
    ).all()
    trend = [
        RunTrendPointRead(
            run_id=r.external_id,
            pass_rate=(r.passed_count / r.total_count) if r.total_count else None,
            created_at=r.created_at,
        )
        for r in reversed(recent_runs)  # oldest first, for a left-to-right trend chart
    ]
    latest_run = None
    if recent_runs:
        latest = recent_runs[0]
        duration_ms = None
        if latest.started_at and latest.completed_at:
            duration_ms = int((latest.completed_at - latest.started_at).total_seconds() * 1000)
        latest_run = LatestRunSummaryRead(
            id=latest.external_id,
            created_at=latest.created_at,
            passed_count=latest.passed_count,
            failed_count=latest.failed_count,
            blocked_count=latest.blocked_count,
            duration_ms=duration_ms,
            trigger=_trigger_label(latest),
        )

    discovery_run = _latest_discovery_run(session, application.id)
    last_discovery_started_at = (
        discovery_run.created_at if discovery_run and discovery_run.status == "complete" else None
    )
    journey_count = session.exec(
        select(func.count())
        .select_from(Journey)
        .where(Journey.application_id == application.id, Journey.status == "candidate")
    ).one()

    return OverviewRead(
        health=_health_tier(pass_rate),
        total_tests=total_tests,
        passed=passed,
        failed=failed,
        not_run=not_run,
        pass_rate=pass_rate,
        trend=trend,
        latest_run=latest_run,
        last_discovery_started_at=last_discovery_started_at,
        journey_count=journey_count,
    )


class SettingsRead(BaseModel):
    max_pages: int
    max_discovery_duration_minutes: int | None
    navigation_timeout_seconds: float
    interaction_level: InteractionLevel
    max_journeys: int | None
    max_scenarios_per_journey: int | None
    max_test_cases_per_application: int | None
    delete_project_after: RetentionPeriod
    max_heal_attempts: int


class SettingsUpdate(BaseModel):
    max_pages: int | None = None
    navigation_timeout_seconds: float | None = None
    interaction_level: InteractionLevel | None = None
    delete_project_after: RetentionPeriod | None = None
    max_heal_attempts: int | None = None
    # Sentinel, not None: None already means "leave unchanged" for every
    # other field here, but these four need "leave unchanged" AND "clear to
    # unlimited" to be distinguishable.
    max_discovery_duration_minutes: int | None | Literal["__unset__"] = "__unset__"
    max_journeys: int | None | Literal["__unset__"] = "__unset__"
    max_scenarios_per_journey: int | None | Literal["__unset__"] = "__unset__"
    max_test_cases_per_application: int | None | Literal["__unset__"] = "__unset__"


def _to_settings_read(settings: DiscoverySettings) -> SettingsRead:
    return SettingsRead(
        max_pages=settings.max_pages,
        max_discovery_duration_minutes=settings.max_discovery_duration_minutes,
        navigation_timeout_seconds=settings.navigation_timeout_seconds,
        interaction_level=settings.interaction_level,  # type: ignore[arg-type]
        max_journeys=settings.max_journeys,
        max_scenarios_per_journey=settings.max_scenarios_per_journey,
        max_test_cases_per_application=settings.max_test_cases_per_application,
        delete_project_after=settings.delete_project_after,  # type: ignore[arg-type]
        max_heal_attempts=settings.max_heal_attempts,
    )


@app.get("/settings", response_model=SettingsRead)
def get_settings(session: SessionDep, _admin: CurrentAdminDep) -> SettingsRead:
    settings = session.exec(select(DiscoverySettings)).one()
    return _to_settings_read(settings)


@app.patch("/settings", response_model=SettingsRead)
def update_settings(
    payload: SettingsUpdate,
    session: SessionDep,
    _admin: CurrentAdminDep,
) -> SettingsRead:
    settings = session.exec(select(DiscoverySettings)).one()
    if payload.max_pages is not None:
        settings.max_pages = payload.max_pages
    if payload.max_discovery_duration_minutes != "__unset__":
        settings.max_discovery_duration_minutes = payload.max_discovery_duration_minutes
    if payload.navigation_timeout_seconds is not None:
        settings.navigation_timeout_seconds = payload.navigation_timeout_seconds
    if payload.interaction_level is not None:
        settings.interaction_level = payload.interaction_level
    if payload.delete_project_after is not None:
        settings.delete_project_after = payload.delete_project_after
    if payload.max_journeys != "__unset__":
        settings.max_journeys = payload.max_journeys
    if payload.max_scenarios_per_journey != "__unset__":
        settings.max_scenarios_per_journey = payload.max_scenarios_per_journey
    if payload.max_test_cases_per_application != "__unset__":
        settings.max_test_cases_per_application = payload.max_test_cases_per_application
    if payload.max_heal_attempts is not None:
        settings.max_heal_attempts = payload.max_heal_attempts
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return _to_settings_read(settings)
