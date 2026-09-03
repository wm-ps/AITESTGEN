"""FindPurgeCandidatesActivity / PurgeApplicationActivity — the I/O boundary
CleanupWorkflow dispatches to (AD-2).

`Application` soft-delete (`deleted_at`, AD-15) never purged anything —
child rows across ~26 dependent tables, the Vault secret, and S3 objects all
accumulated forever. This purges all of it, once `deleted_at` is older than
the admin-configured `DiscoverySettings.delete_project_after` window.

Delete order matters: no FK in this schema has `ondelete=CASCADE` (confirmed
by inspecting every migration that adds one), so dependent rows are deleted
leaf-first, in the order below, inside one DB transaction per Application —
either the whole Application purges, or none of it does. Vault/S3 deletes
happen only after that transaction commits, since a partially-failed
Vault/S3 cleanup is cleanup debt (loggable, retriable), not a correctness
risk — the row is already gone from every user-facing query path by then.

`PurgeApplicationActivity` re-checks eligibility itself (deleted_at set, and
past the *current* cutoff) rather than trusting the candidate list handed to
it — the setting or the row could have changed between the two Activity
calls, and an irreversible bulk delete must never skip that re-check. Every
delete is a `WHERE`-scoped bulk statement (not fetch-then-delete-by-id), so a
Temporal retry of an already-purged Application is a safe no-op.

Schedules feature: `schedule` rows are deleted after `test_run` (the FK
runs `test_run.schedule_id -> schedule.id`, so the referencing rows must go
first). The live Temporal Schedule objects are not reachable from this sync
activity — they're already paused by `delete_application` (apps/api) at
soft-delete time, so a leftover Temporal object here is inert, and
`purge_orphan_schedules.py` sweeps it later.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from domain import (
    Action,
    ApiEndpoint,
    Application,
    Assertion,
    BlockedTask,
    Capability,
    Component,
    ComponentLocator,
    DiagnosticRecord,
    DiscoveryError,
    DiscoveryRun,
    DiscoverySettings,
    ExplorationStep,
    Form,
    FormField,
    Journey,
    JourneyStep,
    Page,
    PageTransition,
    Scenario,
    Schedule,
    SyntheticDataEntry,
    TestAsset,
    TestDataEntry,
    TestResult,
    TestResultArtifact,
    TestRun,
    TestSuite,
    ValidationRule,
)
from object_store import ObjectStore
from secrets_client.vault_client import SecretRef, VaultSecretsClient
from sqlalchemy import ColumnElement, delete
from sqlmodel import Session, select
from temporalio import activity
from workflows import PurgeApplicationInput, PurgeApplicationResult

from execution_worker.db import engine

logger = logging.getLogger(__name__)

_RETENTION_DAYS = {"1_day": 1, "1_week": 7, "1_month": 30}


# SQLModel/pyright limitation (same one the codebase already suppresses
# per-callsite with `# type: ignore[attr-defined]`, e.g.
# execution_worker/activities.py): a Field-typed column's declared Python
# type (`uuid.UUID`, `str`, ...) shadows its real `InstrumentedAttribute`
# type, so pyright sees `Model.col == value`/`.in_(...)` as returning a
# plain `bool`/erroring, not a `ColumnElement[bool]`. Cast once here instead
# of re-suppressing at every one of this module's ~20 delete callsites.
def _eq(column: Any, value: Any) -> ColumnElement[bool]:
    return cast("ColumnElement[bool]", column == value)


def _in(column: Any, values: list[Any]) -> ColumnElement[bool]:
    return cast("ColumnElement[bool]", column.in_(values))


@dataclass
class _PurgeIds:
    discovery_run_ids: list[uuid.UUID]
    journey_ids: list[uuid.UUID]
    form_ids: list[uuid.UUID]
    form_field_ids: list[uuid.UUID]
    component_ids: list[uuid.UUID]
    blocked_task_ids: list[uuid.UUID]
    test_run_ids: list[uuid.UUID]
    test_suite_ids: list[uuid.UUID]
    test_result_ids: list[uuid.UUID]
    test_data_secret_refs: list[str]


def _cutoff(settings: DiscoverySettings) -> datetime:
    days = _RETENTION_DAYS[settings.delete_project_after]
    return datetime.now(UTC) - timedelta(days=days)


@activity.defn(name="FindPurgeCandidatesActivity")
def find_purge_candidates_activity() -> list[str]:
    with Session(engine) as session:
        settings = session.exec(select(DiscoverySettings)).one()
        cutoff = _cutoff(settings)
        applications = session.exec(
            select(Application).where(
                Application.deleted_at.is_not(None),  # type: ignore[union-attr]
                Application.deleted_at <= cutoff,  # type: ignore[operator]
            )
        ).all()
        candidate_ids = [str(a.external_id) for a in applications]

    logger.info(
        "cleanup: %d application(s) past retention (%s): %s",
        len(candidate_ids),
        settings.delete_project_after,
        candidate_ids,
    )
    return candidate_ids


def _collect_purge_ids(session: Session, application_id: uuid.UUID) -> _PurgeIds:
    discovery_run_ids = list(
        session.exec(
            select(DiscoveryRun.id).where(_eq(DiscoveryRun.application_id, application_id))
        )
    )
    journey_ids = list(
        session.exec(select(Journey.id).where(_eq(Journey.application_id, application_id)))
    )
    form_ids = list(session.exec(select(Form.id).where(_eq(Form.application_id, application_id))))
    form_field_ids = (
        list(session.exec(select(FormField.id).where(_in(FormField.form_id, form_ids))))
        if form_ids
        else []
    )
    component_ids = list(
        session.exec(select(Component.id).where(_eq(Component.application_id, application_id)))
    )
    blocked_task_ids = list(
        session.exec(select(BlockedTask.id).where(_eq(BlockedTask.application_id, application_id)))
    )
    test_run_ids = list(
        session.exec(select(TestRun.id).where(_eq(TestRun.application_id, application_id)))
    )
    test_suite_ids = (
        list(session.exec(select(TestSuite.id).where(_in(TestSuite.journey_id, journey_ids))))
        if journey_ids
        else []
    )
    test_result_ids = (
        list(session.exec(select(TestResult.id).where(_in(TestResult.test_run_id, test_run_ids))))
        if test_run_ids
        else []
    )
    test_data_secret_refs = [
        ref
        for ref in session.exec(
            select(TestDataEntry.secret_ref).where(
                _eq(TestDataEntry.application_id, application_id)
            )
        )
        if ref is not None
    ]

    return _PurgeIds(
        discovery_run_ids=discovery_run_ids,
        journey_ids=journey_ids,
        form_ids=form_ids,
        form_field_ids=form_field_ids,
        component_ids=component_ids,
        blocked_task_ids=blocked_task_ids,
        test_run_ids=test_run_ids,
        test_suite_ids=test_suite_ids,
        test_result_ids=test_result_ids,
        test_data_secret_refs=test_data_secret_refs,
    )


def _delete_dependent_rows(session: Session, application_id: uuid.UUID, ids: _PurgeIds) -> int:
    """Leaf-first delete order — see module docstring. Each statement is
    scoped by `WHERE`, so it's a safe no-op on retry."""
    rows_deleted = 0

    def _run(stmt: Any) -> None:
        nonlocal rows_deleted
        result = session.execute(stmt)
        rows_deleted += result.rowcount or 0  # type: ignore[attr-defined]

    if ids.form_field_ids:
        _run(delete(ValidationRule).where(_in(ValidationRule.form_field_id, ids.form_field_ids)))
    if ids.form_ids:
        _run(delete(FormField).where(_in(FormField.form_id, ids.form_ids)))
    if ids.blocked_task_ids:
        _run(
            delete(ExplorationStep).where(
                _in(ExplorationStep.blocked_task_id, ids.blocked_task_ids)
            )
        )
    if ids.test_result_ids:
        _run(
            delete(TestResultArtifact).where(
                _in(TestResultArtifact.test_result_id, ids.test_result_ids)
            )
        )
    if ids.test_run_ids:
        _run(delete(TestResult).where(_in(TestResult.test_run_id, ids.test_run_ids)))
    if ids.test_suite_ids:
        _run(delete(TestAsset).where(_in(TestAsset.test_suite_id, ids.test_suite_ids)))
    if ids.component_ids:
        _run(delete(ComponentLocator).where(_in(ComponentLocator.component_id, ids.component_ids)))
    if ids.journey_ids:
        _run(delete(JourneyStep).where(_in(JourneyStep.journey_id, ids.journey_ids)))
        _run(delete(TestSuite).where(_in(TestSuite.journey_id, ids.journey_ids)))
        _run(delete(Scenario).where(_in(Scenario.journey_id, ids.journey_ids)))
    _run(delete(Assertion).where(_eq(Assertion.application_id, application_id)))
    _run(delete(Component).where(_eq(Component.application_id, application_id)))
    _run(delete(PageTransition).where(_eq(PageTransition.application_id, application_id)))
    _run(delete(ApiEndpoint).where(_eq(ApiEndpoint.application_id, application_id)))
    _run(delete(Form).where(_eq(Form.application_id, application_id)))
    _run(delete(Action).where(_eq(Action.application_id, application_id)))
    _run(delete(SyntheticDataEntry).where(_eq(SyntheticDataEntry.application_id, application_id)))
    _run(delete(Page).where(_eq(Page.application_id, application_id)))
    _run(delete(BlockedTask).where(_eq(BlockedTask.application_id, application_id)))
    _run(delete(DiscoveryError).where(_eq(DiscoveryError.application_id, application_id)))
    _run(delete(TestDataEntry).where(_eq(TestDataEntry.application_id, application_id)))
    _run(delete(TestRun).where(_eq(TestRun.application_id, application_id)))
    # Schedules feature: schedule rows are referenced by test_run.schedule_id
    # (no FK has ondelete=CASCADE in this schema), so this must come after
    # TestRun is gone above, not before. The live Temporal Schedule objects
    # themselves are NOT reachable from here (this is a sync activity, no
    # Temporal client) — they're already paused (Application soft-delete
    # pauses every one, see delete_application in apps/api), so a leftover
    # Temporal object is inert; purge_orphan_schedules.py sweeps it later.
    _run(delete(Schedule).where(_eq(Schedule.application_id, application_id)))
    _run(delete(Journey).where(_eq(Journey.application_id, application_id)))
    _run(delete(Capability).where(_eq(Capability.application_id, application_id)))
    if ids.discovery_run_ids:
        _run(
            delete(DiagnosticRecord).where(
                _in(DiagnosticRecord.discovery_run_id, ids.discovery_run_ids)
            )
        )
    _run(delete(DiscoveryRun).where(_eq(DiscoveryRun.application_id, application_id)))

    return rows_deleted


@activity.defn(name="PurgeApplicationActivity")
def purge_application_activity(input: PurgeApplicationInput) -> PurgeApplicationResult:
    with Session(engine) as session:
        settings = session.exec(select(DiscoverySettings)).one()
        cutoff = _cutoff(settings)
        application = session.exec(
            select(Application).where(_eq(Application.external_id, uuid.UUID(input.application_id)))
        ).first()

        if application is None or application.deleted_at is None or application.deleted_at > cutoff:
            logger.info(
                "cleanup: skipping %s — no longer eligible for purge", input.application_id
            )
            return PurgeApplicationResult(application_id=input.application_id, skipped=True)

        application_id = application.id
        secret_ref = application.secret_ref
        ids = _collect_purge_ids(session, application_id)
        discovery_run_ids = ids.discovery_run_ids
        test_run_ids = ids.test_run_ids
        secret_refs = [secret_ref, *ids.test_data_secret_refs]

        rows_deleted = _delete_dependent_rows(session, application_id, ids)
        session.delete(application)
        session.commit()
        rows_deleted += 1  # the application row itself

    vault = VaultSecretsClient()
    vault_deleted = 0
    for ref in secret_refs:
        try:
            vault.delete(SecretRef(path=ref))
            vault_deleted += 1
        except Exception:
            logger.exception(
                "cleanup: failed to delete Vault secret for application %s", input.application_id
            )

    store = ObjectStore()
    s3_deleted = 0
    prefixes = [f"discovery-runs/{rid}/" for rid in discovery_run_ids] + [
        f"test-runs/{rid}/" for rid in test_run_ids
    ]
    for prefix in prefixes:
        try:
            s3_deleted += store.delete_prefix(prefix)
        except Exception:
            logger.exception(
                "cleanup: failed to delete S3 prefix %s for application %s",
                prefix,
                input.application_id,
            )

    logger.info(
        "cleanup: purged application %s — %d db rows, %d vault secrets, %d s3 objects",
        input.application_id,
        rows_deleted,
        vault_deleted,
        s3_deleted,
    )
    return PurgeApplicationResult(
        application_id=input.application_id,
        skipped=False,
        rows_deleted=rows_deleted,
        vault_secrets_deleted=vault_deleted,
        s3_objects_deleted=s3_deleted,
    )
