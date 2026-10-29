"""Authentication + Organization-scoping (Story 1.2, architecture AD-12).

Sign-in issues a signed, httpOnly session cookie (itsdangerous) — no OAuth/
JWT-library complexity needed for a same-origin SPA+API; a "boring
technology" choice, consistent with the architecture's general bias. This
exact mechanism is not fixed by the PRD or Architecture Spine.

`current_org_id` is the **one central mechanism** every authenticated
router depends on to scope queries by Organization (AD-12) — no endpoint
re-implements this.
"""

import hashlib
import os
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated

import bcrypt
import httpx
from domain import PlatformUser
from fastapi import Cookie, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from mailer import FRONTEND_BASE_URL
from sqlmodel import Session

from api.db import get_session

# Every role a PlatformUser/Invite may hold — the invite validator and the
# change-role endpoint both check against this one list. A "viewer" can read
# everything in its Organization but change nothing (`block_viewer_writes`).
ROLES = ("admin", "member", "viewer")
VIEWER_ROLE = "viewer"

_DEV_SECRET_KEY = "dev-only-insecure-secret-key"
# Local dev = the web app is on localhost; anything else is a real deployment.
_LOCAL_DEV = FRONTEND_BASE_URL.startswith(("http://localhost", "http://127.0.0.1"))
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", _DEV_SECRET_KEY)
if SESSION_SECRET_KEY == _DEV_SECRET_KEY and not _LOCAL_DEV:
    # Anyone who knows the public dev key could forge a session cookie.
    raise RuntimeError("SESSION_SECRET_KEY must be set outside local development")
COOKIE_NAME = "session"
# Secure by default on a real deployment; ops/k8s overrides it to "false"
# until TLS sits in front of the api Service.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", str(not _LOCAL_DEV)).lower() == "true"
# 15 minutes without real user activity logs the user out. The web app sends
# ACTIVITY_HEADER only on requests made shortly after a click/keypress
# (apps/web/src/api.ts), and `current_user` slides the cookie only for those —
# background polling of a long-running job never keeps a session alive.
IDLE_TIMEOUT = 15 * 60
# Even a constantly-active session ends this long after sign-in.
ABSOLUTE_TIMEOUT = 12 * 60 * 60
ACTIVITY_HEADER = "X-User-Activity"

_serializer = URLSafeTimedSerializer(SESSION_SECRET_KEY, salt="platform-session")

SessionDep = Annotated[Session, Depends(get_session)]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# Checked against when the email matches no account, so an unknown email
# takes as long as a wrong password and response time can't reveal which
# emails have accounts.
DUMMY_PASSWORD_HASH = hash_password("not-a-real-password")


def check_new_password(password: str) -> None:
    """Rejects a password found in a known data breach (Have I Been Pwned's
    k-anonymity range API — only the first 5 chars of the SHA-1 leave the
    server). Length is enforced by the request models (min 12)."""
    digest = hashlib.sha1(password.encode()).hexdigest().upper()
    try:
        response = httpx.get(f"https://api.pwnedpasswords.com/range/{digest[:5]}", timeout=3)
        response.raise_for_status()
    except httpx.HTTPError:
        # ponytail: fails open when the breach API is unreachable, so an
        # outage never blocks sign-up/reset; a local breach list if it must be strict.
        return
    if any(line.split(":")[0] == digest[5:] for line in response.text.splitlines()):
        raise HTTPException(
            status_code=422,
            detail="This password has appeared in a data breach. Choose a different one.",
        )


def issue_session_cookie(response: Response, user: PlatformUser, signed_in_at: int | None = None) -> None:
    """`signed_in_at` is carried over when sliding an existing session, so
    ABSOLUTE_TIMEOUT counts from the original sign-in."""
    token = _serializer.dumps([str(user.id), user.session_version, signed_in_at or int(time.time())])
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=IDLE_TIMEOUT,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


_INVALID_SESSION = (BadSignature, ValueError, TypeError)


def _read_session(session_cookie: str) -> tuple[uuid.UUID, int, int]:
    """(user id, session version, signed-in-at). Raises one of
    `_INVALID_SESSION` for a tampered, idle-expired, too-old or old-format cookie."""
    user_id, version, signed_in_at = _serializer.loads(session_cookie, max_age=IDLE_TIMEOUT)
    if time.time() - signed_in_at > ABSOLUTE_TIMEOUT:
        raise ValueError("session past its absolute lifetime")
    return uuid.UUID(user_id), int(version), int(signed_in_at)


def _session_owner(session: Session, session_cookie: str | None) -> tuple[PlatformUser, int] | None:
    """The cookie's user and its signed-in-at, or None if the cookie is
    missing/invalid or was revoked (its session version is out of date)."""
    if session_cookie is None:
        return None
    try:
        user_id, version, signed_in_at = _read_session(session_cookie)
    except _INVALID_SESSION:
        return None
    user = session.get(PlatformUser, user_id)
    if user is None or user.session_version != version:
        return None
    return user, signed_in_at


def end_all_sessions(user: PlatformUser) -> None:
    """Invalidates every session cookie this user holds, on every device.
    Caller commits."""
    user.session_version += 1


def end_session(session: Session, session_cookie: str | None) -> None:
    """Logout: revokes the cookie server-side, so a copied cookie stops
    working too, not just the browser's copy."""
    owner = _session_owner(session, session_cookie)
    if owner is not None:
        end_all_sessions(owner[0])
        session.add(owner[0])
        session.commit()


def current_user(
    request: Request,
    session: SessionDep,
    response: Response,
    session_cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> PlatformUser:
    if session_cookie is None:
        raise HTTPException(status_code=401, detail="not signed in")
    owner = _session_owner(session, session_cookie)
    if owner is None:
        raise HTTPException(status_code=401, detail="invalid session")
    # Loaded fresh on every request, so a role change (e.g. viewer -> member)
    # applies to an already-signed-in user's very next request.
    user, signed_in_at = owner
    if request.headers.get(ACTIVITY_HEADER) == "1":
        # Real user activity: slide the idle window (see IDLE_TIMEOUT) and
        # update the Team members page's "Last active" column.
        issue_session_cookie(response, user, signed_in_at)
        user.last_active_at = datetime.now(UTC)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


CurrentUserDep = Annotated[PlatformUser, Depends(current_user)]


def current_org_id(user: CurrentUserDep) -> uuid.UUID:
    """Every module (Onboarding, Review, Analytics) depends on this, never
    re-derives `organization_id` any other way (AD-12)."""
    return user.organization_id


CurrentOrgIdDep = Annotated[uuid.UUID, Depends(current_org_id)]


def require_admin(user: CurrentUserDep) -> PlatformUser:
    """Gate for admin-only actions (issuing/revoking Invites) — every seeded
    or invite-accepted PlatformUser has a `role`, checked here once rather
    than in each admin-only route."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    return user


CurrentAdminDep = Annotated[PlatformUser, Depends(require_admin)]


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# The only writes a viewer may make.
VIEWER_WRITE_ALLOWLIST = frozenset({"/auth/logout"})


def block_viewer_writes(request: Request, session: SessionDep) -> None:
    """Registered once on the whole app (`FastAPI(dependencies=...)`), so
    every route — including ones added later — is read-only for a viewer
    unless explicitly allowed: deny by default, not per-endpoint opt-in.

    Only identifies the caller; it never authenticates. No or an invalid
    session passes through to the route's own auth (public routes like
    login/accept-invite have none to pass), and it doesn't slide the session
    or touch `last_active_at` — `current_user` still does that once."""
    if request.method in _SAFE_METHODS or request.url.path in VIEWER_WRITE_ALLOWLIST:
        return
    owner = _session_owner(session, request.cookies.get(COOKIE_NAME))
    if owner is not None and owner[0].role == VIEWER_ROLE:
        raise HTTPException(status_code=403, detail="view-only access")


def require_not_viewer(user: CurrentUserDep) -> PlatformUser:
    """For the few *reads* a viewer may not have — the Allure report and the
    test-suite download (writes are already covered by `block_viewer_writes`)."""
    if user.role == VIEWER_ROLE:
        raise HTTPException(status_code=403, detail="view-only access")
    return user


NotViewerDep = Annotated[PlatformUser, Depends(require_not_viewer)]
