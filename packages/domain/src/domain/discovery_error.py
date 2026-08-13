"""DiscoveryError — a starter error taxonomy for engine crashes and
target-application failures (Story 2.18 Task 1).

A typed row, not a generic `DiagnosticRecord` payload — Story 2.22's report
reads this table directly for its Errored category (same reasoning as
`SyntheticDataEntry`: a typed row is queryable on its own terms, not just
buried in a JSONB blob). `error_code` is a starter, deliberately small
taxonomy (DISC-001..006, see the Literal below) — do not expand it ad hoc.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

ErrorCode = Literal["DISC-001", "DISC-002", "DISC-003", "DISC-004", "DISC-005", "DISC-006"]


class DiscoveryError(SQLModel, table=True):
    __tablename__ = "discovery_error"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (Index("ix_discovery_error_run_code", "discovery_run_id", "error_code"),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")),
    )
    application_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("application.id"), nullable=False, index=True
        ),
    )
    discovery_run_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("discovery_run.id"), nullable=False, index=True
        ),
    )
    page_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("page.id"), nullable=True),
    )
    # str, not the Literal — same SQLModel/Literal limitation noted on every
    # other entity in this package (e.g. `Application.auth_method`).
    error_code: str = Field(nullable=False)
    message: str
    retry_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
