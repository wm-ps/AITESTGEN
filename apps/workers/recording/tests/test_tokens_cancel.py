"""mark_cancelled_sync / load_session_for_connect's cancelled handling —
Postgres only. Each test creates its own Organization/Application/
RecordingSession and deletes everything under it afterwards."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from domain import Application, Organization, PlatformUser, RecordingSession
from recording_worker.db import engine
from recording_worker.tokens import (
    RecordingSessionCancelled,
    hash_token,
    load_session_for_connect,
    load_status_sync,
    mark_cancelled_sync,
)
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError, OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)


@pytest.fixture
def make_session():
    with Session(engine) as session:
        org = Organization(name=f"Recording Cancel Test Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        user = PlatformUser(
            organization_id=org.id,
            email=f"recording-cancel-{uuid.uuid4()}@test.invalid",
            name="Recording Cancel Test User",
            hashed_password="x",
        )
        app = Application(
            organization_id=org.id,
            name="Recording Cancel Test App",
            url="https://app.example.com",
            environment="test",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(user)
        session.add(app)
        session.commit()
        org_id, user_id, app_id = org.id, user.id, app.id

    def _make(status: str) -> tuple[str, uuid.UUID]:
        raw_token = uuid.uuid4().hex
        with Session(engine) as session:
            row = RecordingSession(
                application_id=app_id,
                created_by_id=user_id,
                token_hash=hash_token(raw_token),
                name="cancel test",
                auth_mode="logged_out",
                expires_at=datetime.now(UTC) + timedelta(minutes=30),
                status=status,
            )
            session.add(row)
            session.commit()
            return raw_token, row.id

    yield _make

    with Session(engine) as session:
        for statement, params in (
            ("DELETE FROM recording_session WHERE application_id = :id", {"id": app_id}),
            ("DELETE FROM application WHERE id = :id", {"id": app_id}),
            ("DELETE FROM platform_user WHERE id = :id", {"id": user_id}),
            ("DELETE FROM organization WHERE id = :id", {"id": org_id}),
        ):
            session.exec(text(statement), params=params)
        session.commit()


@pytest.mark.parametrize("status", ["pending", "recording"])
def test_mark_cancelled_transitions_a_live_session(make_session, status):
    _, row_id = make_session(status)

    assert mark_cancelled_sync(row_id) is True
    assert load_status_sync(row_id) == "cancelled"


@pytest.mark.parametrize("status", ["complete", "failed", "cancelled"])
def test_mark_cancelled_never_overwrites_a_terminal_session(make_session, status):
    _, row_id = make_session(status)

    assert mark_cancelled_sync(row_id) is False
    assert load_status_sync(row_id) == status


def test_reconnecting_to_a_cancelled_session_is_rejected_as_cancelled(make_session):
    raw_token, row_id = make_session("recording")
    mark_cancelled_sync(row_id)

    with pytest.raises(RecordingSessionCancelled):
        load_session_for_connect(raw_token)
