"""TestRun — one "Run All Tests" execution attempt for an Application (Run
All Tests feature).

Every click creates a new row — runs are immutable and never overwritten,
so history is just every `TestRun` for an Application ordered by
`created_at`. `environment_snapshot`/`target_base_url_snapshot` freeze
`Application.environment`/`url` at start time, so a later edit to the
Application never rewrites what a past run's audit trail says it ran
against (the same reason `Scenario.generation_run_id` freezes
`Journey.attempt` rather than deriving it live).

`execution_policy_id`/`execution_policy_version` are nullable — Run All
Tests no longer requires (or enforces) an `ExecutionPolicy` at all (see
`execution_worker.activities._prepare_test_run_sync`'s own ponytail note);
these columns are vestigial from when it did, kept nullable rather than
dropped in case policy-gated execution is reintroduced later. `status`
stays a plain `str` (not constrained to `TestRunStatus`'s `"blocked"` value
in practice today) for the same reason — nothing sets `"blocked"` anymore,
but the column/status value isn't removed; the Application Workspace UI
relabels a nonzero `blocked_count` as "Skipped" rather than adding a new
column for it.

`triggered_by_name` (Application Workspace feature) is who clicked "Run All
Tests"/"Run Suite" — this app has no scheduling/CI, only manual runs, so
this is the whole "trigger" concept; nullable because a run started outside
the API (e.g. directly via Temporal CLI, as this feature's own manual
verification step already does) has no user to attribute.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

TestRunStatus = Literal["pending", "running", "completed", "blocked"]


class TestRun(SQLModel, table=True):
    __test__ = False  # pytest: not a test class, despite the name prefix
    __tablename__ = "test_run"  # pyright: ignore[reportAssignmentType]

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
    status: str = Field(default="pending")
    execution_policy_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("execution_policy.id"), nullable=True
        ),
    )
    execution_policy_version: int | None = Field(default=None)
    environment_snapshot: str
    target_base_url_snapshot: str
    triggered_by_name: str | None = Field(default=None)
    blocked_reason: str | None = Field(default=None)
    total_count: int = Field(default=0)
    passed_count: int = Field(default=0)
    failed_count: int = Field(default=0)
    timed_out_count: int = Field(default=0)
    errored_count: int = Field(default=0)
    blocked_count: int = Field(default=0)
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
