"""TestResult — one TestAsset's outcome within one TestRun (Run All Tests
feature).

`scenario_id` is denormalized from `test_asset_id` (the same pattern
`TestAsset` itself uses, denormalizing through `test_suite_id` rather than
requiring an extra join) purely so results can be listed/joined without an
extra hop through `TestAsset` on the hot path of polling a run.

`status="blocked"` means `PrepareTestRunActivity` excluded this test before
execution ever started — its `Scenario.safety_classification` was
`DESTRUCTIVE`/`UNKNOWN` and the `ExecutionPolicy` didn't permit it —
`blocked_reason` explains why. Every other non-`pending` status is a real
Playwright outcome, never a safety-gate outcome.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

TestResultStatus = Literal["pending", "passed", "failed", "timed_out", "errored", "blocked"]


class TestResult(SQLModel, table=True):
    __test__ = False  # pytest: not a test class, despite the name prefix
    __tablename__ = "test_result"  # pyright: ignore[reportAssignmentType]

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
    test_run_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("test_run.id"), nullable=False, index=True
        ),
    )
    test_asset_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("test_asset.id"), nullable=False, index=True
        ),
    )
    scenario_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("scenario.id"), nullable=False, index=True
        ),
    )
    status: str = Field(default="pending")
    duration_ms: int | None = Field(default=None)
    error_message: str | None = Field(default=None)
    stack_trace: str | None = Field(default=None)
    console_output: str | None = Field(default=None)
    blocked_reason: str | None = Field(default=None)
    started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    completed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    # Self-healing (HealTestActivity) — two independent budgets, never
    # combined. auto_heal_attempt_count is spent by the automatic path (run
    # right after ExecuteTestActivity), capped at the fixed
    # AUTO_HEAL_ATTEMPT_CAP (see execution_workflow.py). manual_heal_attempt_count
    # is spent only by the manual "Retry with self-healing" endpoint, capped
    # at the admin-configurable DiscoverySettings.max_heal_attempts. Either
    # can be exhausted while the other still has budget.
    auto_heal_attempt_count: int = Field(default=0)
    manual_heal_attempt_count: int = Field(default=0)
    # The *latest* TestAsset a heal attempt produced (set on every attempt
    # that passes typecheck, whether or not that version then passes
    # execution) — combined with `status`, distinguishes "healed and now
    # passing" from "healed but still failing" with no extra field.
    healed_test_asset_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("test_asset.id"), nullable=True),
    )
    # Concurrency guard, not business data: set to the current time while a
    # HealTestActivity invocation (automatic or manual) is actively working
    # this TestResult, cleared back to None when it finishes. Lets the
    # manual-retry endpoint refuse a click that would race an in-flight
    # automatic heal for the same result; a claim older than
    # HEAL_ACTIVITY_STALE_AFTER (see execution_workflow.py) is treated as
    # abandoned (worker crash) rather than a permanent lock.
    heal_started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
