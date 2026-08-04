"""`record_diagnostic()` — the single sink every Discovery Engine v2 heuristic
writes observability through (Story 2.22 Task 1).

Seven producer stories (2.10 state identity, 2.11 planner/loop-return, 2.12
safety, 2.13 data resolution, 2.14 widget coverage, 2.19 loop guards, 2.21
locator durability) plus 2.18's `DiscoveryError` all call this one function
instead of inventing their own logging shape — defining the contract before
any producer exists means there's nothing to reconcile later (see
docs/DISCOVERY_ENGINE_V2.md#7 Story map). `kind` distinguishes producers;
`payload` is loose JSONB so a producer adds a field without a migration.
"""

import logging
import uuid

from domain import DiagnosticRecord
from sqlmodel import Session

logger = logging.getLogger(__name__)


def record_diagnostic(
    session: Session, discovery_run_id: uuid.UUID, kind: str, payload: dict
) -> None:
    """Persist one diagnostic row scoped to a DiscoveryRun. Never raises — a
    failed diagnostic write must not take down the crawl it's observing
    (same rationale as `activities.py`'s `_persist`)."""
    try:
        session.add(
            DiagnosticRecord(discovery_run_id=discovery_run_id, kind=kind, payload=payload)
        )
        session.commit()
    except Exception:
        logger.exception("record_diagnostic: failed to persist kind=%s — continuing", kind)
        session.rollback()
