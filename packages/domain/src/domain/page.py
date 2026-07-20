"""Page — a typed, directly-captured page visit (Story 2.2, AD-8).

Written directly by `DiscoveryActivity`, always with `merged_into_id=null` —
this story never resolves duplicates (that's `ApplicationModelBuilderActivity`,
Story 2.5). `merged_into_id` is a nullable self-FK: null means this row is
canonical, set means it's been superseded by the row it points at. Scoped by
both `application_id` (so the same logical page is recognized across
Discovery Runs — what makes the model reusable) and `discovery_run_id`
(capture provenance). Screenshots are referenced via `object_storage_key`,
never stored inline.

Journey attribution no longer lives here — `InferenceActivity` (Story 2.6)
attributes a canonical Page to a Journey via a `JourneyStep` row instead of a
bare FK on this table, so one Page can support more than one Journey.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class Page(SQLModel, table=True):
    __tablename__ = "page"  # pyright: ignore[reportAssignmentType]

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
    # Nullable self-FK — null = canonical. Only ApplicationModelBuilderActivity
    # (Story 2.5) ever sets this on an existing row (AD-14).
    merged_into_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("page.id"), nullable=True, index=True),
    )
    url: str
    title: str = ""
    object_storage_key: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
