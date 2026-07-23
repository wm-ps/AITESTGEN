"""TestSuite — a named, per-Journey collection of Test Assets (Story 4.2).

One `TestSuite` per Journey per attempt, mirroring `Scenario.journey_id`'s own
convention (not a separate Application-wide grouping). `name` is auto-derived
from the Journey's own name at creation time — there is no manual naming
step (Story 4.2 AC 2). `generation_run_id` is simply `Journey.attempt`, the
same convention `Scenario.generation_run_id` already uses, since a
`TestSuite` is Journey-scoped exactly like `Scenario` is.

`UNIQUE(journey_id, generation_run_id)` is what makes
`EnsureTestSuiteActivity`'s insert-or-fetch idempotent under a real
concurrent race (two `PlaywrightGenerationActivity` calls for the same
Journey both trying to create "their" `TestSuite` at once) — a database
constraint, not just a select-then-create query.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class TestSuite(SQLModel, table=True):
    __test__ = False  # pytest: not a test class, despite the name prefix
    __tablename__ = "test_suite"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint(
            "journey_id", "generation_run_id", name="uq_test_suite_journey_id_generation_run_id"
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
    journey_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("journey.id"), nullable=False, index=True
        ),
    )
    name: str
    generation_run_id: int
    current: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
