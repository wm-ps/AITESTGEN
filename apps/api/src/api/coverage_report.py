"""Coverage Report & Run Diagnostics (Story 2.22 Tasks 2-3).

Task 1 (`record_diagnostic()`, `apps/workers/discovery`) already landed and is
the sink every producer writes through. This module is the read side: it
aggregates what's in `DiagnosticRecord`/`BlockedTask`/the typed capture
tables into AC 1's five coverage categories, plus a diagnostics dump grouped
by `kind` (AC 3) for producers that don't fit one of the five.

Lives in `apps/api`, not `apps/workers/discovery` — `apps/api` and
`apps/workers/discovery` are separate deployables (see
`discovery_worker/db.py`'s own docstring), and this module only ever needs
`domain` + a `Session`, never Playwright/boto3/the rest of the worker's
heavier dependencies. Duplicates `discovery_worker.blocked_frontier`'s small
grouping query rather than adding a cross-deployable dependency for it.

`DiscoveryError` (Story 2.18) is imported lazily inside `_errored_section` —
until that story lands, the import fails and the section reports
`available=False` rather than crashing the whole report (AC 4). No further
edit to this file is needed once 2.18 lands; the section lights up on its
own.
"""

import uuid
from typing import Any

from domain import BlockedTask, Component, ComponentLocator, DiscoveryRun, Form, Page
from sqlmodel import Session, select


def _reached_section(session: Session, discovery_run_id: uuid.UUID) -> dict[str, int]:
    pages = session.exec(
        select(Page).where(Page.discovery_run_id == discovery_run_id, Page.merged_into_id.is_(None))  # type: ignore[union-attr]
    ).all()
    forms = session.exec(
        select(Form).where(Form.discovery_run_id == discovery_run_id, Form.merged_into_id.is_(None))  # type: ignore[union-attr]
    ).all()
    from domain import Action

    actions = session.exec(select(Action).where(Action.discovery_run_id == discovery_run_id)).all()
    return {"pages": len(pages), "forms": len(forms), "actions": len(actions)}


def _blocked_section(session: Session, application_id: uuid.UUID) -> list[dict[str, Any]]:
    """Same grouping `discovery_worker.blocked_frontier.consolidated_view`
    performs — duplicated here (not imported) so `apps/api` never depends on
    `apps/workers/discovery`'s heavier package."""
    open_tasks = session.exec(
        select(BlockedTask).where(
            BlockedTask.application_id == application_id, BlockedTask.status != "resolved"
        )
    ).all()
    grouped: dict[str, dict[str, Any]] = {}
    for task in open_tasks:
        current = grouped.get(task.aggregation_key)
        if current is None:
            grouped[task.aggregation_key] = {
                "aggregation_key": task.aggregation_key,
                "required_description": task.required_description,
                "required_type": task.required_type,
                "status": task.status,
                "waiting_count": task.waiting_count,
            }
            continue
        if "blocked_both" in (current["status"], task.status) or current[
            "required_type"
        ] != task.required_type:
            current["status"] = "blocked_both"
        current["waiting_count"] += task.waiting_count
    return list(grouped.values())


def _diagnostic_payloads(session: Session, discovery_run_id: uuid.UUID, kind: str) -> list[dict]:
    from domain import DiagnosticRecord

    rows = session.exec(
        select(DiagnosticRecord).where(
            DiagnosticRecord.discovery_run_id == discovery_run_id, DiagnosticRecord.kind == kind
        )
    ).all()
    return [row.payload for row in rows]


def _skipped_for_safety_section(session: Session, discovery_run_id: uuid.UUID) -> list[dict]:
    destructive = [
        p
        for p in _diagnostic_payloads(session, discovery_run_id, "safety_verdict")
        if p.get("verdict") == "DESTRUCTIVE"
    ]
    deferred = [
        p
        for p in _diagnostic_payloads(session, discovery_run_id, "execution_decision")
        if p.get("action") == "DEFER" and p.get("deciding_specialist") == "safety"
    ]
    return destructive + deferred


def _unreached_section(session: Session, discovery_run_id: uuid.UUID) -> list[dict]:
    unreached = _diagnostic_payloads(session, discovery_run_id, "unreached")
    unreachable_containers = [
        p
        for p in _diagnostic_payloads(session, discovery_run_id, "widget_coverage")
        if p.get("type") in ("unreachable_container", "frame_depth_exceeded")
    ]
    return unreached + unreachable_containers


def _errored_section(session: Session, discovery_run_id: uuid.UUID) -> dict[str, Any]:
    try:
        from domain import DiscoveryError
    except ImportError:
        # Story 2.18 hasn't landed yet — AC 4: render what's available
        # rather than fail the whole report.
        return {"available": False, "items": []}
    rows = session.exec(
        select(DiscoveryError).where(DiscoveryError.discovery_run_id == discovery_run_id)
    ).all()
    return {
        "available": True,
        "items": [
            {
                "error_code": row.error_code,
                "message": row.message,
                "retry_count": row.retry_count,
                "page_id": str(row.page_id) if row.page_id else None,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


# Producer stories whose diagnostics are grouped verbatim under their own
# `kind` (Task 3/AC 3) — anything not one of the five AC 1 categories above.
_DIAGNOSTIC_KINDS = {
    "state_identity": "2.10 State Identity Engine",
    "safety_verdict": "2.12 Safety Engine",
    "execution_decision": "2.11/2.12/2.13/2.19 Planner decision chain",
    "widget_coverage": "2.14 Widget Coverage",
    "page_readiness": "2.9 Page Readiness",
    "state_return": "2.11 State Return ladder",
    "synthetic_data": "2.13 Data Resolver",
    "resume": "2.16 Blocked Path Record & Re-Crawl Resume",
}


def _diagnostics_sections(session: Session, discovery_run_id: uuid.UUID) -> dict[str, dict]:
    """AC 3/4: one section per producing story, degrading to `available=False`
    (no rows found, or the producer hasn't landed) rather than omitting the
    key outright — a caller always sees the same shape."""
    sections: dict[str, dict] = {}
    for kind, label in _DIAGNOSTIC_KINDS.items():
        payloads = _diagnostic_payloads(session, discovery_run_id, kind)
        sections[kind] = {"label": label, "available": bool(payloads), "records": payloads}
    return sections


def _fragile_locator_ratio(session: Session, application_id: uuid.UUID) -> float | None:
    """Story 2.21's most actionable number (Dev Notes) — surfaced at the top
    level rather than buried inside the `locator_durability` diagnostics
    section. `None` (not 0.0) when there's nothing captured yet, so a caller
    can distinguish "no locators" from "none of them are fragile"."""
    locators = session.exec(
        select(ComponentLocator)
        .join(Component, Component.id == ComponentLocator.component_id)  # type: ignore[arg-type]
        .where(Component.application_id == application_id)
    ).all()
    if not locators:
        return None
    fragile = sum(1 for loc in locators if loc.fragile)
    return fragile / len(locators)


def build_coverage_report(session: Session, discovery_run: DiscoveryRun) -> dict[str, Any]:
    """AC 1/2/3/5: the full report for one Discovery Run. `status` never
    travels without this — see `main.py`'s `_to_application_read`/report
    endpoint, which always embed this alongside `DiscoveryRun.status`."""
    return {
        "discovery_run_id": discovery_run.external_id,
        "status": discovery_run.status,
        "coverage": {
            "reached": _reached_section(session, discovery_run.id),
            "blocked": _blocked_section(session, discovery_run.application_id),
            "skipped_for_safety": _skipped_for_safety_section(session, discovery_run.id),
            "unreached": _unreached_section(session, discovery_run.id),
            "errored": _errored_section(session, discovery_run.id),
        },
        "diagnostics": _diagnostics_sections(session, discovery_run.id),
        "fragile_locator_ratio": _fragile_locator_ratio(session, discovery_run.application_id),
    }
