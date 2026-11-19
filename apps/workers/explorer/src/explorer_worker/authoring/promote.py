"""Every scenario the request planned that worked when tried in the app
becomes a test-case scenario, carrying its proven code — ADDED next to
everything already there. Authoring's counterpart of explorer_worker.promote,
with three differences: one Journey per request (its own identity key, so it
never replaces Explorer's journeys or another request's), scenarios marked
`source="nl"` (Test cases → "Author test cases"), and a grounding key Explorer's
own hand-off doesn't look for, so a later Explorer run never retires them.
A possible bug waits on the run's Scenarios tab, as in Explorer: "Not a bug"
adds it (promote with `only`), "Ignore" drops it."""

import asyncio
import uuid
from collections.abc import Sequence

from domain import (
    Application,
    DiscoveryRun,
    Journey,
    JourneyStep,
    Page,
    Scenario,
    TestAsset,
)
from explorer_core import ExplorerRun, ExplorerScreen, ExplorerShot, ExplorerTestCase
from object_store import ObjectStore
from sqlmodel import Session, col, select

from explorer_worker.db import engine
from explorer_worker.journal import Journal
from explorer_worker.missions import one_at_a_time
from explorer_worker.promote import (
    MAX_STEPS,
    _claim_number,
    _persist_screen_model,
    _proof_sentence,
    _retire,
    _test_data,
    captured_flow,
    route_steps,
    scenario_type,
)
from explorer_worker.session import needs_sign_in


def identity_key(run_external_id: object) -> str:
    return f"explorer-author:{run_external_id}"


async def promote(run_id: uuid.UUID, only: uuid.UUID | None = None) -> list[str]:
    """The external id of the Journey the scenarios were added to ([] when
    nothing was proven) — the workflow generates its test cases next.
    `only`: that one scenario, added next to what is already there."""
    return await asyncio.to_thread(_promote, run_id, only)


def _promote(run_id: uuid.UUID, only: uuid.UUID | None = None) -> list[str]:
    journal = Journal(run_id)
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None:
            return []
        application = session.get(Application, run.application_id)
        if application is None:
            return []
        tests = session.exec(
            select(ExplorerTestCase)
            .where(
                ExplorerTestCase.run_id == run_id,
                # Only what works: a possible bug waits for your answer.
                ExplorerTestCase.status == "proven",
                *([ExplorerTestCase.external_id == only] if only else []),
            )
            .order_by(col(ExplorerTestCase.created_at))
        ).all()
        if not tests:
            journal.event("thought", "No test cases to add", "No scenarios were written.")
            return []
        requires_auth = needs_sign_in(
            application.auth_method, application.secret_ref, application.requires_login
        )
        shared_state = one_at_a_time(session, run_id)
        discovery_run = session.exec(
            select(DiscoveryRun)
            .where(DiscoveryRun.application_id == application.id, DiscoveryRun.source == "crawler")
            .order_by(col(DiscoveryRun.created_at).desc())
        ).first()
        if discovery_run is None:
            discovery_run = DiscoveryRun(
                application_id=application.id, status="complete", stage="explorer"
            )
            session.add(discovery_run)
            session.flush()

        request = (run.brief or {}).get("request") or {}
        # The journey the user picked when starting (an existing one, or a
        # new one by name); none picked = the request's own journey.
        choice = (run.insights or {}).get("journey") or {}
        name = str(choice.get("name") or request.get("title") or run.prompt or "Your request")
        name = name[:200]
        picked = (
            session.exec(
                select(Journey).where(
                    Journey.application_id == application.id,
                    Journey.external_id == uuid.UUID(str(choice["id"])),
                )
            ).first()
            if choice.get("id")
            else None
        )
        journey = (
            picked
            or session.exec(
                select(Journey).where(
                    Journey.application_id == application.id,
                    Journey.identity_key == identity_key(run.external_id),
                )
            ).first()
        )
        if picked is not None:
            # Added to the user's journey: its own scenarios and steps stay;
            # only this request's earlier copies (sent again) are retired.
            _retire_own(session, picked.id, {str(t.external_id) for t in tests})
        elif journey is None:
            journey = Journey(
                application_id=application.id,
                discovery_run_id=discovery_run.id,
                name=name,
                identity_key=identity_key(run.external_id),
                attempt=1,
            )
        elif only is not None:
            pass  # one more scenario: everything already there stays
        else:  # this same request sent again: its own rows only
            journey.attempt += 1
            _retire(session, journey.id)
            for step in session.exec(
                select(JourneyStep).where(JourneyStep.journey_id == journey.id)
            ).all():
                session.delete(step)
        if picked is None:
            journey.description = (run.prompt or name)[:2000]
        journey.status = "candidate"
        journey.generation_error = None
        session.add(journey)
        session.flush()

        has_steps = session.exec(
            select(JourneyStep).where(JourneyStep.journey_id == journey.id)
        ).first()
        if has_steps is None:
            _add_steps(session, application.id, discovery_run.id, journey.id, run_id, tests)

        for test in tests:
            session.add(
                Scenario(
                    journey_id=journey.id,
                    type=scenario_type(test),
                    name=test.title,
                    steps=route_steps(test.script) or list(test.steps),
                    expected_result=test.expected + _proof_sentence(test.check),
                    test_data=_test_data(test.script),
                    generation_run_id=journey.attempt,
                    test_case_number=_claim_number(session, application.id),
                    safety_classification="SAFE",
                    source="nl",
                    grounding={
                        "authored_test": str(test.external_id),
                        "kind": test.kind,
                        # Not proven: written from its steps (no proven_code).
                        "proven": test.status == "proven",
                        "requires_auth": requires_auth
                        and not (test.script and test.script[0].get("signed_out")),
                        "check": test.check,
                        "captured_flow": captured_flow(test.script),
                        "proven_code": test.code,
                        "one_at_a_time": shared_state,
                    },
                )
            )
        first, count = tests[0].title, len(tests)  # read before the commit expires them
        session.commit()
        journey_id = str(journey.external_id)
    journal.event(
        "summary",
        f"Added to the test cases: {first}"
        if only
        else f"{count} scenarios added — writing their test cases",
        "They appear under Test cases → Author test cases when ready.",
    )
    return [journey_id]


def _retire_own(session: Session, journey_id: uuid.UUID, authored: set[str]) -> None:
    """Retire only this request's scenarios (and their test code) on a
    journey the user picked — never the journey's other scenarios."""
    for older in session.exec(select(Scenario).where(Scenario.journey_id == journey_id)).all():
        if str((older.grounding or {}).get("authored_test")) not in authored:
            continue
        older.current = False
        session.add(older)
        for asset in session.exec(select(TestAsset).where(TestAsset.scenario_id == older.id)):
            asset.current = False
            session.add(asset)


def _add_steps(
    session: Session,
    application_id: uuid.UUID,
    discovery_run_id: uuid.UUID,
    journey_id: uuid.UUID,
    run_id: uuid.UUID,
    tests: Sequence[ExplorerTestCase],
) -> None:
    """The journey's steps: the screens its scenarios start on, each a Page
    with its screenshot — as Explorer's hand-off does. Test-case writing reads
    "needs the app's login" (`grounding.requires_auth`) only for a journey
    with a step page; without one an authored test was tagged @public and ran
    signed out."""
    screens = session.exec(
        select(ExplorerScreen)
        .where(ExplorerScreen.run_id == run_id)
        .order_by(col(ExplorerScreen.created_at))
    ).all()
    by_name = {s.name: s for s in screens}
    wanted = list(dict.fromkeys(t.start_screen for t in tests if t.start_screen))
    area = [by_name[n] for n in wanted if n in by_name] or list(screens[:1])
    try:
        store: ObjectStore | None = ObjectStore()
    except Exception:  # noqa: BLE001 — a step without its screenshot still works
        store = None
    for order, screen in enumerate(area[:MAX_STEPS], start=1):
        key = None
        shot = session.get(ExplorerShot, screen.shot_id) if screen.shot_id else None
        if store is not None and shot is not None:
            try:
                key = store.put(shot.data, discovery_run_id, content_type="image/jpeg")
            except Exception:  # noqa: BLE001
                key = None
        page = Page(
            application_id=application_id,
            discovery_run_id=discovery_run_id,
            url=screen.url,
            title=screen.name,
            heading=screen.name,
            object_storage_key=key,
        )
        session.add(page)
        session.flush()
        _persist_screen_model(session, application_id, discovery_run_id, page, screen)
        session.add(
            JourneyStep(
                journey_id=journey_id,
                page_id=page.id,
                step_order=order,
                stage_label=screen.name[:120],
            )
        )
