"""TestAsset — one compiled Playwright test, generated from one Scenario (Story 4.2).

`scenario_id`: one `TestAsset` compiles from one `Scenario`. `test_suite_id`:
every `TestAsset` belongs to exactly one `TestSuite` (its Scenario's
Journey's suite for this attempt).

Deliberately has **no `generation_run_id` field of its own** — it's always
derivable via `test_suite_id` -> `TestSuite.generation_run_id`, and always
correct: unlike `Scenario` (whose parent `Journey.attempt` is a *mutable*
counter that keeps incrementing across regenerations, so `Scenario` must
freeze its own copy at creation time), `TestSuite` is itself already a
frozen, one-row-per-attempt entity — deriving through it can never go stale.
Storing a second, redundant copy here would only add a second source of
truth that could drift out of sync with its own `test_suite_id`, for no
benefit (the same "derive over duplicate" principle this codebase already
applies to `Scenario.test_data_complete()`).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class TestAsset(SQLModel, table=True):
    __test__ = False  # pytest: not a test class, despite the name prefix
    __tablename__ = "test_asset"  # pyright: ignore[reportAssignmentType]

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
    scenario_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("scenario.id"), nullable=False, index=True
        ),
    )
    test_suite_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("test_suite.id"), nullable=False, index=True
        ),
    )
    code: str
    current: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
