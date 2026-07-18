"""Action — a typed, directly-captured UI action (Story 2.2, AD-8).

No `merged_into_id` and no `journey_id` — raw `Action` rows are historical
capture detail, never merged into each other; Story 2.5's `Component` is the
deduped/canonical unit built *from* grouped Action rows, and only Component
ever gets a `journey_id`. `representative` is set `true` for the one instance
a repeated identical action pattern samples (AC 6) — every other instance of
that pattern gets no `Action` row at all, not a `representative=false` one.
`captured_selector` mirrors `FormField.captured_selector`'s purpose, for
Story 2.5's button/link `ComponentLocator` derivation.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class Action(SQLModel, table=True):
    __tablename__ = "action"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=text("uuidv7()"),
        ),
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
    page_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("page.id"), nullable=False, index=True),
    )
    description: str
    captured_selector: str | None = Field(default=None)
    representative: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
