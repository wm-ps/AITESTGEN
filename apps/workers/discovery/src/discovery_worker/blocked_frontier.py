"""Blocked Frontier — normalized-key aggregated deferral (Story 2.15, spine
box E — ACT).

`attach_or_create` is the Planner-DEFER write path (AC 1/2/3/4): looked up
by `(application_id, aggregation_key)` alone — a block is a property of the
Application, not one Discovery Run of it, so a key that was already open
from an earlier run attaches instead of duplicating. Returns immediately
either way; there is no wait/sleep/user-input call anywhere on this path
(AC 4 — a blocked area never stops the crawl).

`consolidated_view` is the read side (AC 5), consumed by Story 2.22's
report — grouped in Python, not SQL, as a defensive net in case
`attach_or_create`'s own select-then-write ever raced a concurrent
Discovery Run for the same Application into two open rows for the same key
(the same race shape `activities.py`'s `InferenceActivity` already guards
against for `Journey.identity_key`). The primary de-dup is `attach_or_create`
itself; this is a safety net, not the mechanism.

AC 6 (a Test Data Pool entry satisfies a block without a new ask) needs no
code here: Story 2.13's `data_resolver.resolve()` already checks the pool
*first*, before ever returning `None` (the only trigger for a data-type
DEFER) — so a populated pool entry means `resolve()` never returns `None`
for that key in the first place, and `attach_or_create` is never even
called. Verified by a regression test, not a new mechanism.
"""

import uuid
from dataclasses import dataclass

from domain import BlockedTask
from sqlmodel import Session, select

_INITIAL_STATUS = {"data": "blocked_data", "approval": "blocked_approval"}


def attach_or_create(
    session: Session,
    *,
    application_id: uuid.UUID,
    discovery_run_id: uuid.UUID,
    aggregation_key: str,
    required_description: str,
    required_type: str,
) -> BlockedTask:
    """AC 1/3: attach to the open `BlockedTask` for this key, or create one.
    A key already open for the *other* `required_type` is upgraded to
    `blocked_both` — never downgraded once both have been seen."""
    existing = session.exec(
        select(BlockedTask).where(
            BlockedTask.application_id == application_id,
            BlockedTask.aggregation_key == aggregation_key,
            BlockedTask.status != "resolved",
        )
    ).first()

    if existing is None:
        task = BlockedTask(
            application_id=application_id,
            discovery_run_id=discovery_run_id,
            status=_INITIAL_STATUS[required_type],
            aggregation_key=aggregation_key,
            required_description=required_description,
            required_type=required_type,
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        return task

    existing.waiting_count += 1
    if existing.status != "blocked_both" and existing.status != _INITIAL_STATUS[required_type]:
        existing.status = "blocked_both"
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return existing


@dataclass(frozen=True)
class ConsolidatedBlock:
    aggregation_key: str
    required_description: str
    required_type: str
    status: str
    waiting_count: int


def consolidated_view(session: Session, application_id: uuid.UUID) -> list[ConsolidatedBlock]:
    """AC 5: one item per distinct `aggregation_key`, with the (usually
    already-consolidated) waiting-path count and whether it's blocked on
    data, approval, or both."""
    open_tasks = session.exec(
        select(BlockedTask).where(
            BlockedTask.application_id == application_id, BlockedTask.status != "resolved"
        )
    ).all()

    grouped: dict[str, ConsolidatedBlock] = {}
    for task in open_tasks:
        current = grouped.get(task.aggregation_key)
        if current is None:
            grouped[task.aggregation_key] = ConsolidatedBlock(
                aggregation_key=task.aggregation_key,
                required_description=task.required_description,
                required_type=task.required_type,
                status=task.status,
                waiting_count=task.waiting_count,
            )
            continue
        merged_status = current.status
        if "blocked_both" in (current.status, task.status) or current.required_type != (
            task.required_type
        ):
            merged_status = "blocked_both"
        grouped[task.aggregation_key] = ConsolidatedBlock(
            aggregation_key=current.aggregation_key,
            required_description=current.required_description,
            required_type=current.required_type,
            status=merged_status,
            waiting_count=current.waiting_count + task.waiting_count,
        )
    return list(grouped.values())
