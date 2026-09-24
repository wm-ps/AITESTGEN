"""Record and Play — minting a `RecordingSession` (plan §1/§2/§10).

Mirrors `api.invites`/`api.password_reset`'s token design (the raw token is
the sole secret, never persisted — only its sha256 `token_hash` is) but the
raw token here is returned directly in this endpoint's own response body,
never emailed — there is no "SMTP not configured" fallback path for this
feature, so (unlike `invites.py`/`password_reset.py`'s own dev-fallback log
lines) there is never a reason to log it, and it must never appear in any
`logger.*` call anywhere in this app.
"""

import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from domain import RecordingSession
from sqlmodel import Session

from api.invites import _hash_token

RECORDING_TOKEN_EXPIRY = timedelta(minutes=30)

# The recording service (`apps/workers/recording`) is not `apps/api` — a
# separate deployable with its own websocket routes (plan: "not a Temporal
# worker... a plain FastAPI/websocket process"). This is the base this
# endpoint builds `vnc_ws_url`/`control_ws_url` from; ws(s):// scheme is the
# caller's responsibility to set correctly per environment.
RECORDING_SERVICE_WS_BASE = os.environ.get(
    "RECORDING_SERVICE_WS_BASE", "ws://localhost:8100"
)


def mint_recording_session(
    session: Session,
    *,
    application_id: uuid.UUID,
    created_by_id: uuid.UUID,
    auth_mode: str,
) -> tuple[RecordingSession, str]:
    token = secrets.token_urlsafe(32)
    recording_session = RecordingSession(
        application_id=application_id,
        created_by_id=created_by_id,
        token_hash=_hash_token(token),
        auth_mode=auth_mode,
        expires_at=datetime.now(UTC) + RECORDING_TOKEN_EXPIRY,
    )
    session.add(recording_session)
    session.commit()
    session.refresh(recording_session)
    return recording_session, token


def recording_ws_urls(token: str) -> tuple[str, str]:
    base = f"{RECORDING_SERVICE_WS_BASE}/recordings/{token}"
    return f"{base}/vnc", f"{base}/control"
