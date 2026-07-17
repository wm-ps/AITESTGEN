"""Capability — groups related Journeys for one Application (Story 2.5).

Scoped to `Application` per the Core-Entity ERD. `status` mirrors `Journey`'s
shape (`"candidate" | "deleted"`) — Capability curation isn't Epic 3's
explicit focus, but nothing else in the planning artifacts gives it a
different shape, so this is a deliberate inference, not a literal schema.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

CapabilityStatus = Literal["candidate", "deleted"]


class Capability(SQLModel, table=True):
    __tablename__ = "capability"  # pyright: ignore[reportAssignmentType]

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
    status: str = Field(default="candidate")
    name: str
    description: str = Field(default="")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
