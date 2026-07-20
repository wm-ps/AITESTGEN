"""PageTransition — a captured navigation edge between two Pages (Story 2.2, AD-8).

No `merged_into_id` of its own — once `from_page_id`/`to_page_id` resolve to
canonical Pages (Story 2.5), a duplicate edge between the same canonical pair
collapses via find-or-create on that pair, not a merge scheme of its own.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class PageTransition(SQLModel, table=True):
    __tablename__ = "page_transition"  # pyright: ignore[reportAssignmentType]

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
    from_page_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("page.id"), nullable=False, index=True),
    )
    to_page_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("page.id"), nullable=False, index=True),
    )
    triggered_by_action_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("action.id"), nullable=True, index=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
