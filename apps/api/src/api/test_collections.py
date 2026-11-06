"""Test suites — user-made, named groups of test cases per Application
(Smoke, Regression, ...), runnable from the Test runs "Run" dialog.

Named `TestCollection` in code because `domain.TestSuite` already means one
Journey's generated tests; the UI says "Test suites".

A *test case* here is what the Test cases tab lists: a current `Scenario` with
a current `TestAsset` under a current `TestSuite` of a candidate `Journey`
(the same filter `list_test_suites` applies). Membership is stored against the
`Scenario`, so heals and regenerations (which only replace the `TestAsset`)
keep it. A member whose Scenario is no longer such a test case (Explorer
re-promote retires it) is "unavailable": skipped on run, shown struck through,
and removed only when the user says so.

Writes are blocked for viewers by the app-wide `block_viewer_writes`
dependency; every route is scoped to the caller's organization.
"""

import logging
import uuid
from datetime import UTC, datetime

from domain import (
    Application,
    Journey,
    Scenario,
    Schedule,
    TestCollection,
    TestCollectionMember,
    TestResult,
    TestResultArtifact,
    TestRun,
    runnable_asset_external_ids,
    runnable_by_scenario,
)
from domain.test_collection_resolver import Runnable
from fastapi import APIRouter, HTTPException, Query, Response
from object_store import ObjectStore
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from api.activity import record_activity
from api.auth import CurrentOrgIdDep, CurrentUserDep, SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["test-collections"])

COLLECTION_NAME_TAKEN = "COLLECTION_NAME_TAKEN"
COLLECTION_EMPTY = "COLLECTION_EMPTY"
SUITE_HAS_RUNS = "SUITE_HAS_RUNS"
SUITE_RUN_IN_PROGRESS = "SUITE_RUN_IN_PROGRESS"
SUITE_HAS_SCHEDULES = "SUITE_HAS_SCHEDULES"

_IN_PROGRESS = ("pending", "running")
MAX_NAME_LENGTH = 60
# ponytail: one generous cap per list, not a paged/streamed save. "Select all"
# on a big application must still save in one request; a fuller version
# batches on the client if an application ever has more test cases than this.
MAX_MEMBER_IDS = 5000
_RECENT_RUNS = 20


# --- response / request models -------------------------------------------------


class CollectionSummary(BaseModel):
    id: uuid.UUID
    name: str
    # Members that are runnable test cases right now.
    test_case_count: int
    unavailable_count: int
    run_count: int


class CollectionRef(BaseModel):
    id: uuid.UUID
    name: str


class CollectionCaseRead(BaseModel):
    scenario_id: uuid.UUID
    test_case_number: int
    name: str
    journey_id: uuid.UUID
    journey_name: str
    # Other suites this test case is in (the picker's "also in Regression").
    in_collections: list[CollectionRef]


class CollectionMemberRead(BaseModel):
    scenario_id: uuid.UUID
    name: str
    journey_name: str | None = None


class CollectionRunRead(BaseModel):
    id: uuid.UUID
    run_number: int
    suite_name: str | None
    status: str
    created_at: datetime
    total: int
    passed: int
    failed: int


class CollectionDetail(BaseModel):
    id: uuid.UUID
    name: str
    test_case_count: int
    journey_count: int
    run_count: int
    available: list[CollectionMemberRead]
    unavailable: list[CollectionMemberRead]
    recent_runs: list[CollectionRunRead]


class CollectionName(BaseModel):
    name: str

    @field_validator("name", mode="before")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("name")
    @classmethod
    def _length(cls, value: str) -> str:
        if not 1 <= len(value) <= MAX_NAME_LENGTH:
            raise ValueError(f"name must be 1-{MAX_NAME_LENGTH} characters")
        return value


class MembersChange(BaseModel):
    # `Scenario.external_id` values (the ids the picker lists).
    add: list[uuid.UUID] = []
    remove: list[uuid.UUID] = []


# --- helpers ---------------------------------------------------------------------


def _main():
    # ponytail: `_get_org_application` lives in main.py (which imports this
    # router), so it is imported at call time to avoid a cycle — same
    # workaround as `api.environments`. A fuller version moves it into a
    # shared module.
    from api import main

    return main


def _org_application(
    session: Session, organization_id: uuid.UUID, external_id: uuid.UUID
) -> Application:
    return _main()._get_org_application(session, organization_id, external_id)


def _get_collection(
    session: Session, organization_id: uuid.UUID, collection_id: uuid.UUID
) -> tuple[TestCollection, Application]:
    row = session.exec(
        select(TestCollection, Application)
        .join(Application, col(Application.id) == col(TestCollection.application_id))
        .where(
            TestCollection.external_id == collection_id,
            Application.organization_id == organization_id,
            col(Application.deleted_at).is_(None),
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="test suite not found")
    return row


def _runnable(session: Session, application: Application) -> dict[uuid.UUID, Runnable]:
    return runnable_by_scenario(session, application.id)


def _member_ids(
    session: Session, collection_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    by_collection: dict[uuid.UUID, list[uuid.UUID]] = {cid: [] for cid in collection_ids}
    if not collection_ids:
        return by_collection
    for collection_id, scenario_id in session.exec(
        select(TestCollectionMember.collection_id, TestCollectionMember.scenario_id).where(
            col(TestCollectionMember.collection_id).in_(collection_ids)
        )
    ):
        by_collection[collection_id].append(scenario_id)
    return by_collection


def _run_counts(session: Session, collection_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not collection_ids:
        return {}
    return {
        collection_id: count
        for collection_id, count in session.exec(
            select(TestRun.test_collection_id, func.count())
            .where(col(TestRun.test_collection_id).in_(collection_ids))
            .group_by(TestRun.test_collection_id)
        )
        if collection_id is not None
    }


def _commit_name_change(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail=COLLECTION_NAME_TAKEN) from None


def resolve_runnable_asset_ids(
    session: Session, application: Application, collection: TestCollection
) -> list[uuid.UUID]:
    """The `TestAsset.external_id`s a run of this suite executes — its
    available members, resolved now. Raises 409 `COLLECTION_EMPTY` when there
    are none (an empty list would otherwise be read as a Complete run)."""
    ids = runnable_asset_external_ids(session, application.id, collection.id)
    if not ids:
        raise HTTPException(status_code=409, detail=COLLECTION_EMPTY)
    return ids


def get_collection_for_run(
    session: Session, application: Application, collection_id: uuid.UUID
) -> TestCollection:
    collection = session.exec(
        select(TestCollection).where(
            TestCollection.external_id == collection_id,
            TestCollection.application_id == application.id,
        )
    ).first()
    if collection is None:
        raise HTTPException(status_code=404, detail="test suite not found")
    return collection


# --- routes ----------------------------------------------------------------------


def _summaries(
    session: Session, application: Application, collections: list[TestCollection]
) -> list[CollectionSummary]:
    ids = [c.id for c in collections]
    runnable = _runnable(session, application)
    members = _member_ids(session, ids)
    runs = _run_counts(session, ids)
    result = []
    for collection in collections:
        member_ids = members[collection.id]
        available = sum(1 for sid in member_ids if sid in runnable)
        result.append(
            CollectionSummary(
                id=collection.external_id,
                name=collection.name,
                test_case_count=available,
                unavailable_count=len(member_ids) - available,
                run_count=runs.get(collection.id, 0),
            )
        )
    return result


@router.get("/applications/{external_id}/test-collections", response_model=list[CollectionSummary])
def list_collections(
    external_id: uuid.UUID, session: SessionDep, organization_id: CurrentOrgIdDep
) -> list[CollectionSummary]:
    application = _org_application(session, organization_id, external_id)
    collections = session.exec(
        select(TestCollection)
        .where(TestCollection.application_id == application.id)
        .order_by(col(TestCollection.created_at), col(TestCollection.id))
    ).all()
    return _summaries(session, application, list(collections))


@router.get(
    "/applications/{external_id}/test-collection-cases",
    response_model=list[CollectionCaseRead],
)
def list_collection_cases(
    external_id: uuid.UUID, session: SessionDep, organization_id: CurrentOrgIdDep
) -> list[CollectionCaseRead]:
    """Every test case of the application, for the Select test cases dialog —
    lean on purpose (no code or steps), with the other suites each is in."""
    application = _org_application(session, organization_id, external_id)
    runnable = _runnable(session, application)
    collections = {
        c.id: c
        for c in session.exec(
            select(TestCollection).where(TestCollection.application_id == application.id)
        ).all()
    }
    in_collections: dict[uuid.UUID, list[CollectionRef]] = {}
    for collection_id, members in _member_ids(session, list(collections)).items():
        collection = collections[collection_id]
        for scenario_id in members:
            in_collections.setdefault(scenario_id, []).append(
                CollectionRef(id=collection.external_id, name=collection.name)
            )
    cases = sorted(runnable.values(), key=lambda r: r.scenario.test_case_number)
    return [
        CollectionCaseRead(
            scenario_id=r.scenario.external_id,
            test_case_number=r.scenario.test_case_number,
            name=r.scenario.name,
            journey_id=r.journey.external_id,
            journey_name=r.journey.name,
            in_collections=sorted(
                in_collections.get(r.scenario.id, []), key=lambda c: c.name.lower()
            ),
        )
        for r in cases
    ]


@router.post(
    "/applications/{external_id}/test-collections",
    response_model=CollectionSummary,
    status_code=201,
)
def create_collection(
    external_id: uuid.UUID,
    body: CollectionName,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
    user: CurrentUserDep,
) -> CollectionSummary:
    application = _org_application(session, organization_id, external_id)
    collection = TestCollection(
        application_id=application.id, name=body.name, created_by_user_id=user.id
    )
    session.add(collection)
    _commit_name_change(session)
    record_activity(
        session,
        user,
        "test_cases",
        f"Created test suite “{collection.name}”",
        application=application,
    )
    session.commit()
    session.refresh(collection)
    return CollectionSummary(
        id=collection.external_id,
        name=collection.name,
        test_case_count=0,
        unavailable_count=0,
        run_count=0,
    )


@router.get("/test-collections/{collection_id}", response_model=CollectionDetail)
def get_collection(
    collection_id: uuid.UUID, session: SessionDep, organization_id: CurrentOrgIdDep
) -> CollectionDetail:
    collection, application = _get_collection(session, organization_id, collection_id)
    runnable = _runnable(session, application)
    member_ids = _member_ids(session, [collection.id])[collection.id]

    available = sorted(
        (runnable[sid] for sid in member_ids if sid in runnable),
        key=lambda r: r.scenario.test_case_number,
    )
    gone_ids = [sid for sid in member_ids if sid not in runnable]
    gone = (
        session.exec(select(Scenario).where(col(Scenario.id).in_(gone_ids))).all()
        if gone_ids
        else []
    )
    run_count = _run_counts(session, [collection.id]).get(collection.id, 0)
    runs = session.exec(
        select(TestRun)
        .where(TestRun.test_collection_id == collection.id)
        .order_by(col(TestRun.created_at).desc(), col(TestRun.id).desc())
        .limit(_RECENT_RUNS)
    ).all()
    return CollectionDetail(
        id=collection.external_id,
        name=collection.name,
        test_case_count=len(available),
        journey_count=len({r.journey.id for r in available}),
        run_count=run_count,
        available=[
            CollectionMemberRead(
                scenario_id=r.scenario.external_id,
                name=r.scenario.name,
                journey_name=r.journey.name,
            )
            for r in available
        ],
        unavailable=[
            CollectionMemberRead(scenario_id=s.external_id, name=s.name)
            for s in sorted(gone, key=lambda s: s.test_case_number)
        ],
        recent_runs=[
            CollectionRunRead(
                id=run.external_id,
                run_number=run.run_number,
                suite_name=run.suite_name,
                status=run.status,
                created_at=run.created_at,
                total=run.total_count,
                passed=run.passed_count,
                failed=run.failed_count + run.timed_out_count + run.errored_count,
            )
            for run in runs
        ],
    )


@router.patch("/test-collections/{collection_id}", response_model=CollectionSummary)
def rename_collection(
    collection_id: uuid.UUID,
    body: CollectionName,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
    user: CurrentUserDep,
) -> CollectionSummary:
    collection, application = _get_collection(session, organization_id, collection_id)
    old_name = collection.name
    if body.name != old_name:
        collection.name = body.name
        collection.updated_at = datetime.now(UTC)
        session.add(collection)
        _commit_name_change(session)
        # Past and in-progress runs of this suite (and only those) read the new
        # name too; Complete/Selective runs that share the name are untouched.
        session.execute(
            update(TestRun)
            .where(col(TestRun.test_collection_id) == collection.id)
            .values(suite_name=body.name)
        )
        record_activity(
            session,
            user,
            "test_cases",
            f"Renamed test suite “{old_name}” to “{body.name}”",
            application=application,
        )
        session.commit()
        session.refresh(collection)
    return _summaries(session, application, [collection])[0]


@router.put("/test-collections/{collection_id}/members", response_model=CollectionSummary)
def change_members(
    collection_id: uuid.UUID,
    body: MembersChange,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
    user: CurrentUserDep,
) -> CollectionSummary:
    """One atomic add/remove diff (the Select test cases dialog's Save, and
    Remove / Remove all on unavailable cases)."""
    collection, application = _get_collection(session, organization_id, collection_id)
    add_ids, remove_ids = set(body.add), set(body.remove)
    if len(add_ids) > MAX_MEMBER_IDS or len(remove_ids) > MAX_MEMBER_IDS:
        raise HTTPException(
            status_code=422, detail=f"at most {MAX_MEMBER_IDS} test cases per request"
        )
    if add_ids & remove_ids:
        raise HTTPException(
            status_code=422, detail="a test case cannot be added and removed together"
        )

    added = 0
    if add_ids:
        runnable = _runnable(session, application)
        by_external = {r.scenario.external_id: r.scenario.id for r in runnable.values()}
        if not add_ids <= by_external.keys():
            raise HTTPException(
                status_code=422, detail="some test cases are not available in this application"
            )
        existing = set(_member_ids(session, [collection.id])[collection.id])
        new_ids = [by_external[e] for e in add_ids if by_external[e] not in existing]
        if new_ids:
            # ON CONFLICT DO NOTHING: two people saving at once is harmless.
            session.execute(
                pg_insert(TestCollectionMember)
                .values(
                    [
                        {
                            "collection_id": collection.id,
                            "scenario_id": sid,
                            "created_at": datetime.now(UTC),
                        }
                        for sid in new_ids
                    ]
                )
                .on_conflict_do_nothing()
            )
        added = len(new_ids)

    removed = 0
    if remove_ids:
        # Any scenario of this application, current or not: a retired one is
        # exactly what Remove / Remove all targets.
        scenario_pks = session.exec(
            select(Scenario.id, Scenario.external_id)
            .join(Journey, col(Journey.id) == col(Scenario.journey_id))
            .where(
                Journey.application_id == application.id,
                col(Scenario.external_id).in_(remove_ids),
            )
        ).all()
        if len(scenario_pks) != len(remove_ids):
            raise HTTPException(
                status_code=422, detail="some test cases are not in this application"
            )
        result = session.execute(
            delete(TestCollectionMember).where(
                col(TestCollectionMember.collection_id) == collection.id,
                col(TestCollectionMember.scenario_id).in_([pk for pk, _ in scenario_pks]),
            )
        )
        removed = result.rowcount or 0  # type: ignore[attr-defined]

    if added or removed:
        collection.updated_at = datetime.now(UTC)
        session.add(collection)
        parts = []
        if added:
            parts.append(f"added {added}")
        if removed:
            parts.append(f"removed {removed}")
        record_activity(
            session,
            user,
            "test_cases",
            f"Test suite “{collection.name}”: {' and '.join(parts)} "
            f"test case{'s' if added + removed != 1 else ''}",
            application=application,
            details={"added": added, "removed": removed},
        )
    session.commit()
    return _summaries(session, application, [collection])[0]


@router.delete("/test-collections/{collection_id}", status_code=204)
def delete_collection(
    collection_id: uuid.UUID,
    session: SessionDep,
    organization_id: CurrentOrgIdDep,
    user: CurrentUserDep,
    delete_runs: bool = Query(default=False),
) -> Response:
    """Deletes the suite. Its runs are history, so they are only removed when
    the caller says so (`delete_runs=true`, after the user confirms in the
    UI); otherwise a suite with runs is refused and nothing changes. Test
    cases are never touched."""
    collection, application = _get_collection(session, organization_id, collection_id)
    # Checked first and never overridden by `delete_runs`: a schedule would
    # otherwise fire against a suite that no longer exists. Disabled schedules
    # count too — they can be switched back on. The UI lists them (the schedule
    # list already carries `test_collection_id`).
    has_schedule = session.exec(
        select(Schedule.id)
        .where(
            Schedule.test_collection_id == collection.id,
            col(Schedule.deleted_at).is_(None),
        )
        .limit(1)
    ).first()
    if has_schedule is not None:
        raise HTTPException(status_code=409, detail=SUITE_HAS_SCHEDULES)
    runs = session.exec(
        select(TestRun.id, TestRun.external_id, TestRun.status).where(
            TestRun.test_collection_id == collection.id
        )
    ).all()
    if runs and not delete_runs:
        raise HTTPException(status_code=409, detail=SUITE_HAS_RUNS)
    if any(status in _IN_PROGRESS for _, _, status in runs):
        raise HTTPException(status_code=409, detail=SUITE_RUN_IN_PROGRESS)

    run_pks = [pk for pk, _, _ in runs]
    if run_pks:
        result_pks = list(
            session.exec(select(TestResult.id).where(col(TestResult.test_run_id).in_(run_pks)))
        )
        # Leaf first: no FK in this schema cascades.
        if result_pks:
            session.execute(
                delete(TestResultArtifact).where(
                    col(TestResultArtifact.test_result_id).in_(result_pks)
                )
            )
        session.execute(delete(TestResult).where(col(TestResult.test_run_id).in_(run_pks)))
        session.execute(delete(TestRun).where(col(TestRun.id).in_(run_pks)))
    session.execute(
        delete(TestCollectionMember).where(col(TestCollectionMember.collection_id) == collection.id)
    )
    name = collection.name
    session.delete(collection)
    record_activity(
        session,
        user,
        "test_cases",
        f"Deleted test suite “{name}”" + (f" and its {len(runs)} runs" if runs else ""),
        application=application,
        details={"runs_deleted": len(runs)},
    )
    session.commit()

    # After the commit, best effort (as the application purge does): a storage
    # failure leaves orphaned files, never a half-deleted suite.
    if runs:
        store = ObjectStore()
        for _, external_id, _ in runs:
            try:
                store.delete_prefix(f"test-runs/{external_id}/")
            except Exception:
                logger.exception("test suite delete: failed to delete files of run %s", external_id)
    return Response(status_code=204)
