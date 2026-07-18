"""Assertion — a derived expected outcome (Story 2.5, AD-8/AD-14).

Never raw-captured — derived from canonical `PageTransition`/`ApiEndpoint`
outcomes attached to a canonical `Page`. `component_id` is set only when the
assertion targets a specific element's state; null for a page/API-level
outcome.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class Assertion(SQLModel, table=True):
    __tablename__ = "assertion"  # pyright: ignore[reportAssignmentType]

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
    page_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("page.id"), nullable=False, index=True),
    )
    component_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("component.id"), nullable=True, index=True
        ),
    )
    journey_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("journey.id"), nullable=True, index=True),
    )
    kind: str
    expected_value: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
