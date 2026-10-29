"""Admin Activity page — one cross-application timeline of what happened.

Two kinds of source, merged newest-first:

- `ActivityEvent` rows, written by `record_activity` from the API routes that
  change something (settings, execution policy, credentials, team, schedules,
  scenario edits) or start scenario/test case generation.
- `DiscoveryRun` and `TestRun` rows read as-is — they already hold status,
  counts and failure reasons, so a run shows as one row whose result updates
  in place rather than a "started" row plus a "finished" row.

Generation has no row of its own to read, so its start event stores the
Journeys it covered and the outcome is worked out from those Journeys'
current Scenarios/TestSuites each time the feed is read.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from domain import (
    ActivityEvent,
    Application,
    DiscoveryError,
    DiscoveryRun,
    Journey,
    Page,
    PlatformUser,
    Scenario,
    TestRun,
    TestSuite,
)
from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlmodel import Session, select

from api.auth import CurrentAdminDep, SessionDep

router = APIRouter()

GENERATION_CATEGORIES = ("scenarios", "test_cases")
INTERNAL_VERIFICATION_TRIGGER_NAME = "Add Test Case"

_FIELD_LABELS = {
    "max_pages": "max pages",
    "max_discovery_duration_minutes": "max exploration duration (minutes)",
    "navigation_timeout_seconds": "page load timeout (seconds)",
    "interaction_level": "interaction level",
    "max_journeys": "max journeys",
    "max_scenarios_per_journey": "max scenarios per journey",
    "max_test_cases_per_application": "max test cases per application",
    "delete_project_after": "delete deleted projects after",
    "max_heal_attempts": "max heal attempts",
    "screenshot_capture": "screenshot capture",
    "execution_enabled": "test execution",
    "allowed_base_urls": "allowed base URLs",
    "destructive_actions_permitted": "destructive actions",
    "video_capture_enabled": "video capture",
}


def _fmt(value: Any) -> str:
    if value is None:
        return "unlimited"
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "none"
    return str(value).replace("_", " ")


def field_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, str]]:
    """Only the fields whose value actually changed, already formatted for
    display. Never pass secrets in — values are shown verbatim."""
    return [
        {
            "field": _FIELD_LABELS.get(key, key.replace("_", " ")),
            "before": _fmt(before.get(key)),
            "after": _fmt(value),
        }
        for key, value in after.items()
        if before.get(key) != value
    ]


def changes_summary(subject: str, changes: list[dict[str, str]]) -> str:
    if len(changes) == 1:
        c = changes[0]
        return f"Changed {subject}{c['field']} from {c['before']} to {c['after']}"
    return f"Changed {subject or 'settings: '}{', '.join(c['field'] for c in changes)}"


def record_activity(
    session: Session,
    actor: PlatformUser,
    category: str,
    summary: str,
    *,
    application: Application | None = None,
    outcome: str = "changed",
    details: dict[str, Any] | None = None,
) -> None:
    """Adds the row to the caller's session — it commits with the change it
    describes, so a rolled-back change never leaves a phantom row."""
    session.add(
        ActivityEvent(
            organization_id=actor.organization_id,
            application_id=application.id if application else None,
            application_name=application.name if application else None,
            actor_name=actor.name,
            category=category,
            outcome=outcome,
            summary=summary,
            details=details or {},
        )
    )


class ActivityItemRead(BaseModel):
    id: str
    kind: str  # "event" | "discovery" | "test_run"
    created_at: datetime
    category: str
    outcome: str
    summary: str
    # Short plain-language reason, for a failed/stopped row.
    reason: str | None = None
    actor: str
    application_id: uuid.UUID | None = None
    application_name: str | None = None
    application_deleted: bool = False
    # Which application tab "Open" lands on; `test_run_id` opens that run.
    target_tab: str | None = None
    test_run_id: uuid.UUID | None = None
    details: dict[str, Any] = {}


class ActivityPageRead(BaseModel):
    items: list[ActivityItemRead]
    # Pass back as `cursor` for the next page; null when there is none.
    next_cursor: datetime | None
    # Counts per filter option over the whole time range (other filters
    # ignored), for the filter menus: {"category": {...}, "outcome": {...},
    # "application": {external_id: n}, "total": {"all": n}}.
    facets: dict[str, dict[str, int]]


_STOP_REASONS = {
    "exhausted": "explored every reachable page",
    "max_pages": "stopped at the max pages limit",
    "max_duration": "stopped at the time limit",
}
_DISCOVERY_OUTCOMES = {"running": "running", "paused": "stopped", "complete": "done", "failed": "failed"}


def _app_fields(application: Application) -> dict[str, Any]:
    return {
        "application_id": application.external_id,
        "application_name": application.name,
        "application_deleted": application.deleted_at is not None,
    }


def _discovery_items(session: Session, rows: list[tuple[DiscoveryRun, Application]]) -> list[ActivityItemRead]:
    run_ids = [run.id for run, _ in rows]
    page_counts = dict(
        session.exec(
            select(Page.discovery_run_id, func.count())
            .where(Page.discovery_run_id.in_(run_ids))  # type: ignore[attr-defined]
            .group_by(Page.discovery_run_id)  # type: ignore[arg-type]
        ).all()
    ) if run_ids else {}
    journey_counts = dict(
        session.exec(
            select(Journey.discovery_run_id, func.count())
            .where(Journey.discovery_run_id.in_(run_ids))  # type: ignore[attr-defined]
            .group_by(Journey.discovery_run_id)  # type: ignore[arg-type]
        ).all()
    ) if run_ids else {}
    failed_ids = [run.id for run, _ in rows if run.status == "failed"]
    errors: dict[uuid.UUID, list[dict[str, str]]] = {}
    if failed_ids:
        for error in session.exec(
            select(DiscoveryError)
            .where(DiscoveryError.discovery_run_id.in_(failed_ids))  # type: ignore[attr-defined]
            .order_by(DiscoveryError.created_at.desc())  # type: ignore[attr-defined]
        ).all():
            bucket = errors.setdefault(error.discovery_run_id, [])
            if len(bucket) < 10:
                bucket.append({"code": error.error_code, "message": error.message})

    items = []
    for run, application in rows:
        outcome = _DISCOVERY_OUTCOMES.get(run.status, "running")
        live = run.source == "live_exploration"
        what = "AI test case authoring" if live else "Exploration"
        pages = page_counts.get(run.id, 0)
        journeys = journey_counts.get(run.id, 0)
        if outcome == "done":
            counts = "" if live else f" — {pages} pages, {journeys} journeys"
            summary = f"{what} finished on {application.name}{counts}"
        elif outcome == "failed":
            summary = f"{what} failed on {application.name}"
        elif outcome == "stopped":
            summary = f"{what} paused on {application.name}"
        else:
            stage = f" ({run.stage})" if run.stage else ""
            summary = f"{what} running on {application.name}{stage}"
        items.append(
            ActivityItemRead(
                id=f"discovery:{run.external_id}",
                kind="discovery",
                created_at=run.created_at,
                category="test_cases" if live else "discovery",
                outcome=outcome,
                summary=summary,
                reason=run.failure_reason if outcome == "failed" else None,
                actor="System",
                target_tab="suite" if live else "journeys",
                details={
                    "pages": pages,
                    "journeys_found": journeys,
                    "stage": run.stage,
                    "stop_reason": _STOP_REASONS.get(run.stop_reason or ""),
                    "failure_reason": run.failure_reason,
                    "errors": errors.get(run.id, []),
                },
                **_app_fields(application),
            )
        )
    return items


def _test_run_items(rows: list[tuple[TestRun, Application]]) -> list[ActivityItemRead]:
    items = []
    for run, application in rows:
        bad = run.failed_count + run.timed_out_count + run.errored_count
        label = f"Test run #{run.run_number} on {application.name}"
        reason = None
        if run.status in ("pending", "running"):
            outcome = "running"
            summary = f"{label} running ({run.total_count} tests)" if run.total_count else f"{label} starting"
        elif run.status == "cancelled":
            outcome, summary = "stopped", f"{label} cancelled"
        elif run.status == "blocked":
            outcome, summary = "failed", f"{label} could not run"
            reason = run.blocked_reason
        else:
            outcome = "failed" if bad else "done"
            summary = f"{label} — {run.passed_count} passed, {bad} failed"
            if bad:
                reason = f"{bad} of {run.total_count} tests failed"
        if run.schedule_id is not None and run.triggered_by_name:
            actor = f"Schedule: {run.triggered_by_name}"
        else:
            actor = run.triggered_by_name or "Someone"
        items.append(
            ActivityItemRead(
                id=f"test_run:{run.external_id}",
                kind="test_run",
                created_at=run.created_at,
                category="test_runs",
                outcome=outcome,
                summary=summary,
                reason=reason,
                actor=actor,
                target_tab="runs",
                test_run_id=run.external_id,
                details={
                    "total": run.total_count,
                    "passed": run.passed_count,
                    "failed": run.failed_count,
                    "timed_out": run.timed_out_count,
                    "errored": run.errored_count,
                    "skipped": run.blocked_count,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                },
                **_app_fields(application),
            )
        )
    return items


def _generation_outcomes(
    session: Session, events: list[ActivityEvent]
) -> dict[uuid.UUID, tuple[str, list[dict[str, Any]]]]:
    """Per generation start event: (outcome, per-Journey status). A Journey
    is failed when its generation_error is set (scenarios) or its TestSuite
    ended incomplete/terminated (test cases); running until it has a result.

    ponytail: reads each Journey's *current* attempt state, so re-running
    generation for a Journey also changes what an older start event shows. A
    per-attempt history would need GenerationWorkflow to record its own end."""
    refs = [
        (event, uuid.UUID(j["id"]), j["attempt"])
        for event in events
        for j in event.details.get("journeys", [])
    ]
    journey_ids = list({jid for _, jid, _ in refs})
    if not journey_ids:
        return {event.id: ("done", []) for event in events}
    journeys = {
        j.id: j
        for j in session.exec(select(Journey).where(Journey.id.in_(journey_ids))).all()  # type: ignore[attr-defined]
    }
    scenario_pairs = set(
        session.exec(
            select(Scenario.journey_id, Scenario.generation_run_id)
            .where(Scenario.journey_id.in_(journey_ids))  # type: ignore[attr-defined]
            .distinct()
        ).all()
    )
    suites = {
        (s.journey_id, s.generation_run_id): s.status
        for s in session.exec(select(TestSuite).where(TestSuite.journey_id.in_(journey_ids))).all()  # type: ignore[attr-defined]
    }

    result: dict[uuid.UUID, tuple[str, list[dict[str, Any]]]] = {}
    for event in events:
        rows = []
        for j in event.details.get("journeys", []):
            journey = journeys.get(uuid.UUID(j["id"]))
            key = (uuid.UUID(j["id"]), j["attempt"])
            error = None
            if event.category == "scenarios":
                if journey is not None and journey.generation_error:
                    status, error = "failed", journey.generation_error
                elif key in scenario_pairs or journey is None:
                    status = "done"
                else:
                    status = "running"
            else:
                suite_status = suites.get(key)
                status = {
                    "complete": "done",
                    "incomplete": "failed",
                    "terminated": "stopped",
                }.get(suite_status or "", "running" if journey is not None else "done")
                if status == "failed":
                    error = "Some test cases could not be generated"
            rows.append({"name": journey.name if journey else j.get("name", ""), "status": status, "error": error})
        statuses = {r["status"] for r in rows}
        outcome = next((s for s in ("running", "failed", "stopped") if s in statuses), "done")
        result[event.id] = (outcome, rows)
    return result


def _event_items(
    session: Session, rows: list[tuple[ActivityEvent, Application | None]]
) -> list[ActivityItemRead]:
    generation = _generation_outcomes(
        session, [e for e, _ in rows if e.category in GENERATION_CATEGORIES and "journeys" in e.details]
    )
    items = []
    for event, application in rows:
        outcome, details, reason, summary = event.outcome, dict(event.details), None, event.summary
        if event.id in generation:
            outcome, journeys = generation[event.id]
            details["journeys"] = journeys
            failed = [j for j in journeys if j["status"] == "failed"]
            if failed:
                reason = f"{len(failed)} of {len(journeys)} journeys failed"
            # The stored summary was written at start; say where it is now.
            what = "Scenario generation" if event.category == "scenarios" else "Test case generation"
            state = {"running": "running", "done": "finished", "failed": "failed", "stopped": "stopped"}[outcome]
            noun = "journey" if len(journeys) == 1 else "journeys"
            summary = f"{what} {state} on {event.application_name} for {len(journeys)} {noun}"
        target_tab = {"discovery": "journeys", "scenarios": "scenarios", "test_cases": "suite", "test_runs": "schedules"}.get(
            event.category
        )
        items.append(
            ActivityItemRead(
                id=f"event:{event.external_id}",
                kind="event",
                created_at=event.created_at,
                category=event.category,
                outcome=outcome,
                summary=summary,
                reason=reason,
                actor=event.actor_name,
                application_id=application.external_id if application else None,
                application_name=event.application_name,
                # Purged (application_id SET NULL) or soft-deleted.
                application_deleted=event.application_name is not None
                and (application is None or application.deleted_at is not None),
                target_tab=target_tab if application else None,
                details=details,
            )
        )
    return items


def _matches(item: ActivityItemRead, outcome: str | None, q: str | None) -> bool:
    if outcome and item.outcome != outcome:
        return False
    if q:
        haystack = f"{item.summary} {item.actor} {item.application_name or ''} {item.reason or ''}".lower()
        return q.lower() in haystack
    return True


def _collect(
    session: Session,
    organization_id: uuid.UUID,
    *,
    since: datetime,
    cursor: datetime | None,
    limit: int,
    oldest_first: bool = False,
    application_id: uuid.UUID | None = None,
    category: str | None = None,
    outcome: str | None = None,
    q: str | None = None,
) -> tuple[list[ActivityItemRead], datetime | None]:
    """Newest-first merge of the three sources, `limit` rows each.

    Paging stays correct even though `outcome`/`q` filter after fetching:
    a source that returned a full `limit` rows may have more older rows we
    haven't seen, so nothing older than its oldest fetched row is shown on
    this page — the next page starts from there.

    ponytail: `q` is matched in Python on the fetched rows, so a search can
    return short (even empty) pages while Next still has more. Move it into
    each source's SQL if searching long histories gets slow or confusing."""
    app_filter = []
    if application_id is not None:
        app_filter = [Application.external_id == application_id]

    def order(column: Any) -> Any:
        return column.asc() if oldest_first else column.desc()

    def window(column: Any) -> list[Any]:
        clauses = [column >= since]
        if cursor is not None:
            clauses.append(column > cursor if oldest_first else column < cursor)
        return clauses

    sources: list[tuple[list[Any], list[ActivityItemRead]]] = []

    if category in (None, "discovery", "test_cases"):
        stmt = (
            select(DiscoveryRun, Application)
            .join(Application, DiscoveryRun.application_id == Application.id)  # type: ignore[arg-type]
            .where(Application.organization_id == organization_id, *app_filter, *window(DiscoveryRun.created_at))
        )
        if category is not None:
            stmt = stmt.where(DiscoveryRun.source == ("crawler" if category == "discovery" else "live_exploration"))
        if outcome in ("running", "stopped", "done", "failed"):
            stmt = stmt.where(DiscoveryRun.status.in_([s for s, o in _DISCOVERY_OUTCOMES.items() if o == outcome]))  # type: ignore[attr-defined]
        elif outcome is not None:
            stmt = None
        if stmt is not None:
            rows = list(session.exec(stmt.order_by(order(DiscoveryRun.created_at)).limit(limit)).all())  # type: ignore[attr-defined]
            sources.append((rows, _discovery_items(session, rows)))

    if category in (None, "test_runs"):
        stmt = (
            select(TestRun, Application)
            .join(Application, TestRun.application_id == Application.id)  # type: ignore[arg-type]
            .where(
                Application.organization_id == organization_id,
                *app_filter,
                *window(TestRun.created_at),
                # Live exploration's own throwaway verification runs (same
                # exclusion as main._INTERNAL_VERIFICATION_TRIGGER_NAME).
                TestRun.triggered_by_name.is_distinct_from(INTERNAL_VERIFICATION_TRIGGER_NAME),  # type: ignore[union-attr]
            )
        )
        bad = TestRun.failed_count + TestRun.timed_out_count + TestRun.errored_count
        if outcome == "failed":
            stmt = stmt.where(or_(TestRun.status == "blocked", (TestRun.status == "completed") & (bad > 0)))
        elif outcome == "done":
            stmt = stmt.where(TestRun.status == "completed", bad == 0)
        elif outcome == "running":
            stmt = stmt.where(TestRun.status.in_(["pending", "running"]))  # type: ignore[attr-defined]
        elif outcome == "stopped":
            stmt = stmt.where(TestRun.status == "cancelled")
        elif outcome is not None:
            stmt = None
        if stmt is not None:
            rows = list(session.exec(stmt.order_by(order(TestRun.created_at)).limit(limit)).all())  # type: ignore[attr-defined]
            sources.append((rows, _test_run_items(rows)))

    stmt = (
        select(ActivityEvent, Application)
        .join(Application, ActivityEvent.application_id == Application.id, isouter=True)  # type: ignore[arg-type]
        .where(ActivityEvent.organization_id == organization_id, *window(ActivityEvent.created_at))
    )
    if application_id is not None:
        stmt = stmt.where(*app_filter)
    if category is not None:
        stmt = stmt.where(ActivityEvent.category == category)
    if outcome is not None:
        # Generation rows' outcome is derived at read time — filtered below.
        stmt = stmt.where(
            or_(ActivityEvent.outcome == outcome, ActivityEvent.category.in_(GENERATION_CATEGORIES))  # type: ignore[attr-defined]
        )
    rows = list(session.exec(stmt.order_by(order(ActivityEvent.created_at)).limit(limit)).all())  # type: ignore[attr-defined]
    sources.append((rows, _event_items(session, rows)))

    # The furthest point every full source has been read up to.
    edges = [items[-1].created_at for raw, items in sources if len(raw) == limit and items]
    boundary = (max if not oldest_first else min)(edges, default=None)

    def within(item: ActivityItemRead) -> bool:
        if boundary is None:
            return True
        return item.created_at <= boundary if oldest_first else item.created_at >= boundary

    merged = sorted(
        (item for _, items in sources for item in items if within(item) and _matches(item, outcome, q)),
        key=lambda i: i.created_at,
        reverse=not oldest_first,
    )
    if len(merged) > limit:
        merged = merged[:limit]
        return merged, merged[-1].created_at
    return merged, boundary


def facet_counts(session: Session, organization_id: uuid.UUID, since: datetime) -> dict[str, dict[str, int]]:
    """ponytail: counts at most 500 rows per source — a busier time range
    under-counts. Swap for per-source GROUP BY queries if that's ever hit."""
    items, _ = _collect(session, organization_id, since=since, cursor=None, limit=500)
    facets: dict[str, dict[str, int]] = {"category": {}, "outcome": {}, "application": {}, "total": {"all": len(items)}}
    for item in items:
        facets["category"][item.category] = facets["category"].get(item.category, 0) + 1
        facets["outcome"][item.outcome] = facets["outcome"].get(item.outcome, 0) + 1
        if item.application_id is not None:
            key = str(item.application_id)
            facets["application"][key] = facets["application"].get(key, 0) + 1
    return facets


@router.get("/activity", response_model=ActivityPageRead)
def list_activity(
    session: SessionDep,
    admin: CurrentAdminDep,
    application_id: uuid.UUID | None = None,
    category: str | None = None,
    outcome: str | None = None,
    q: str | None = None,
    since_hours: Annotated[int, Query(ge=1, le=24 * 90)] = 24 * 7,
    cursor: datetime | None = None,
    sort: Literal["newest", "oldest"] = "newest",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ActivityPageRead:
    now = datetime.now(UTC)
    items, next_cursor = _collect(
        session,
        admin.organization_id,
        since=now - timedelta(hours=since_hours),
        cursor=cursor,
        oldest_first=sort == "oldest",
        limit=limit,
        application_id=application_id,
        category=category,
        outcome=outcome,
        q=q.strip() if q else None,
    )
    return ActivityPageRead(
        items=items,
        next_cursor=next_cursor,
        facets=facet_counts(session, admin.organization_id, now - timedelta(hours=since_hours)),
    )
