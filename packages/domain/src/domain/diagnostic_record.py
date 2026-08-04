"""DiagnosticRecord — one typed row written by the discovery engine's
`record_diagnostic()` sink (Story 2.22 Task 1).

Seven producer stories (2.10, 2.11, 2.12, 2.13, 2.14, 2.19, 2.21) plus 2.18's
`DiscoveryError` all write through the same sink function in
`apps/workers/discovery`, distinguished only by `kind`. Payload is JSONB, not
typed columns, because these are diagnostics, not domain data — a producer
adds a field by changing its payload dict, never by writing a migration.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class DiagnosticRecord(SQLModel, table=True):
    __tablename__ = "diagnostic_record"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=text("uuidv7()"),
        ),
    )
    discovery_run_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("discovery_run.id"), nullable=False, index=True
        ),
    )
    # One kind per producing story ("state_identity", "safety",
    # "data_resolution", "loop_guard", "locator_durability",
    # "widget_coverage", "discovery_error", ...) — indexed so a report section
    # can query its own kind regardless of which other producers have landed.
    kind: str = Field(index=True, nullable=False)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
