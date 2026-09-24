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

Confirmed during planning: `TestSuite` is one-per-Journey (DB-constrained
`(journey_id, generation_run_id)`, not `application_id`) — creating a fresh
Journey and its own fresh TestSuite here is exactly what the discovery and
live-exploration pipelines already do; the Suite tab's "one test suite per
application" is a UI/API-layer aggregation across every Journey's own
TestSuite, not a single row to find-or-reuse.
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


def _create_recording_journey_sync(
    session: Session, *, application_id: uuid.UUID, discovery_run_id: uuid.UUID
) -> Journey:
    existing_names = [
        j.name
        for j in session.exec(select(Journey).where(Journey.application_id == application_id)).all()
    ]
    base_name = "Recorded flow"
    name = base_name
    n = 2
    existing_lower = {e.lower() for e in existing_names}
    while name.lower() in existing_lower:
        name = f"{base_name} ({n})"
        n += 1

    # Unlike a crawl/live-exploration Journey, there is no underlying
    # evidence shape (pages visited, form fields) to fingerprint — each
    # recording session is already a distinct, deliberate human act, so its
    # own random session id is a perfectly good identity key; it only needs
    # to be unique per Application, same as every other Journey's.
    identity_key = hashlib.sha256(f"recording:{uuid.uuid4()}".encode()).hexdigest()

    journey = Journey(
        application_id=application_id,
        discovery_run_id=discovery_run_id,
        name=name,
        description="Recorded via Record and Play",
        identity_key=identity_key,
        attempt=1,
        captured_flow=None,
    )
    session.add(journey)
    try:
        session.flush()
    except IntegrityError:  # pragma: no cover - astronomically unlikely random collision
        session.rollback()
        journey = session.exec(
            select(Journey).where(
                Journey.application_id == application_id, Journey.identity_key == identity_key
            )
        ).one()
    return journey


def _ensure_test_suite_sync(session: Session, journey: Journey) -> TestSuite:
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
        session.flush()
    except IntegrityError:
        session.rollback()
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
) -> SavedRecording:
    """Assembles and writes the full row chain for one finished recording —
    the only entry point this module exposes. `code` is Codegen's own raw
    output file content — `apply_auth_tag` is applied here, not by the
    caller, so it's never possible to persist a `TestAsset.code` whose
    `@auth`/`@public` tag disagrees with `requires_auth`."""
    with Session(engine) as session:
        journey = _create_recording_journey_sync(
            session, application_id=application_id, discovery_run_id=discovery_run_id
        )
        test_suite = _ensure_test_suite_sync(session, journey)
        test_case_number = _claim_test_case_number_sync(session, application_id)

        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name=journey.name,
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
    own docstring for the same reasoning applied to `Scenario.steps`)."""
    with Session(engine) as session:
        discovery_run = DiscoveryRun(
            application_id=application_id,
            status="complete",
            source="recorded",
        )
        session.add(discovery_run)
        session.commit()
        session.refresh(discovery_run)
        return discovery_run.id
