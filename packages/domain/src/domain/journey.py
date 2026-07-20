"""Journey — a candidate business workflow inferred from the Application Model (Story 2.6, AD-8/AD-13).

`discovery_run_id` identifies which Discovery Run *discovered* the Journey —
set once at creation, immutable, independent of how many times it's later
regenerated (AD-8). `identity_key` is a deterministic fingerprint of the
Journey's underlying evidence shape, never its AI-generated `name` (AD-13) —
`InferenceActivity` is the only writer of both.

No `approved`/`rejected` status — Approve/Reject were cut (2026-07-15); every
non-`deleted` Journey is in the Trusted Knowledge Model immediately (FR-14).
`attempt` starts at `1` here (no approval step to increment it); Story 4.3's
regeneration endpoint is what increments it later.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Column, DateTime, ForeignKey, inspect, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import validates
from sqlmodel import Field, SQLModel

JourneyStatus = Literal["candidate", "deleted"]


class Journey(SQLModel, table=True):
    __tablename__ = "journey"  # pyright: ignore[reportAssignmentType]

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
    discovery_run_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("discovery_run.id"),
            nullable=False,
            index=True,
        ),
    )
    capability_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("capability.id"),
            nullable=True,
            index=True,
        ),
    )
    status: str = Field(default="candidate")
    name: str
    identity_key: str = Field(index=True)
    attempt: int = Field(default=1)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    @validates("discovery_run_id")
    def _discovery_run_id_is_immutable(self, key: str, value: uuid.UUID) -> uuid.UUID:
        state = inspect(self)
        assert state is not None
        if state.persistent and value != self.discovery_run_id:
            raise ValueError("Journey.discovery_run_id is immutable once set (AD-8)")
        return value
