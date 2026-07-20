"""ComponentLocator — one automation locator for a `Component` (Story 2.5).

One mechanism for every locator, whether the Component is a button or a form
field: `kind="preferred"` plus zero or more `kind="fallback"`, ordered by
`priority`.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class ComponentLocator(SQLModel, table=True):
    __tablename__ = "component_locator"  # pyright: ignore[reportAssignmentType]

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
    component_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("component.id"), nullable=False, index=True
        ),
    )
    kind: str = "preferred"
    strategy: str
    value: str
    priority: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
