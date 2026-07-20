"""ValidationRule — a constraint captured on a `FormField` (Story 2.2, AD-8)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class ValidationRule(SQLModel, table=True):
    __tablename__ = "validation_rule"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=text("uuidv7()"),
        ),
    )
    form_field_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("form_field.id"), nullable=False, index=True
        ),
    )
    rule_type: str
    value: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
