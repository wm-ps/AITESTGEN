"""Evidence — raw discovery signal captured for a DiscoveryRun (Story 2.2, AD-8).

Captured and tagged with `discovery_run_id` only; attribution to a specific
Journey (`journey_id`) happens later, exclusively via `InferenceActivity`
(Story 2.5) — `DiscoveryActivity` must never set it. Large binary artifacts
(screenshots, DOM snapshots) are referenced via `object_storage_key`, never
stored inline here — `details` holds only structured metadata (URL, action
type, API call signature, ...).
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

EvidenceType = Literal["page", "action", "form", "api_call", "state_transition"]


class Evidence(SQLModel, table=True):
    __tablename__ = "evidence"  # pyright: ignore[reportAssignmentType]

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
    # Nullable — set only by InferenceActivity (Story 2.5), never DiscoveryActivity.
    journey_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("journey.id"),
            nullable=True,
            index=True,
        ),
    )
    type: str  # EvidenceType values; plain str, matching Application.auth_method's convention
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    object_storage_key: str | None = Field(default=None)
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
