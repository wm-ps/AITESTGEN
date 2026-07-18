"""FormField — one input captured on a `Form` (Story 2.2, AD-8).

`captured_selector` holds whatever locator info was reasonably available at
fill-time (label association, `data-testid`, `name`/`id`, or a CSS-path
fallback) — needed by Story 2.5 to derive a `ComponentLocator` for this field;
without it, that field gets no usable locator at all, not just a lower-
fidelity one. `component_id` is a plain nullable column with no FK constraint
yet — mirrors the old `Evidence.journey_id` pattern: `component` doesn't
exist until Story 2.5's migration adds both the table and this column's FK.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class FormField(SQLModel, table=True):
    __tablename__ = "form_field"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=text("uuidv7()"),
        ),
    )
    form_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("form.id"), nullable=False, index=True),
    )
    # Nullable — a real input can carry no `name` attribute at all (e.g. a
    # quick-search box with no form submission semantics); Story 2.5 falls
    # back to a label/selector-based Component identity when this is null.
    name: str | None = Field(default=None)
    input_type: str = "text"
    required: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    default_value: str | None = Field(default=None)
    captured_selector: str | None = Field(default=None)
    # No ForeignKey yet — `component` table lands in Story 2.5's migration.
    component_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), nullable=True, index=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
