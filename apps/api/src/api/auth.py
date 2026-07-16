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
from typing import Annotated

import bcrypt
from domain import PlatformUser
from fastapi import Cookie, Depends, HTTPException, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlmodel import Session

from api.db import get_session

SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "dev-only-insecure-secret-key")
COOKIE_NAME = "session"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

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


def current_user(
    session: SessionDep,
    session_cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> PlatformUser:
    if session_cookie is None:
        raise HTTPException(status_code=401, detail="not signed in")
    try:
        user_id = uuid.UUID(_serializer.loads(session_cookie, max_age=COOKIE_MAX_AGE))
    except BadSignature as exc:
        raise HTTPException(status_code=401, detail="invalid session") from exc
    user = session.get(PlatformUser, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    return user


CurrentUserDep = Annotated[PlatformUser, Depends(current_user)]


def current_org_id(user: CurrentUserDep) -> uuid.UUID:
    """Every module (Onboarding, Review, Analytics) depends on this, never
    re-derives `organization_id` any other way (AD-12)."""
    return user.organization_id


CurrentOrgIdDep = Annotated[uuid.UUID, Depends(current_org_id)]
