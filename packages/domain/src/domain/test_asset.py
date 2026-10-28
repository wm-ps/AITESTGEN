"""TestAsset — one compiled Playwright test, generated from one Scenario (Story 4.2).

`scenario_id`: one `TestAsset` compiles from one `Scenario`. `test_suite_id`:
every `TestAsset` belongs to exactly one `TestSuite` (its Scenario's
Journey's suite for this attempt).

Deliberately has **no `generation_run_id` field of its own** — it's always
derivable via `test_suite_id` -> `TestSuite.generation_run_id`, and always
correct: unlike `Scenario` (whose parent `Journey.attempt` is a *mutable*
counter that keeps incrementing across regenerations, so `Scenario` must
freeze its own copy at creation time), `TestSuite` is itself already a
frozen, one-row-per-attempt entity — deriving through it can never go stale.
Storing a second, redundant copy here would only add a second source of
truth that could drift out of sync with its own `test_suite_id`, for no
benefit (the same "derive over duplicate" principle this codebase already
applies to `Scenario.test_data_complete()`).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, Session, SQLModel, select


class TestAsset(SQLModel, table=True):
    __test__ = False  # pytest: not a test class, despite the name prefix
    __tablename__ = "test_asset"  # pyright: ignore[reportAssignmentType]

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
    scenario_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("scenario.id"), nullable=False, index=True
        ),
    )
    test_suite_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("test_suite.id"), nullable=False, index=True
        ),
    )
    code: str
    current: bool = Field(default=True)
    # Generation-pipeline hardening: does this TestAsset's target page need an
    # authenticated session? Drives the exported project's auth/public
    # Playwright project split (deterministically re-tagged onto the generated
    # code by `spec_linter.apply_auth_tag`, never trusted from the LLM alone).
    requires_auth: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    # "ready" or "needs_review" — set by the post-generation linter
    # (`spec_linter.py`): locator provenance, required-field coverage, shared
    # auth-helper usage, sibling-spec consistency. Flag-only, never blocks.
    status: str = Field(default="ready")
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    # This Scenario's primary Page (first Page its Journey's steps visit) —
    # stored, not re-derived per read, so sibling-consistency linting can
    # group TestAssets by target page with a plain equality filter.
    primary_page_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("page.id"), nullable=True, index=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


def supersede_test_asset(
    session: Session,
    prior: TestAsset,
    *,
    code: str,
    requires_auth: bool,
    warnings: list[str],
    status: str,
    primary_page_id: uuid.UUID | None,
) -> TestAsset:
    """Flips `prior.current` off and inserts a new `current=True` TestAsset
    for the same scenario/suite — the in-place "replace the current asset"
    operation the generation worker's `_persist_test_asset_sync` never
    needed (it only ever inserts a brand-new current row; whole-suite
    supersede is handled
    separately by `ensure_test_suite_activity`, on a *new* TestSuite, not by
    flipping an existing row). HealTestActivity (execution worker) was the
    first caller that needs this, every time a healed candidate passes
    typecheck — not only when it also passes execution — so the "latest
    code" for the next heal attempt is simply whatever TestAsset is
    currently `current` for this scenario, with no separate state to thread
    through the heal loop.

    `RegenerateTestAssetActivity` (Edit Test Data) is a second caller
    alongside HealTestActivity, and the two can now genuinely race — a heal
    triggered by an in-flight run, at the same moment as a manual
    data-driven regenerate for the same scenario. `prior` is re-fetched
    under a row lock (`with_for_update`) and re-checked immediately before
    being flipped, so the loser of a real race aborts cleanly (raises)
    instead of both callers each inserting their own `current=True` row for
    the same scenario."""
    locked_prior = session.exec(
        select(TestAsset).where(TestAsset.id == prior.id).with_for_update()
    ).one()
    if not locked_prior.current:
        raise RuntimeError(
            f"TestAsset {locked_prior.id} was already superseded by another caller"
        )
    locked_prior.current = False
    session.add(locked_prior)
    new_asset = TestAsset(
        scenario_id=locked_prior.scenario_id,
        test_suite_id=locked_prior.test_suite_id,
        code=code,
        current=True,
        requires_auth=requires_auth,
        warnings=warnings,
        status=status,
        primary_page_id=primary_page_id,
    )
    session.add(new_asset)
    session.flush()
    return new_asset
