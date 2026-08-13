"""SyntheticDataEntry — every value the Data Resolver used, with its
resolution source and success outcome (Story 2.13 Task 4).

Written for **every** resolved value, not only synthesized ones — pool and
reused values matter equally for the "what data touched the target
application" report (Dev Notes). `outcome` is populated by the
success-feedback loop (AC 2/3): a value later found to have been rejected by
the application is demoted and never reused for the same `normalized_key`
again this run.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

DataSource = Literal["pool", "page", "reused", "synthetic"]
Outcome = Literal["success", "rejected", "unknown"]


class SyntheticDataEntry(SQLModel, table=True):
    __tablename__ = "synthetic_data_entry"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")),
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
    page_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("page.id"), nullable=True),
    )
    field_name: str
    normalized_key: str
    # str, not the Literal — see Application.auth_method's docstring for why
    # (SQLModel can't infer a column type from Literal).
    value: str
    source: str = Field(default="synthetic")
    is_placeholder_file: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    outcome: str = Field(default="unknown")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
