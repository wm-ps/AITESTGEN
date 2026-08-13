"""Application — a target system registered for discovery (Story 1.3).

**First entity whose id is ever exposed to the frontend** — establishes the
architecture's UUIDv7-internal / UUIDv4-external convention for every entity
after it (`DiscoveryRun`, `Journey`, `Scenario`, `TestAsset`, ...): `id` is
the internal PK (UUIDv7, index locality) and never leaves the backend;
`external_id` (UUIDv4, opaque) is the only id ever returned in an API
response, since a UUIDv7's embedded timestamp would leak creation time.

`secret_ref` stores only the opaque reference returned by `SecretsClient`
(AD-5) — never the raw credential. `auth_method` (Story 1.4) selects which
credential shape `secret_ref` currently points at; the two are mutually
exclusive, so one column suffices — switching `auth_method` repoints
`secret_ref` rather than keeping a second ref column around.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

AuthMethod = Literal["standard_login", "sso_session_reuse"]


class Application(SQLModel, table=True):
    __tablename__ = "application"  # pyright: ignore[reportAssignmentType]

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
    organization_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("organization.id"),
            nullable=False,
            index=True,
        ),
    )
    name: str
    url: str
    # Story: onboarding's Application URL is a home page, not necessarily the
    # login page (auth_method=standard_login's login form can live behind a
    # link, or on an endpoint that 500s without an existing session cookie —
    # observed live: shopbit.onwavemaker.com's /login). Optional override so
    # `establish_session` can navigate straight there instead of guessing;
    # deliberately never reachability-checked at onboarding time (main.py) —
    # the same cookie-dependent 500 that motivated this field would otherwise
    # block onboarding again.
    login_url: str | None = Field(default=None)
    environment: str
    secret_ref: str
    # str, not the AuthMethod Literal — SQLModel can't infer a column type from
    # Literal; the Literal is still the source of truth for callers (api layer).
    auth_method: str = Field(default="standard_login")
    # Story 2.9: per-Application default for the crawler's readiness ceiling
    # (`wait_for_page_ready`). Nullable — `None` means "use the DiscoveryRun's
    # override, or the hardcoded default", not "wait forever". Backend/config
    # only in V1, no API route or UI field.
    page_load_timeout_seconds: float | None = Field(default=None)
    # Story 2.10 AC 8: per-Application state-identity thresholds — never
    # hardcoded constants in the comparison code. Expect these to need
    # tuning on the first real pilot (Dev Notes).
    state_identity_threshold_same: float = Field(default=0.75)
    state_identity_threshold_new: float = Field(default=0.35)
    # Story 2.12 AC 2: `non_production` (default) executes Ambiguous
    # actions to maximise coverage; `production` defers them to the
    # Blocked Frontier. A declaration by the user about how cautious to be
    # — not a detection of where the crawler is actually running (Dev
    # Notes: never conflate the two). Backend/config only in V1, no UI field.
    safety_posture: str = Field(default="non_production")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    # Soft-delete only — no cascade to child rows (discovery_run, journey,
    # etc.) or the Vault secret. `_get_org_application` treats a non-null
    # value as "not found" everywhere, so every existing route already
    # respects it.
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
