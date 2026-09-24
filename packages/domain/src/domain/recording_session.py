"""RecordingSession — an in-progress Record and Play session (Round 1-3 plan).

Gates the handshake for a worker-hosted, human-driven recording: a human
drives a real headed Chromium via the real `playwright codegen` CLI, running
in `apps/workers/recording`, streamed back over a VNC-family remote-desktop
transport. Mirrors `Invite`/`PasswordReset`'s token design (`token_hash` is
the sole secret, sha256 of a `secrets.token_urlsafe` value never itself
persisted) but, unlike those two, adds a `status` column: a recording
session has real async lifecycle beyond one-shot token validity (a
long-lived, possibly-failing background browser process), which `used_at`/
`expires_at` alone can't express — `used_at` here means "a websocket has
first connected", not "no further reconnects allowed" (a disconnect within
the service's own grace-period window reconnects to the same still-running
session; see the recording service's own session-lifecycle module).

`auth_mode` is fixed at mint time and decides whether the recording service
starts Codegen against a fresh, logged-out browser ("logged_out" — the
human's own recorded actions include the login step, and the resulting
TestAsset is tagged `@public`) or one pre-loaded with the Application's
existing stored credential/session via `--load-storage` ("authenticated" —
no login step is recorded, and the resulting TestAsset is tagged `@auth`,
reusing `Application.secret_ref` exactly like every other `@auth` spec —
nothing new is added to the credential surface).
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Column, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

RecordingAuthMode = Literal["logged_out", "authenticated"]
RecordingSessionStatus = Literal["pending", "recording", "complete", "failed"]


class RecordingSession(SQLModel, table=True):
    __tablename__ = "recording_session"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=text("uuidv7()"),
        ),
    )
    external_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), unique=True, nullable=False, index=True),
    )
    application_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("application.id"), nullable=False, index=True
        ),
    )
    created_by_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("platform_user.id"), nullable=False),
    )
    token_hash: str = Field(unique=True, index=True, nullable=False)
    auth_mode: str = Field(
        sa_column=Column(String, nullable=False),
    )
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    used_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    status: str = Field(
        default="pending",
        sa_column=Column(String, server_default=text("'pending'"), nullable=False),
    )
    error_message: str | None = Field(default=None)
    journey_external_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True)
    )
    scenario_external_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
