"""Component — a derived, automatable element (Story 2.5, AD-8/AD-14).

Never raw-captured — only `ApplicationModelBuilderActivity` writes this,
grouping canonical `Action` rows (buttons/links) or canonical `FormField`
rows (inputs) on the same canonical `Page`/`Form`. No `discovery_run_id` —
Component is purely Application-scoped, derived from potentially many runs'
captures, same reasoning as `Capability`. `form_id` is set only for
field-type Components (button/link Components leave it null); `target_page_id`
is set only for buttons/links that navigate (null for form fields).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class Component(SQLModel, table=True):
    __tablename__ = "component"  # pyright: ignore[reportAssignmentType]

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
    form_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("form.id"), nullable=True, index=True),
    )
    name: str
    type: str
    action: str
    target_page_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("page.id"), nullable=True, index=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
