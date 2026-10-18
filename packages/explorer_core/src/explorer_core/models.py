"""Vantage Explorer's own tables — every one prefixed `explorer_` so the
module stays separable from the classic discovery tables (Page, Journey,
...), which it never reads or writes. Only `application` is referenced, as
the tenant/target anchor.

Same id convention as the rest of the platform: `id` is the internal UUIDv7
PK, `external_id` (UUIDv4) is the only id that leaves the backend.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Identity, Integer, LargeBinary
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

# Run lifecycle, in order. `awaiting_confirmation` is the human checkpoint
# after the App Summary is written; the workflow waits on a signal there.
RUN_STATUSES = (
    "queued",
    "signing_in",
    "understanding",
    "summarizing",
    "awaiting_confirmation",
    "confirmed",
    "planning",  # Stage 2: turning the confirmed summary into missions
    "exploring",  # Stage 2: missions running
    "explored",
    "hunting",  # Stage 3: hunting hidden screens
    "testing",  # Stage 5: writing and proving test cases
    "tested",
    "failed",
    "stopped",
    "paused",  # stopped on purpose, to be resumed from where it left off
)
ACTIVE_RUN_STATUSES = (
    "queued",
    "signing_in",
    "understanding",
    "summarizing",
    "awaiting_confirmation",
    "planning",
    "exploring",
    "hunting",
    "testing",
)
MISSION_STATUSES = ("queued", "running", "waiting", "done", "blocked", "failed", "skipped")


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid_pk() -> Any:
    return Field(
        default_factory=uuid.uuid7, sa_column=Column(PGUUID(as_uuid=True), primary_key=True)
    )


def _run_fk() -> Any:
    return Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("explorer_run.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )


def _ts() -> Any:
    return Field(default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class ExplorerRun(SQLModel, table=True):
    __tablename__ = "explorer_run"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = _uuid_pk()
    external_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), unique=True, nullable=False, index=True),
    )
    application_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("application.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    status: str = Field(default="queued")
    # One plain-language line for the live header ("Reading the Quotes screen").
    headline: str = Field(default="Getting ready")
    health_score: int | None = Field(default=None)
    # True when the health check found the app too unstable to trust what it
    # shows — later stages lean on documents/answers instead (PLAN.md §4.4).
    requirements_first: bool = Field(default=False)
    # The App Summary (PLAN.md Step 1) — editable by the user until confirmed.
    brief: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    brief_confirmed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # Optional extra knowledge the user typed in on the Start card.
    notes: str | None = Field(default=None)
    # Who started it — emailed whenever the run needs them (explorer_core.notify).
    started_by_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("platform_user.id", ondelete="SET NULL"), nullable=True
        ),
    )
    # Stage 6 findings: code coverage, parts of the code never triggered,
    # unlinked pages, role differences — {"coverage": {...}, ...}.
    insights: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default="{}")
    )
    # Choices noticed during walk-throughs that probably change the path —
    # the seeds for Stage 2's branch missions.
    branch_points: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False, server_default="[]")
    )
    error: str | None = Field(default=None)
    created_at: datetime = _ts()
    updated_at: datetime = _ts()


class ExplorerEvent(SQLModel, table=True):
    """The live feed: one row per thing Explorer did or thought. Polled by
    the Live screen with an `after=<id>` cursor, hence the integer PK."""

    __tablename__ = "explorer_event"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(default=None, sa_column=Column(BigInteger, Identity(), primary_key=True))
    run_id: uuid.UUID = _run_fk()
    # thought | action | screen | health | phase | summary | error
    kind: str
    title: str
    detail: str | None = Field(default=None)
    shot_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True)
    )
    mission_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True, index=True)
    )
    created_at: datetime = _ts()


class ExplorerShot(SQLModel, table=True):
    """Screenshot bytes. ponytail: kept in Postgres (JPEG, viewport-only,
    ~60-150 KB each, a few dozen per run) so Explorer needs no object-store
    setup; move to the object store if runs grow to thousands of shots."""

    __tablename__ = "explorer_shot"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = _uuid_pk()
    run_id: uuid.UUID = _run_fk()
    data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    created_at: datetime = _ts()


class ExplorerScreen(SQLModel, table=True):
    """A screen as Explorer *understands* it (entity × view × mode), not a
    URL — many URLs collapse into one row via `signature`."""

    __tablename__ = "explorer_screen"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = _uuid_pk()
    run_id: uuid.UUID = _run_fk()
    signature: str = Field(index=True)
    name: str
    entity: str | None = Field(default=None)
    view_kind: str = Field(default="other")
    mode: str | None = Field(default=None)
    purpose: str | None = Field(default=None)
    url: str
    url_pattern: str
    visits: int = Field(default=1, sa_column=Column(Integer, nullable=False))
    # [{label, type, required, notes}]
    fields: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False)
    )
    # [{label, kind, risky}]
    actions: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False)
    )
    # Plain-language guesses about parts that only appear sometimes.
    hidden_hints: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    reached_by: str | None = Field(default=None)
    shot_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True)
    )
    # Set when the screen only appeared because of a particular choice or
    # situation (a branch mission) — a "hidden screen" (PLAN.md §5).
    condition: str | None = Field(default=None)
    created_at: datetime = _ts()


class ExplorerHealthIssue(SQLModel, table=True):
    __tablename__ = "explorer_health_issue"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = _uuid_pk()
    run_id: uuid.UUID = _run_fk()
    # crash | broken_link | server_error | background_error | slow | wording
    kind: str
    severity: str  # high | medium | low
    title: str
    detail: str | None = Field(default=None)
    url: str
    occurrences: int = Field(default=1, sa_column=Column(Integer, nullable=False))
    shot_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True)
    )
    created_at: datetime = _ts()


class ExplorerMission(SQLModel, table=True):
    """A goal on the Mission Board (PLAN.md Step 3)."""

    __tablename__ = "explorer_mission"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = _uuid_pk()
    external_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), unique=True, nullable=False, index=True),
    )
    run_id: uuid.UUID = _run_fk()
    title: str
    goal: str
    kind: str = Field(default="task")  # task | branch | area | rule | custom
    why: str | None = Field(default=None)
    priority: int = Field(default=3, sa_column=Column(Integer, nullable=False))
    # Concrete path guidance, e.g. "On 'Was anyone hurt?' choose 'Someone needs urgent help'".
    instructions: str | None = Field(default=None)
    # For branch missions: the situation being tested; new screens found
    # get this as their "appears when" condition.
    condition: str | None = Field(default=None)
    # What SHOULD happen, from trusted sources — never from the app (§4.2).
    expected: str | None = Field(default=None)
    start_screen: str | None = Field(default=None)
    status: str = Field(default="queued")
    outcome: str | None = Field(default=None)
    matches_expected: bool | None = Field(default=None)
    steps: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    new_screens: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    added_by: str = Field(default="explorer")  # explorer | user
    started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = _ts()


class ExplorerTransition(SQLModel, table=True):
    """An edge of the App Map: doing `action` on one screen led to another."""

    __tablename__ = "explorer_transition"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = _uuid_pk()
    run_id: uuid.UUID = _run_fk()
    from_screen_id: uuid.UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    to_screen_id: uuid.UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    action: str
    mission_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True)
    )
    created_at: datetime = _ts()


class ExplorerRecording(SQLModel, table=True):
    """One mission's screen recording (webm). Captions come from the
    mission's events, offset from `started_at`. ponytail: bytes in Postgres
    like screenshots (~1-6 MB per mission); move to the object store if
    runs grow large."""

    __tablename__ = "explorer_recording"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = _uuid_pk()
    run_id: uuid.UUID = _run_fk()
    # A mission's recording, or a test case's proof video.
    mission_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True, index=True)
    )
    # mission | proof | reel (the shareable highlight video, Stage 7)
    kind: str = Field(default="mission")
    test_case_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True, index=True)
    )
    data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    started_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    duration_seconds: float = Field(default=0)
    created_at: datetime = _ts()


TEST_KINDS = ("navigation", "validation", "error_state", "data_load", "form_submission")


class ExplorerTestCase(SQLModel, table=True):
    """A test case in one of the 5 kinds (PLAN.md §6), with its executable
    script and how it was proven (Stage 5)."""

    __tablename__ = "explorer_test_case"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = _uuid_pk()
    external_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), unique=True, nullable=False, index=True),
    )
    run_id: uuid.UUID = _run_fk()
    kind: str  # one of TEST_KINDS
    title: str
    purpose: str
    technique: str | None = Field(default=None)
    business_thing: str | None = Field(default=None)
    start_screen: str | None = Field(default=None)
    # Plain steps as written for people.
    steps: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    # What should happen, and where that belief comes from: confirmed (you or
    # your documents) | standard (common sense) | seen (only the app).
    expected: str
    trust: str = Field(default="standard")
    # What the app actually did when Explorer ran the test.
    observed: str | None = Field(default=None)
    # Exact replayable actions: [{"do": "goto"|"fill"|"choose"|"click", ...}]
    script: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False)
    )
    # {"kind": "text_visible" | "url_contains", "value": "..."}
    check: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    # planned | building | proven | known_bug | dropped
    status: str = Field(default="planned")
    drop_reason: str | None = Field(default=None)
    proof_runs: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    proof_passes: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    # The test failed when its decisive step was removed (it can catch a bug).
    catches_breakage: bool | None = Field(default=None)
    evidence_shot_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True)
    )
    code: str | None = Field(default=None)
    created_at: datetime = _ts()
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class ExplorerQuestion(SQLModel, table=True):
    """Something Explorer needs a person for (PLAN.md Step 6 / Stage 4).
    Only the mission that asked waits; everything else keeps going."""

    __tablename__ = "explorer_question"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = _uuid_pk()
    external_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), unique=True, nullable=False, index=True),
    )
    run_id: uuid.UUID = _run_fk()
    mission_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True)
    )
    # data | risk | rule | clarify
    kind: str
    question: str
    why: str | None = Field(default=None)
    options: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    shot_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True)
    )
    # Health issue this question is about (rule questions on possible bugs).
    issue_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True)
    )
    status: str = Field(default="open")  # open | answered | dismissed
    answer: str | None = Field(default=None)
    answered_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = _ts()


class ExplorerKnowledge(SQLModel, table=True):
    """What Explorer knows about an application, across all runs: your
    answers, uploaded documents and facts you add. Trust level 'confirmed'
    (PLAN.md §4.1). ponytail: plain text recall (keyword match, newest
    first) — move to vector search if an app's knowledge grows past a few
    hundred items."""

    __tablename__ = "explorer_knowledge"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = _uuid_pk()
    external_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), unique=True, nullable=False, index=True),
    )
    application_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("application.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    kind: str  # answer | doc | fact
    text: str
    source: str | None = Field(default=None)
    created_at: datetime = _ts()


class ExplorerRole(SQLModel, table=True):
    """Another kind of user to explore as (Stage 6, "who can see what").
    The login lives in the secrets store; only its reference is kept here."""

    __tablename__ = "explorer_role"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = _uuid_pk()
    external_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), unique=True, nullable=False, index=True),
    )
    application_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("application.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    name: str
    secret_ref: str
    created_at: datetime = _ts()


class ExplorerAccess(SQLModel, table=True):
    """Could this kind of user open this screen? (Stage 6)"""

    __tablename__ = "explorer_access"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = _uuid_pk()
    run_id: uuid.UUID = _run_fk()
    role: str
    screen_id: uuid.UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    allowed: bool
    note: str | None = Field(default=None)
    created_at: datetime = _ts()
