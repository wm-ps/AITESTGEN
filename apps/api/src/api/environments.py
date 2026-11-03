"""Application environments — extra deployments of an Application that the
same test cases can run against (Application Settings → Environments).

The Application row is the *default* environment; rows here are the extras
(see `domain.application_environment`). Login details mirror the default: an
environment inherits the default's `auth_method`, so a standard-login app needs
a username and password (and a login URL, when the default has one) for every
environment, and a no-sign-in app takes none. An SSO-session default isn't
supported — there is nothing in the UI that could capture a session per host.

Credential *validation* (a real browser login) is orchestrated by the web
dialog through the existing `/applications/verify-credentials` start+poll,
exactly like onboarding the default; this module enforces what can be checked
inline — approved domain, reachability, required fields, unique name.
"""

import json
import uuid
from urllib.parse import urlsplit

import httpx
from domain import Application, ApplicationEnvironment, Schedule, TestRun
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from secrets_client import SecretRef, VaultSecretsClient
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from api.activity import record_activity
from api.approved_domains import require_approved_domain
from api.auth import CurrentOrgIdDep, CurrentUserDep, NotViewerDep, SessionDep

router = APIRouter(tags=["environments"])

_IN_PROGRESS = ("pending", "running")
_EMPTY_SESSION = b'{"cookies": [], "origins": []}'
ENVIRONMENT_IN_USE = "ENVIRONMENT_IN_USE"
ENVIRONMENT_RUNNING = "ENVIRONMENT_RUNNING"
ENVIRONMENT_NAME_TAKEN = "ENVIRONMENT_NAME_TAKEN"


class EnvironmentRead(BaseModel):
    # `None` for the default environment (the Application row itself).
    id: uuid.UUID | None
    name: str
    url: str
    login_url: str | None
    is_default: bool
    auth_method: str
    # Never the password. Hidden from viewers, like every other credential.
    username: str | None = None


class EnvironmentCreate(BaseModel):
    name: str
    url: str
    login_url: str | None = None
    username: str | None = None
    password: str | None = None

    @field_validator("name", "username", "password", "login_url", mode="before")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class EnvironmentUpdate(BaseModel):
    """Only the fields present are changed (`model_fields_set`). A blank
    password means "unchanged"."""

    name: str | None = None
    url: str | None = None
    login_url: str | None = None
    username: str | None = None
    password: str | None = None
    # Same MFA fields as the default's credentials form; untouched unless sent.
    mfa_enabled: bool | None = None
    totp_seed: str | None = None

    @field_validator("name", "username", "password", "login_url", "url", "totp_seed", mode="before")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class EnvironmentReveal(BaseModel):
    password: str


def _main():
    # ponytail: `_normalize_application_url` / `_check_reachable` live in
    # main.py (which imports this router), so they're imported at call time to
    # avoid a cycle. A fuller version moves them into a shared module.
    from api import main

    return main


def _org_application(
    session: Session, organization_id: uuid.UUID, external_id: uuid.UUID
) -> Application:
    return _main()._get_org_application(session, organization_id, external_id)


def _get_environment(
    session: Session, application: Application, environment_id: uuid.UUID
) -> ApplicationEnvironment:
    environment = session.exec(
        select(ApplicationEnvironment).where(
            ApplicationEnvironment.external_id == environment_id,
            ApplicationEnvironment.application_id == application.id,
        )
    ).first()
    if environment is None:
        raise HTTPException(status_code=404, detail="environment not found")
    return environment


def _valid_http_url(value: str, label: str) -> None:
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise HTTPException(status_code=422, detail=f"Enter a valid {label} starting with https://")


async def _require_reachable(url: str) -> None:
    async with httpx.AsyncClient(follow_redirects=True, timeout=5.0) as client:
        await _main()._check_reachable(client, url)


def _require_login_rules(
    application: Application,
    auth_method: str,
    *,
    username: str | None,
    password: str | None,
    login_url: str | None,
) -> None:
    """Same details the default app was onboarded with: username and password
    when it signs in with them, a login URL when the default has one."""
    if auth_method == "sso_session_reuse":
        raise HTTPException(
            status_code=422,
            detail="Environments aren't supported for apps that sign in with a saved SSO session",
        )
    if auth_method == "standard_login":
        if not username:
            raise HTTPException(status_code=422, detail="Enter the username")
        if not password:
            raise HTTPException(status_code=422, detail="Enter the password")
    if application.login_url and not login_url:
        raise HTTPException(status_code=422, detail="Enter the login URL")


def _check_name(
    session: Session, application: Application, name: str, *, except_id: uuid.UUID | None = None
) -> None:
    if not name:
        raise HTTPException(status_code=422, detail="Enter the environment name")
    query = select(ApplicationEnvironment.id).where(
        ApplicationEnvironment.application_id == application.id,
        func.lower(ApplicationEnvironment.name) == name.lower(),
    )
    if except_id is not None:
        query = query.where(ApplicationEnvironment.id != except_id)
    if name.lower() == application.environment.strip().lower() or session.exec(query).first():
        raise HTTPException(status_code=409, detail=ENVIRONMENT_NAME_TAKEN)


def _active_run_exists(session: Session, environment: ApplicationEnvironment) -> bool:
    return (
        session.exec(
            select(TestRun.id).where(
                TestRun.environment_id == environment.id,
                col(TestRun.status).in_(_IN_PROGRESS),
            )
        ).first()
        is not None
    )


def _username_of(secret_ref: str, auth_method: str) -> str | None:
    if auth_method != "standard_login":
        return None
    creds = json.loads(VaultSecretsClient().resolve(SecretRef(path=secret_ref)))
    return creds.get("username")


def _read(
    application: Application, environment: ApplicationEnvironment | None, *, show_username: bool
) -> EnvironmentRead:
    source = environment or application
    return EnvironmentRead(
        id=environment.external_id if environment else None,
        name=environment.name if environment else application.environment,
        url=source.url,
        login_url=source.login_url,
        is_default=environment is None,
        auth_method=source.auth_method,
        username=_username_of(source.secret_ref, source.auth_method) if show_username else None,
    )


@router.get("/applications/{external_id}/environments", response_model=list[EnvironmentRead])
def list_environments(
    external_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUserDep,
    organization_id: CurrentOrgIdDep,
) -> list[EnvironmentRead]:
    application = _org_application(session, organization_id, external_id)
    show_username = user.role != "viewer"
    extras = session.exec(
        select(ApplicationEnvironment)
        .where(ApplicationEnvironment.application_id == application.id)
        .order_by(col(ApplicationEnvironment.created_at))
    ).all()
    return [_read(application, None, show_username=show_username)] + [
        _read(application, env, show_username=show_username) for env in extras
    ]


@router.post(
    "/applications/{external_id}/environments", response_model=EnvironmentRead, status_code=201
)
async def create_environment(
    external_id: uuid.UUID,
    payload: EnvironmentCreate,
    session: SessionDep,
    user: NotViewerDep,
    organization_id: CurrentOrgIdDep,
) -> EnvironmentRead:
    application = _org_application(session, organization_id, external_id)
    url = _main()._normalize_application_url(payload.url)
    _valid_http_url(url, "deployed URL")
    if payload.login_url:
        _valid_http_url(payload.login_url, "login URL")
    _check_name(session, application, payload.name)
    _require_login_rules(
        application,
        application.auth_method,
        username=payload.username,
        password=payload.password,
        login_url=payload.login_url,
    )
    require_approved_domain(session, organization_id, url)
    await _require_reachable(url)

    if application.auth_method == "standard_login":
        credential = json.dumps({"username": payload.username, "password": payload.password}).encode()
    else:
        credential = _EMPTY_SESSION
    vault = VaultSecretsClient()
    secret_ref = vault.store(organization_id, credential)
    try:
        environment = ApplicationEnvironment(
            application_id=application.id,
            name=payload.name,
            url=url,
            login_url=payload.login_url or None,
            auth_method=application.auth_method,
            requires_login=application.auth_method != "none",
            secret_ref=secret_ref.path,
        )
        session.add(environment)
        session.flush()
        record_activity(
            session,
            user,
            "settings",
            f"Added the {environment.name} environment to {application.name}",
            application=application,
            details={
                "info": [
                    {"label": "Environment", "value": environment.name},
                    {"label": "URL", "value": environment.url},
                    {"label": "Login page", "value": environment.login_url or "Not given"},
                ]
            },
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        vault.delete(secret_ref)
        raise HTTPException(status_code=409, detail=ENVIRONMENT_NAME_TAKEN) from exc
    except Exception:
        # Nothing references the secret once the row is gone — don't orphan it.
        session.rollback()
        vault.delete(secret_ref)
        raise
    return _read(application, environment, show_username=True)


@router.patch(
    "/applications/{external_id}/environments/{environment_id}", response_model=EnvironmentRead
)
async def update_environment(
    external_id: uuid.UUID,
    environment_id: uuid.UUID,
    payload: EnvironmentUpdate,
    session: SessionDep,
    user: NotViewerDep,
    organization_id: CurrentOrgIdDep,
) -> EnvironmentRead:
    application = _org_application(session, organization_id, external_id)
    environment = _get_environment(session, application, environment_id)
    sent = payload.model_fields_set
    # A run that already started keeps the URL/credentials it began with only
    # because nothing changes under it: refuse edits while one is in flight.
    if sent and _active_run_exists(session, environment):
        raise HTTPException(status_code=409, detail=ENVIRONMENT_RUNNING)

    name = payload.name if "name" in sent and payload.name is not None else environment.name
    url = environment.url
    if "url" in sent and payload.url:
        url = _main()._normalize_application_url(payload.url)
        _valid_http_url(url, "deployed URL")
    login_url = payload.login_url if "login_url" in sent else environment.login_url
    if login_url:
        _valid_http_url(login_url, "login URL")
    if name != environment.name:
        _check_name(session, application, name, except_id=environment.id)

    vault = VaultSecretsClient()
    existing: dict = {}
    if environment.auth_method == "standard_login":
        existing = json.loads(vault.resolve(SecretRef(path=environment.secret_ref)))
    # A blank password means "unchanged"; a blank username is an error (below).
    username = payload.username if "username" in sent else existing.get("username")
    password = (payload.password if "password" in sent else None) or existing.get("password")
    _require_login_rules(
        application,
        environment.auth_method,
        username=username,
        password=password,
        login_url=login_url,
    )

    if url != environment.url:
        require_approved_domain(session, organization_id, url)
        await _require_reachable(url)

    if environment.auth_method == "standard_login" and (
        {"username", "password", "mfa_enabled", "totp_seed"} & sent
    ):
        creds: dict[str, str | bool | None] = {"username": username, "password": password}
        mfa_enabled = (
            payload.mfa_enabled if "mfa_enabled" in sent else bool(existing.get("mfa_enabled"))
        )
        if mfa_enabled:
            totp_seed = (payload.totp_seed if "totp_seed" in sent else None) or existing.get(
                "totp_seed"
            )
            if not totp_seed:
                raise HTTPException(status_code=422, detail="totp_seed is required when mfa_enabled is set")
            creds["mfa_enabled"] = True
            creds["totp_seed"] = totp_seed
        vault.update(SecretRef(path=environment.secret_ref), json.dumps(creds).encode())

    environment.name, environment.url, environment.login_url = name, url, login_url or None
    session.add(environment)
    # Never the values — only that they changed.
    record_activity(
        session,
        user,
        "settings",
        f"Updated the {environment.name} environment of {application.name}",
        application=application,
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=ENVIRONMENT_NAME_TAKEN) from exc
    return _read(application, environment, show_username=True)


@router.delete("/applications/{external_id}/environments/{environment_id}", status_code=204)
def delete_environment(
    external_id: uuid.UUID,
    environment_id: uuid.UUID,
    session: SessionDep,
    user: NotViewerDep,
    organization_id: CurrentOrgIdDep,
) -> None:
    """Refused (409) while any run, or any live schedule, uses it — history is
    never left pointing at a deleted environment."""
    application = _org_application(session, organization_id, external_id)
    environment = _get_environment(session, application, environment_id)
    has_runs = (
        session.exec(select(TestRun.id).where(TestRun.environment_id == environment.id)).first()
        is not None
    )
    has_live_schedule = (
        session.exec(
            select(Schedule.id).where(
                Schedule.environment_id == environment.id,
                col(Schedule.deleted_at).is_(None),
            )
        ).first()
        is not None
    )
    if has_runs or has_live_schedule:
        raise HTTPException(status_code=409, detail=ENVIRONMENT_IN_USE)
    # Soft-deleted schedules no longer fire; release their FK so the delete can go through.
    session.execute(
        update(Schedule)
        .where(Schedule.environment_id == environment.id)  # type: ignore[arg-type]
        .values(environment_id=None)
    )
    secret_ref = SecretRef(path=environment.secret_ref)
    name = environment.name
    session.delete(environment)
    record_activity(
        session,
        user,
        "settings",
        f"Removed the {name} environment from {application.name}",
        application=application,
    )
    session.commit()
    # After the commit: a failed delete leaves a stray secret, never a row
    # that points at a destroyed one.
    VaultSecretsClient().delete(secret_ref)


def _reveal(session: Session, user, application: Application, source, label: str) -> EnvironmentReveal:
    if source.auth_method != "standard_login":
        raise HTTPException(status_code=422, detail="credential reveal is only supported for standard_login")
    creds = json.loads(VaultSecretsClient().resolve(SecretRef(path=source.secret_ref)))
    record_activity(
        session, user, "settings", f"Viewed the saved password for {label}", application=application
    )
    session.commit()
    return EnvironmentReveal(password=creds.get("password", ""))


# Application Settings shows the password behind an eye icon to anyone who can
# edit it (admins and members, never viewers — POST, so `block_viewer_writes`
# covers it too). The older admin-only `/credentials/{id}/reveal` is untouched.
@router.post("/applications/{external_id}/credentials/reveal", response_model=EnvironmentReveal)
def reveal_default_credentials(
    external_id: uuid.UUID,
    session: SessionDep,
    user: NotViewerDep,
    organization_id: CurrentOrgIdDep,
) -> EnvironmentReveal:
    application = _org_application(session, organization_id, external_id)
    return _reveal(session, user, application, application, application.name)


@router.post(
    "/applications/{external_id}/environments/{environment_id}/reveal",
    response_model=EnvironmentReveal,
)
def reveal_environment_credentials(
    external_id: uuid.UUID,
    environment_id: uuid.UUID,
    session: SessionDep,
    user: NotViewerDep,
    organization_id: CurrentOrgIdDep,
) -> EnvironmentReveal:
    application = _org_application(session, organization_id, external_id)
    environment = _get_environment(session, application, environment_id)
    return _reveal(
        session, user, application, environment, f"{application.name} ({environment.name})"
    )
