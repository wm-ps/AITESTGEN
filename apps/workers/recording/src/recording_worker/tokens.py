"""Token hashing/lookup — same `sha256(raw)` pattern `api.invites._hash_token`
and `api.password_reset` already use (plan §2/§10): only the hash is ever
persisted, and the raw token itself must never be logged anywhere in this
app or in `apps/api`."""

import hashlib
import uuid
from datetime import UTC, datetime

from domain import RecordingSession
from sqlmodel import Session, select

from recording_worker.db import engine


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class InvalidRecordingToken(Exception):
    """Unknown token, or a real one that is expired/already terminal — the
    caller closes the websocket with an authentication-failure code; no
    session process tree is ever launched for it (plan §10 verification)."""


def load_session_for_connect(raw_token: str) -> RecordingSession:
    """Validated at *every* connect (mint-time validity isn't reused
    silently, plan §10) — but reconnect within the grace window is a valid
    connect too, so this only rejects a token that's outright unknown,
    past `expires_at` while still `pending` (never used), or in a terminal
    state (`complete`/`failed`) — `status == "recording"` stays acceptable
    for as long as the runtime itself is willing to reattach it (plan §3)."""
    token_hash = hash_token(raw_token)
    with Session(engine) as session:
        recording_session = session.exec(
            select(RecordingSession).where(RecordingSession.token_hash == token_hash)
        ).first()
        if recording_session is None:
            raise InvalidRecordingToken("unknown token")
        if recording_session.status in ("complete", "failed"):
            raise InvalidRecordingToken("session already finished")
        if recording_session.status == "pending" and recording_session.expires_at < datetime.now(
            UTC
        ):
            raise InvalidRecordingToken("token expired before first connect")
        session.expunge(recording_session)
        return recording_session


def mark_first_connect_sync(recording_session_id: uuid.UUID) -> None:
    with Session(engine) as session:
        row = session.get(RecordingSession, recording_session_id)
        assert row is not None
        if row.used_at is None:
            row.used_at = datetime.now(UTC)
        row.status = "recording"
        session.add(row)
        session.commit()


def mark_complete_sync(
    recording_session_id: uuid.UUID,
    *,
    journey_external_id: uuid.UUID,
    scenario_external_id: uuid.UUID,
) -> None:
    with Session(engine) as session:
        row = session.get(RecordingSession, recording_session_id)
        assert row is not None
        row.status = "complete"
        row.journey_external_id = journey_external_id
        row.scenario_external_id = scenario_external_id
        session.add(row)
        session.commit()


def mark_failed_sync(recording_session_id: uuid.UUID, *, error_message: str) -> None:
    with Session(engine) as session:
        row = session.get(RecordingSession, recording_session_id)
        assert row is not None
        row.status = "failed"
        row.error_message = error_message
        session.add(row)
        session.commit()
