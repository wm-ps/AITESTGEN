"""ExplorationStep entity (Story 2.16 Task 1) — real Postgres, same
skip-cleanly convention as test_discovery_error.py.
"""

import uuid

import pytest
from discovery_worker.db import engine, init_db
from discovery_worker.resume import _nearest_confirmed_entry_point
from domain import (
    Application,
    BlockedTask,
    DiscoveryRun,
    ExplorationStep,
    Organization,
    Page,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, select


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)


def _seed_blocked_task_and_page() -> tuple[uuid.UUID, uuid.UUID]:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Exploration Step Test App",
            url="https://example.test",
            environment="test",
            secret_ref="unused",
        )
        session.add(application)
        session.flush()
        run = DiscoveryRun(application_id=application.id)
        session.add(run)
        session.flush()
        page = Page(
            application_id=application.id,
            discovery_run_id=run.id,
            url="https://example.test/wizard/step-c",
            title="Step C",
        )
        session.add(page)
        session.flush()
        blocked_task = BlockedTask(
            application_id=application.id,
            discovery_run_id=run.id,
            aggregation_key="*:text:policy-number",
            required_description="Active Policy Number",
            required_type="data",
        )
        session.add(blocked_task)
        session.commit()
        return blocked_task.id, page.id


def test_exploration_step_round_trips_ordered_path() -> None:
    init_db()
    blocked_task_id, page_id = _seed_blocked_task_and_page()

    with Session(engine) as session:
        session.add(
            ExplorationStep(
                blocked_task_id=blocked_task_id,
                step_order=1,
                page_id=page_id,
                action_description="Navigation",
                input_values={},
            )
        )
        session.add(
            ExplorationStep(
                blocked_task_id=blocked_task_id,
                step_order=2,
                page_id=page_id,
                action_description="Policy Number",
                input_values={"requested": "Policy Number"},
            )
        )
        session.commit()

    with Session(engine) as session:
        steps = list(
            session.exec(
                select(ExplorationStep)
                .where(ExplorationStep.blocked_task_id == blocked_task_id)
                .order_by(ExplorationStep.step_order)  # type: ignore[arg-type]
            ).all()
        )

    assert [s.step_order for s in steps] == [1, 2]
    assert steps[1].input_values == {"requested": "Policy Number"}


def test_duplicate_step_order_for_the_same_blocked_task_is_rejected() -> None:
    """The `UNIQUE(blocked_task_id, step_order)` constraint (Task 1) — the
    same guarantee `_record_exploration_path`'s own step-order-continuation
    logic relies on to never collide on a repeat block (AC 5)."""
    init_db()
    blocked_task_id, page_id = _seed_blocked_task_and_page()

    with Session(engine) as session:
        session.add(
            ExplorationStep(
                blocked_task_id=blocked_task_id,
                step_order=1,
                page_id=page_id,
                action_description="first",
                input_values={},
            )
        )
        session.commit()

        session.add(
            ExplorationStep(
                blocked_task_id=blocked_task_id,
                step_order=1,
                page_id=page_id,
                action_description="colliding duplicate",
                input_values={},
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_nearest_entry_point_skips_every_step_on_the_blocked_page_itself() -> None:
    """AC 6, the genuine degenerate case: every recorded step sits on the
    same page as the block (e.g. a repeat block with no real preceding hop
    ever recorded) — no entry point qualifies, `resume.py`'s caller must
    fall back to the Application root rather than re-enter the blocked page
    itself (which never resolved and never will)."""
    init_db()
    blocked_task_id, page_id = _seed_blocked_task_and_page()

    with Session(engine) as session:
        session.add(
            ExplorationStep(
                blocked_task_id=blocked_task_id,
                step_order=1,
                page_id=page_id,
                action_description="Policy Number",
                input_values={"requested": "Policy Number"},
            )
        )
        session.add(
            ExplorationStep(
                blocked_task_id=blocked_task_id,
                step_order=2,
                page_id=page_id,
                action_description="Policy Number",
                input_values={"requested": "Policy Number"},
            )
        )
        session.commit()

        blocked_task = session.get(BlockedTask, blocked_task_id)
        assert blocked_task is not None
        assert _nearest_confirmed_entry_point(session, blocked_task) is None


def test_nearest_entry_point_finds_the_last_different_canonical_page() -> None:
    """The normal case: the step immediately preceding the block sits on a
    different, still-canonical page — that page's URL is the entry point,
    not the blocked page and not the Application root."""
    init_db()
    blocked_task_id, blocked_page_id = _seed_blocked_task_and_page()

    with Session(engine) as session:
        blocked_task = session.get(BlockedTask, blocked_task_id)
        assert blocked_task is not None
        entry_page = Page(
            application_id=blocked_task.application_id,
            discovery_run_id=blocked_task.discovery_run_id,
            url="https://example.test/wizard/step-b",
            title="Step B",
        )
        session.add(entry_page)
        session.flush()

        session.add(
            ExplorationStep(
                blocked_task_id=blocked_task_id,
                step_order=1,
                page_id=entry_page.id,
                action_description="Navigation",
                input_values={},
            )
        )
        session.add(
            ExplorationStep(
                blocked_task_id=blocked_task_id,
                step_order=2,
                page_id=blocked_page_id,
                action_description="Policy Number",
                input_values={"requested": "Policy Number"},
            )
        )
        session.commit()

        assert _nearest_confirmed_entry_point(session, blocked_task) == entry_page.url
