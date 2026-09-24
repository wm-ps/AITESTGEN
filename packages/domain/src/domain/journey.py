"""Journey — a candidate business workflow inferred from the Application Model (Story 2.6, AD-8/AD-13).

`discovery_run_id` identifies which Discovery Run *discovered* the Journey —
set once at creation, immutable, independent of how many times it's later
regenerated (AD-8). `identity_key` is a deterministic fingerprint of the
Journey's underlying evidence shape, never its AI-generated `name` (AD-13) —
`InferenceActivity` is the only writer of both.

`application_id` is denormalized here (not just reachable transitively via
`discovery_run_id -> DiscoveryRun.application_id`) specifically so
`UNIQUE(application_id, identity_key)` can be a real, single-table Postgres
constraint — a race between two overlapping `InferenceActivity` runs against
the same Application is caught by the database, not just by a
select-then-create query. `InferenceActivity` already resolves the
`Application` row before creating a `Journey`, so populating this costs
nothing extra.

No `approved`/`rejected` status — Approve/Reject were cut (2026-07-15); every
non-`deleted` Journey is in the Trusted Knowledge Model immediately (FR-14).
`attempt` starts at `1` here (no approval step to increment it). No feature
increments it today — Story 4.3/FR-18 (regeneration) is cut in full, see
sprint-change-proposal-2026-07-27.md.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import validates
from sqlmodel import Field, SQLModel

JourneyStatus = Literal["candidate", "deleted"]


class Journey(SQLModel, table=True):
    __tablename__ = "journey"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint(
            "application_id", "identity_key", name="uq_journey_application_id_identity_key"
        ),
    )

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
    description: str | None = Field(default=None)
    # No standalone index — every real lookup filters by application_id
    # together with identity_key, which the composite unique constraint
    # above already indexes.
    identity_key: str
    attempt: int = Field(default=1)
    # Only populated for a `LiveExplorationTestWorkflow` Journey — the
    # literal, ordered transcript of what the live-exploration agent
    # actually clicked/typed/observed (see `LiveFlowModel.steps`), so
    # `ScenarioGenerationActivity` can ground Scenario steps in the real
    # session instead of the crawler-shaped Form/Component reinterpretation,
    # which has no way to represent a plain navigation click. Never set for
    # a crawler/discovery Journey.
    captured_flow: list[dict] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    # `[ADDED]` Set by `ScenarioGenerationActivity` when it catches its own
    # failure instead of letting it propagate — `GenerationWorkflow` has no
    # per-scenario fault isolation the way `SuiteGenerationWorkflow` does
    # (see that workflow's own comment), so before this field existed a
    # Journey whose generation genuinely failed stayed at 0 Scenarios
    # forever, with no durable record of why, and the Review Scenarios
    # screen's `journeysCovered >= journeys.length` completion check could
    # never pass — the progress bar spun forever with nothing to show the
    # user. Cleared at the start of every generation attempt (never sticks
    # around from an old attempt once a new one starts).
    generation_error: str | None = Field(default=None)
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
