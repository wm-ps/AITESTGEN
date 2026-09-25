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

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
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
    # Story 2.10: distinct from `merged_into_id` — this row is a live sibling
    # of the referenced row (same route template, materially different
    # behaviour), NOT a duplicate superseded by it. Both rows stay canonical
    # (`merged_into_id IS NULL`) and both remain independently attributable
    # to a Journey. Conflating the two silently deletes real behaviour.
    variant_of_page_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("page.id"), nullable=True, index=True),
    )
    url: str
    title: str = ""
    object_storage_key: str | None = Field(default=None)
    # Story 2.10: the heading + structural-shape signals `state_identity.py`
    # scores against — persisted so a *prior* Discovery Run's canonical
    # pages can be re-fingerprinted when seeding a new run's in-process
    # cache (Task 5), not just pages captured this run.
    heading: str | None = Field(default=None)
    structural_tokens: list | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    # `[ADDED journey-screenshot]` Story 2.9's own `wait_for_page_ready`
    # readiness gate (`ReadinessResult.settled`), captured at screenshot
    # time — reused as-is rather than a second "is this blank" analysis: a
    # page that never settled (network still busy / DOM still mutating /
    # content not yet present) is very likely to have been screenshotted
    # blank or mid-load. Defaults `True` (existing rows, and the
    # dialog/popup/login capture paths that don't pass a readiness result,
    # are assumed settled — never worse than today's behaviour) so this only
    # ever narrows which page's screenshot a Journey shows, never widens it.
    page_settled: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    # `[ADDED screenshot-content-score]` The deterministic Screenshot
    # Content Score (`discovery_worker.screenshot_quality.score_screenshot`,
    # 0.0-1.0) — computed once at capture time from the screenshot bytes and
    # this same row's own `structural_tokens`/`heading`/`page_settled`, no
    # LLM/vision model involved. Lets a Journey's screenshot selection
    # (apps/api/src/api/main.py) pick whichever of its steps' Pages is most
    # likely to show real, rendered application content instead of a blank
    # or mid-load capture. Null for existing rows captured before this
    # field existed, and for the dialog/popup/login capture paths that
    # don't compute it — both read the same as "no opinion", never worse
    # than the page_settled-only selection this augments.
    content_score: float | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
