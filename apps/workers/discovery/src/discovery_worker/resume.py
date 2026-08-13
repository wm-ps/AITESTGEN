"""Re-crawl resume for a blocked exploration path (Story 2.16 Task 3, spine
box F — RETURN).

Mechanism replaced 2026-08-03 (see the story's own Dev Notes): the original
design replayed every already-succeeded step with its stored inputs,
skipping steps believed "known-irreversible". That was found unreliable for
four independent reasons (irreversibility isn't knowable from the DOM, deep-
linking past a skipped step usually fails, stored inputs go stale, the
target app may have changed) — replaced with re-crawling forward from the
nearest confirmed entry point using the exact same crawl loop every other
Discovery Run already has to work (`run_discovery_crawl`), never a second,
parallel replay executor. `ExplorationStep` (`activities.py`'s
`_record_exploration_path`) is the diagnostic record of how the block was
reached; this module never executes it.

No caller wires this up yet — Story 2.17's `[GAP — needs UX pass]` applies
here too (answering a `BlockedTask` has no screen in the current 6-screen
IA). `resume_blocked_task` is the whole mechanism, ready for that endpoint
once it exists.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from domain import BlockedTask, ExplorationStep, Page, TestDataEntry
from playwright.async_api import Browser
from sqlmodel import Session, select

from discovery_worker.crawler import run_discovery_crawl
from discovery_worker.data_resolver import PoolEntry
from discovery_worker.diagnostics import record_diagnostic
from discovery_worker.session import establish_session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResumeResult:
    resumed_from_root: bool
    entry_point_url: str


def _write_pool_entry(
    session: Session,
    application_id: uuid.UUID,
    blocked_task: BlockedTask,
    value: str,
    is_sensitive: bool,
) -> None:
    """AC 3: the supplied value is written into the Test Data Pool under the
    block's `aggregation_key` — available everywhere that key appears
    (Story 2.20), not just re-injected on this one path."""
    existing = session.exec(
        select(TestDataEntry).where(
            TestDataEntry.application_id == application_id,
            TestDataEntry.normalized_key == blocked_task.aggregation_key,
        )
    ).first()
    if existing is not None:
        existing.value = value
        existing.is_sensitive = is_sensitive
        session.add(existing)
    else:
        session.add(
            TestDataEntry(
                application_id=application_id,
                label=blocked_task.required_description,
                normalized_key=blocked_task.aggregation_key,
                value=value,
                is_sensitive=is_sensitive,
            )
        )
    session.commit()


def _nearest_confirmed_entry_point(session: Session, blocked_task: BlockedTask) -> str | None:
    """AC 3/6: walks the recorded `ExplorationStep` path backwards (skipping
    every step recorded on the *same page* as the block — a repeat block on
    the same field can record several such steps across attempts/runs, and
    none of them ever resolved, so none is a valid re-entry point) for the
    last step whose `Page` is still canonical. Actual URL-reachability is
    confirmed by the resumed crawl itself when it re-navigates there and
    re-fingerprints (Story 2.10) — this function only picks the candidate.
    `None` means no step qualifies; the caller falls back to the Application
    root."""
    steps = list(
        session.exec(
            select(ExplorationStep)
            .where(ExplorationStep.blocked_task_id == blocked_task.id)
            .order_by(ExplorationStep.step_order.desc())  # type: ignore[arg-type]
        ).all()
    )
    if not steps:
        return None
    blocked_page_id = steps[0].page_id
    for step in steps:
        if step.page_id == blocked_page_id:
            continue
        page = session.get(Page, step.page_id)
        if page is not None and page.merged_into_id is None:
            return page.url
    return None


async def resume_blocked_task(
    session: Session,
    browser: Browser,
    *,
    application,
    blocked_task: BlockedTask,
    supplied_value: str,
    credential: bytes,
    object_store,
    discovery_run_id: uuid.UUID,
    is_sensitive: bool = False,
    pool: dict[str, PoolEntry] | None = None,
) -> ResumeResult:
    """AC 3/4/6: the whole re-crawl resume mechanism.

    1. Write `supplied_value` into the Test Data Pool under the block's key.
    2. Establish a fresh session (Story 2.2's `establish_session` — never
       assume the blocking session survived).
    3. Pick the nearest confirmed entry point, or fall back to the
       Application root, recording which happened (AC 6: resume degrades,
       never fails silently).
    4. Re-crawl forward from there under normal rules — Story 2.12 safety,
       Story 2.19 loop guards, Story 2.11 state return all apply unchanged,
       since this is the exact same `run_discovery_crawl` every other run
       uses, not a second execution path.
    5. Mark `blocked_task` resolved — the pool now satisfies the aggregation
       key by construction (`data_resolver.resolve()`'s step 1), so this
       resume crawl cannot re-DEFER on the same key.

    `pool` is the caller's existing Test Data Pool (e.g. from
    `activities.py`'s `_seed_test_data_pool`) merged with the newly supplied
    value — omit it to resume with only this one value available.
    """
    _write_pool_entry(session, application.id, blocked_task, supplied_value, is_sensitive)

    entry_point_url = _nearest_confirmed_entry_point(session, blocked_task)
    resumed_from_root = entry_point_url is None
    start_url = entry_point_url or application.url

    record_diagnostic(
        session,
        discovery_run_id,
        "resume",
        {
            "blocked_task_id": str(blocked_task.id),
            "aggregation_key": blocked_task.aggregation_key,
            "resumed_from_root": resumed_from_root,
            "entry_point_url": start_url,
        },
    )

    context = await establish_session(
        browser,
        auth_method=application.auth_method,
        credential=credential,
        base_url=application.url,
        login_url=application.login_url,
    )
    resume_pool = dict(pool or {})
    resume_pool[blocked_task.aggregation_key] = PoolEntry(
        value=supplied_value, is_sensitive=is_sensitive
    )
    try:
        await run_discovery_crawl(
            context,
            start_url,
            object_store,
            discovery_run_id,
            auth_method=application.auth_method,
            credential=credential,
            data_resolver_pool=resume_pool,
        )
    finally:
        await context.close()

    blocked_task.status = "resolved"
    blocked_task.resolved_at = datetime.now(UTC)
    session.add(blocked_task)
    session.commit()

    return ResumeResult(resumed_from_root=resumed_from_root, entry_point_url=start_url)
