"""Story 2.15: normalized-key aggregated deferral — `attach_or_create`'s
find-or-create/upgrade logic and `consolidated_view`'s read-time grouping.
Real Postgres (the attach-or-create lookup and the upgrade-to-`blocked_both`
transition are both DB-round-trip behaviour, not pure logic), same
skip-cleanly convention as `test_discovery_activity_integration.py`.
"""

import uuid

import pytest
from discovery_worker.blocked_frontier import attach_or_create, consolidated_view
from discovery_worker.data_resolver import PoolEntry, ResolutionLog, field_key, resolve
from discovery_worker.db import engine
from domain import Application, DiscoveryRun, Organization, aggregation_key
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel


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


def _seed_application_and_run() -> tuple[uuid.UUID, uuid.UUID]:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        application = Application(
            organization_id=org.id,
            name="Blocked Frontier Test App",
            url="https://app.example.com",
            environment="test",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.flush()

        run = DiscoveryRun(application_id=application.id)
        session.add(run)
        session.commit()
        return application.id, run.id


def test_four_paths_needing_the_same_field_produce_one_open_blocked_task() -> None:
    application_id, discovery_run_id = _seed_application_and_run()
    key = aggregation_key("Policy Number", "text", "*")

    with Session(engine) as session:
        for _ in range(4):
            attach_or_create(
                session,
                application_id=application_id,
                discovery_run_id=discovery_run_id,
                aggregation_key=key,
                required_description="Active Policy Number",
                required_type="data",
            )

        results = consolidated_view(session, application_id)
        assert len(results) == 1
        assert results[0].waiting_count == 4
        assert results[0].status == "blocked_data"


def test_differently_worded_descriptions_still_aggregate_to_one_key() -> None:
    """AC 2 — the specific regression this story's rewrite exists to
    prevent: exact-prose matching would have produced two rows here."""
    key_a = aggregation_key("Active Policy Number", "text", "*")
    key_b = aggregation_key("Policy Number (Active)", "text", "*")
    assert key_a == key_b

    application_id, discovery_run_id = _seed_application_and_run()
    with Session(engine) as session:
        attach_or_create(
            session,
            application_id=application_id,
            discovery_run_id=discovery_run_id,
            aggregation_key=key_a,
            required_description="Active Policy Number",
            required_type="data",
        )
        attach_or_create(
            session,
            application_id=application_id,
            discovery_run_id=discovery_run_id,
            aggregation_key=key_b,
            required_description="Policy Number (Active)",
            required_type="data",
        )

        results = consolidated_view(session, application_id)
        assert len(results) == 1
        assert results[0].waiting_count == 2


def test_a_key_blocked_for_both_data_and_approval_becomes_blocked_both() -> None:
    application_id, discovery_run_id = _seed_application_and_run()
    key = aggregation_key("Approve Claim", "action_approval", "/claims/{id}")

    with Session(engine) as session:
        first = attach_or_create(
            session,
            application_id=application_id,
            discovery_run_id=discovery_run_id,
            aggregation_key=key,
            required_description="Approve Claim",
            required_type="data",
        )
        assert first.status == "blocked_data"

        second = attach_or_create(
            session,
            application_id=application_id,
            discovery_run_id=discovery_run_id,
            aggregation_key=key,
            required_description="Approve Claim",
            required_type="approval",
        )
        assert second.id == first.id
        assert second.status == "blocked_both"


def test_resolved_tasks_are_excluded_from_the_consolidated_view() -> None:
    application_id, discovery_run_id = _seed_application_and_run()
    key = aggregation_key("Resolved Field", "text", "*")

    with Session(engine) as session:
        task = attach_or_create(
            session,
            application_id=application_id,
            discovery_run_id=discovery_run_id,
            aggregation_key=key,
            required_description="Resolved Field",
            required_type="data",
        )
        task.status = "resolved"
        session.add(task)
        session.commit()

        assert consolidated_view(session, application_id) == []


def test_pool_entry_satisfies_an_otherwise_deferred_field_without_a_new_ask() -> None:
    """AC 6 — no `attach_or_create` code is needed for this: Story 2.13's
    `resolve()` already checks the pool before it can ever return `None`
    (the only trigger for a data-type DEFER), so a populated pool entry
    means the block is never even attempted a second time."""
    pool = {field_key("Policy Number", "text"): PoolEntry(value="POL-999")}
    result = resolve(
        field_name="Policy Number",
        input_type="text",
        route_family="/claims/{id}",
        pool=pool,
        log=ResolutionLog(),
        generic_value="Test value",
    )
    assert result is not None
    assert result.value == "POL-999"
    assert result.source == "pool"
