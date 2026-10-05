"""Persisting a finished recording — plan §8/"Persistence logic reuse".

Reuses the *shape* of `generation_worker.live_exploration_activities
._create_live_journey_sync` (identity-key + name-dedup) for the Journey
row, and the same atomic-claim/get-or-create idioms
`generation_worker.activities._claim_test_case_number_sync`/
`_ensure_test_suite_sync` use for the rest of the chain — reimplemented as
plain functions here (not imported: those are that worker's own
Temporal-activity-private helpers, and duplicating a ~10-line SQL idiom is
the same "different caller, not worth the coupling" call
`generation_worker.spec_linter` already makes for its own login-page
heuristic).

No Temporal activity wrapper, same sync-vs-workflow reasoning already
established for this feature: this is a bounded, fast, DB-only operation
once a recording is finished, exactly like `terminate_test_suite`/the
journey/scenario PATCH/DELETE endpoints in `apps/api/src/api/main.py`
already are.

`TestSuite` is one-per-Journey (DB-constrained `(journey_id,
generation_run_id)`, not `application_id`), and `TestAsset`/`Scenario`
both require one — so recordings share a single per-Application "Recorded
tests" Journey + its TestSuite (see `get_or_create_recorded_tests_journey_
sync`), each recording adding one more Scenario/TestAsset to it, rather
than each minting a Journey of its own.
"""

import hashlib
import uuid
from dataclasses import dataclass

from domain import Application, DiscoveryRun, Journey, Scenario, TestAsset, TestSuite
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from recording_worker.auth_tag import apply_auth_tag
from recording_worker.db import engine


@dataclass(frozen=True)
class SavedRecording:
    journey_external_id: uuid.UUID
    scenario_external_id: uuid.UUID
    test_case_number: int


def load_application_sync(application_id: uuid.UUID) -> Application:
    with Session(engine) as session:
        application = session.get(Application, application_id)
        assert application is not None
        session.expunge(application)
        return application


def _claim_test_case_number_sync(session: Session, application_id: uuid.UUID) -> int:
    return session.execute(
        update(Application)
        .where(Application.id == application_id)  # type: ignore[arg-type]
        .values(next_test_case_number=Application.next_test_case_number + 1)
        .returning(Application.next_test_case_number - 1)  # type: ignore[arg-type]
    ).scalar_one()


# Every recording lands as one more test case in a single per-Application
# "Recorded tests" Journey/TestSuite, never a Journey of its own (that used
# to mint "Recorded flow (2)", "(3)", ... — one Journey per recording). A
# fixed identity key makes `uq_journey_application_id_identity_key` the
# get-or-create's race guard, the same way `_ensure_test_suite_sync` leans
# on its own unique constraint below.
RECORDED_TESTS_JOURNEY_NAME = "Recorded tests"
RECORDED_TESTS_JOURNEY_DESCRIPTION = "Test cases recorded via Record and Play"
RECORDED_TESTS_IDENTITY_KEY = hashlib.sha256(b"recording:bucket").hexdigest()
# What every per-recording Journey created before the bucket existed was
# described as — how `convert_legacy_recordings.py` finds them.
LEGACY_RECORDING_JOURNEY_DESCRIPTION = "Recorded via Record and Play"


def _select_recorded_tests_journey(session: Session, application_id: uuid.UUID) -> Journey | None:
    return session.exec(
        select(Journey).where(
            Journey.application_id == application_id,
            Journey.identity_key == RECORDED_TESTS_IDENTITY_KEY,
        )
    ).first()


def get_or_create_recorded_tests_journey_sync(
    session: Session, *, application_id: uuid.UUID, discovery_run_id: uuid.UUID
) -> Journey:
    existing = _select_recorded_tests_journey(session, application_id)
    if existing is not None:
        return existing
    journey = Journey(
        application_id=application_id,
        discovery_run_id=discovery_run_id,
        name=RECORDED_TESTS_JOURNEY_NAME,
        description=RECORDED_TESTS_JOURNEY_DESCRIPTION,
        identity_key=RECORDED_TESTS_IDENTITY_KEY,
        attempt=1,
        captured_flow=None,
    )
    session.add(journey)
    try:
        # Savepoint, so losing the race doesn't roll back the caller's
        # outer transaction (the legacy conversion runs inside one).
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        journey = _select_recorded_tests_journey(session, application_id)
        assert journey is not None
    return journey


def ensure_test_suite_sync(session: Session, journey: Journey) -> TestSuite:
    existing = session.exec(
        select(TestSuite).where(
            TestSuite.journey_id == journey.id,
            TestSuite.generation_run_id == journey.attempt,
        )
    ).first()
    if existing is not None:
        return existing
    test_suite = TestSuite(
        journey_id=journey.id,
        name=f"{journey.name} Test Suite",
        generation_run_id=journey.attempt,
        current=True,
        status="complete",
    )
    session.add(test_suite)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        test_suite = session.exec(
            select(TestSuite).where(
                TestSuite.journey_id == journey.id,
                TestSuite.generation_run_id == journey.attempt,
            )
        ).one()
    return test_suite


def save_recording_sync(
    *,
    application_id: uuid.UUID,
    discovery_run_id: uuid.UUID,
    code: str,
    steps: list[str],
    requires_auth: bool,
    name: str,
) -> SavedRecording:
    """Assembles and writes the full row chain for one finished recording —
    the only entry point this module exposes. `code` is Codegen's own raw
    output file content — `apply_auth_tag` is applied here, not by the
    caller, so it's never possible to persist a `TestAsset.code` whose
    `@auth`/`@public` tag disagrees with `requires_auth`. `name` is the
    human-provided name from the idle screen (`RecordingSession.name`) —
    never a generic placeholder."""
    with Session(engine) as session:
        journey = get_or_create_recorded_tests_journey_sync(
            session, application_id=application_id, discovery_run_id=discovery_run_id
        )
        test_suite = ensure_test_suite_sync(session, journey)
        test_case_number = _claim_test_case_number_sync(session, application_id)

        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name=name,
            steps=steps,
            expected_result="",
            test_data=[],
            generation_run_id=journey.attempt,
            test_case_number=test_case_number,
            current=True,
            source="recorded",
        )
        session.add(scenario)
        session.flush()

        test_asset = TestAsset(
            scenario_id=scenario.id,
            test_suite_id=test_suite.id,
            code=apply_auth_tag(code, requires_auth),
            current=True,
            requires_auth=requires_auth,
            status="ready",
            warnings=[],
            primary_page_id=None,
        )
        session.add(test_asset)
        session.commit()
        session.refresh(journey)
        session.refresh(scenario)

        return SavedRecording(
            journey_external_id=journey.external_id,
            scenario_external_id=scenario.external_id,
            test_case_number=test_case_number,
        )


def create_recording_discovery_run_sync(application_id: uuid.UUID) -> uuid.UUID:
    """A recorded Journey still needs *some* `DiscoveryRun` row — that FK is
    not nullable (AD-8) — mirroring `source="live_exploration"`'s own
    precedent (`materialize_live_flow_sync`) with `source="recorded"`
    instead. No Page/Action/PageTransition rows are created alongside it —
    unlike a live-exploration session, a Codegen recording has no structured
    action trace to derive an application-model fragment from, only the
    final source file (which is `TestAsset.code` itself; see steps_parser's
    own docstring for the same reasoning applied to `Scenario.steps`).

    One per Application, reused by every recording (the "Recorded tests"
    Journey only ever points at one), rather than a fresh row per session."""
    with Session(engine) as session:
        existing = session.exec(
            select(DiscoveryRun)
            .where(DiscoveryRun.application_id == application_id, DiscoveryRun.source == "recorded")
            .order_by(DiscoveryRun.created_at)  # type: ignore[arg-type]
        ).first()
        if existing is not None:
            return existing.id
        discovery_run = DiscoveryRun(
            application_id=application_id,
            status="complete",
            source="recorded",
        )
        session.add(discovery_run)
        session.commit()
        session.refresh(discovery_run)
        return discovery_run.id
