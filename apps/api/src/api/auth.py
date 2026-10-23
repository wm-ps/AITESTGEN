"""Authentication + Organization-scoping (Story 1.2, architecture AD-12).

Sign-in issues a signed, httpOnly session cookie (itsdangerous) — no OAuth/
JWT-library complexity needed for a same-origin SPA+API; a "boring
technology" choice, consistent with the architecture's general bias. This
exact mechanism is not fixed by the PRD or Architecture Spine.

`current_org_id` is the **one central mechanism** every authenticated
router depends on to scope queries by Organization (AD-12) — no endpoint
re-implements this.
"""

import os
import uuid
from datetime import UTC, datetime
from typing import Annotated

import bcrypt
from domain import PlatformUser
from fastapi import Cookie, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlmodel import Session

from api.db import get_session

# Every role a PlatformUser/Invite may hold — the invite validator and the
# change-role endpoint both check against this one list. A "viewer" can read
# everything in its Organization but change nothing (`block_viewer_writes`).
ROLES = ("admin", "member", "viewer")
VIEWER_ROLE = "viewer"

SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "dev-only-insecure-secret-key")
COOKIE_NAME = "session"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
# 1 hour of inactivity logs the user out (security requirement — a session
# used to live 7 fixed days regardless of activity). `current_user` re-issues
# this cookie with a fresh timestamp on every authenticated request, so it's
# a sliding idle window, not an absolute one: any real usage — including a
# browser tab left open polling a long-running discovery/generation/
# execution job — keeps sliding it forward. Only true silence (tab closed or
# genuinely idle) past this many seconds expires it.
COOKIE_MAX_AGE = 60 * 60

_serializer = URLSafeTimedSerializer(SESSION_SECRET_KEY, salt="platform-session")

SessionDep = Annotated[Session, Depends(get_session)]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def issue_session_cookie(response: Response, user_id: uuid.UUID) -> None:
    token = _serializer.dumps(str(user_id))
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


def _session_user_id(session_cookie: str) -> uuid.UUID:
    """Raises BadSignature for a tampered or expired cookie."""
    return uuid.UUID(_serializer.loads(session_cookie, max_age=COOKIE_MAX_AGE))


def current_user(
    session: SessionDep,
    response: Response,
    session_cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> PlatformUser:
    if session_cookie is None:
        raise HTTPException(status_code=401, detail="not signed in")
    try:
        user_id = _session_user_id(session_cookie)
    except BadSignature as exc:
        raise HTTPException(status_code=401, detail="invalid session") from exc
    # Loaded fresh on every request, so a role change (e.g. viewer -> member)
    # applies to an already-signed-in user's very next request.
    user = session.get(PlatformUser, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    # Slide the idle window forward on every authenticated request (see
    # COOKIE_MAX_AGE's docstring) — every route depending on CurrentUserDep
    # gets this for free, one choke point.
    issue_session_cookie(response, user.id)
    # Team members page's "Last active" column — same choke point, so it
    # reflects real session activity rather than only login time.
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
    session_cookie = request.cookies.get(COOKIE_NAME)
    if session_cookie is None:
        return
    try:
        user_id = _session_user_id(session_cookie)
    except (BadSignature, ValueError):
        return
    user = session.get(PlatformUser, user_id)
    if user is not None and user.role == VIEWER_ROLE:
        raise HTTPException(status_code=403, detail="view-only access")


def require_not_viewer(user: CurrentUserDep) -> PlatformUser:
    """For the few *reads* a viewer may not have — the Allure report and the
    test-suite download (writes are already covered by `block_viewer_writes`)."""
    if user.role == VIEWER_ROLE:
        raise HTTPException(status_code=403, detail="view-only access")
    return user


NotViewerDep = Annotated[PlatformUser, Depends(require_not_viewer)]
