"""FailureExplanationRecord — the cached LLM explanation of one kind of test
failure no rule in `workflows.failure_explainer` recognises.

Keyed by `error_fingerprint` (a hash of the *redacted* error text), not by
TestResult: the same unknown error across tests and runs is explained once,
and no raw secret is ever stored. Separate from `test_result` on purpose —
self-healing never reads it, and nothing here changes `error_message`.

The primary key is also the claim: whichever API request inserts the row
first (`status="pending"`) is the only one that calls the LLM, so concurrent
polls and many results sharing an error never cause a duplicate call.
"""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

FailureExplanationStatus = Literal["pending", "done", "failed"]


class FailureExplanationRecord(SQLModel, table=True):
    __tablename__ = "failure_explanation"  # pyright: ignore[reportAssignmentType]

    error_fingerprint: str = Field(primary_key=True, max_length=64)
    status: str = Field(default="pending")
    title: str | None = Field(default=None)
    detail: str | None = Field(default=None)
    requested_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    completed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
