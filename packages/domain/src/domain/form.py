"""Form — a typed, directly-captured form submission (Story 2.2, AD-8).

Same canonical/merge shape as `Page`: `merged_into_id` null = canonical,
written null always by `DiscoveryActivity`. `page_id` points at whatever
`Page` row was current at capture time (may itself later be superseded —
resolve through to the canonical Page when reading, same as any FK here).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class Form(SQLModel, table=True):
    __tablename__ = "form"  # pyright: ignore[reportAssignmentType]

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
    merged_into_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("form.id"), nullable=True, index=True),
    )
    action_url: str
    method: str = "GET"
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
