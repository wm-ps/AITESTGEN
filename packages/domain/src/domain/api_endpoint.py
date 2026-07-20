"""ApiEndpoint — a typed, directly-captured API call (Story 2.2, AD-8).

Same canonical/merge shape as `Page`/`Form` — `merged_into_id` null =
canonical, written null always by `DiscoveryActivity`.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class ApiEndpoint(SQLModel, table=True):
    __tablename__ = "api_endpoint"  # pyright: ignore[reportAssignmentType]

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
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("api_endpoint.id"), nullable=True, index=True
        ),
    )
    method: str
    path: str
    # Captured alongside method/path so a negative/error-path Scenario (Story
    # 4.1) has real signal to draw from instead of hallucinating one —
    # nullable since not every capture backend (or a pre-existing row) has
    # response details available.
    status_code: int | None = None
    response_summary: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
