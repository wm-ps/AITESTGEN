"""JourneyStep — one ordered, stage-labeled step attributing a canonical
Application Model row to a Journey (Story 2.6, AD-8/AD-14).

Replaces the earlier bare `journey_id` FK directly on `Page`/`Form`/
`ApiEndpoint`/`Component` (that shape had nowhere to record order or a stage
label, and made it structurally impossible for one canonical row to support
more than one Journey — e.g. a shared login page). Exactly one of
`page_id`/`form_id`/`api_endpoint_id`/`component_id` is set per row,
enforced by a DB `CHECK` constraint, mirroring how canonical rows are
already typed rather than polymorphic. `InferenceActivity` is the sole
writer; it never references a row whose `merged_into_id` is set.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

_EXACTLY_ONE_TARGET = (
    "(CASE WHEN page_id IS NOT NULL THEN 1 ELSE 0 END) + "
    "(CASE WHEN form_id IS NOT NULL THEN 1 ELSE 0 END) + "
    "(CASE WHEN api_endpoint_id IS NOT NULL THEN 1 ELSE 0 END) + "
    "(CASE WHEN component_id IS NOT NULL THEN 1 ELSE 0 END) = 1"
)


class JourneyStep(SQLModel, table=True):
    __tablename__ = "journey_step"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("journey_id", "step_order", name="uq_journey_step_journey_id_step_order"),
        CheckConstraint(_EXACTLY_ONE_TARGET, name="ck_journey_step_exactly_one_target"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=text("uuidv7()"),
        ),
    )
    journey_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("journey.id"), nullable=False, index=True
        ),
    )
    page_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("page.id"), nullable=True, index=True),
    )
    form_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("form.id"), nullable=True, index=True),
    )
    api_endpoint_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("api_endpoint.id"), nullable=True, index=True
        ),
    )
    component_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("component.id"), nullable=True, index=True
        ),
    )
    step_order: int
    stage_label: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
