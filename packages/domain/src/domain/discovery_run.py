"""DiscoveryRun — one bounded execution of the DiscoveryWorkflow (AD-1).

Story 1.3 absorbs the former Story 1.5's job: onboarding an Application
starts a DiscoveryRun (`status="running"`) in the same request, no separate
"Start Discovery Run" action. Story 2.3 adds the `complete` transition;
Story 2.4 adds `failed`/`failure_reason` (AD-11) — `session_expired` is the
one value the Architecture Spine names explicitly, meaningful only when
`status="failed"`. Follows the same UUIDv7-internal / UUIDv4-external split
`Application` establishes.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class DiscoveryRun(SQLModel, table=True):
    __tablename__ = "discovery_run"  # pyright: ignore[reportAssignmentType]

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
            PGUUID(as_uuid=True),
            ForeignKey("application.id"),
            nullable=False,
            index=True,
        ),
    )
    status: str = Field(default="running")
    failure_reason: str | None = Field(default=None)
    # initializing | authenticating | discovering | analyzing — meaningful
    # only while status="running" (AD-10 extension, sprint-change-proposal
    # 2026-07-21 CR-2). Set by Stories 2.1/2.2/2.6; read by Story 2.7.
    stage: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
