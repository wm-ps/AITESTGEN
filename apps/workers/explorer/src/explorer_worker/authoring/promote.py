"""The request's proven scenarios become test-case scenarios — ADDED next to
everything already there. Authoring's counterpart of explorer_worker.promote,
with three differences: one Journey per request (its own identity key, so it
never replaces Explorer's journeys or another request's), scenarios marked
`source="nl"` (Test cases → "Author test cases"), and a grounding key Explorer's
own hand-off doesn't look for, so a later Explorer run never retires them."""

import asyncio
import uuid
from collections.abc import Sequence

from domain import Application, DiscoveryRun, Journey, JourneyStep, Page, Scenario
from explorer_core import ExplorerRun, ExplorerScreen, ExplorerShot, ExplorerTestCase
from object_store import ObjectStore
from sqlmodel import Session, col, select

from explorer_worker.db import engine
from explorer_worker.journal import Journal
from explorer_worker.missions import one_at_a_time
from explorer_worker.promote import (
    _SCENARIO_TYPE,
    MAX_STEPS,
    _claim_number,
    _persist_screen_model,
    _proof_sentence,
    _retire,
    _test_data,
    captured_flow,
    route_steps,
)
from explorer_worker.session import needs_sign_in


def identity_key(run_external_id: object) -> str:
    return f"explorer-author:{run_external_id}"


async def promote(run_id: uuid.UUID) -> list[str]:
    """The external id of the Journey the scenarios were added to ([] when
    nothing was proven) — the workflow generates its test cases next."""
    return await asyncio.to_thread(_promote, run_id)


def _promote(run_id: uuid.UUID) -> list[str]:
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
            .where(ExplorerTestCase.run_id == run_id, ExplorerTestCase.status == "proven")
            .order_by(col(ExplorerTestCase.created_at))
        ).all()
        if not tests:
            journal.event(
                "thought", "No test cases to add", "None of the scenarios held up in the app."
            )
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
        name = str(request.get("title") or run.prompt or "Your request")[:200]
        journey = session.exec(
            select(Journey).where(
                Journey.application_id == application.id,
                Journey.identity_key == identity_key(run.external_id),
            )
        ).first()
        if journey is None:
            journey = Journey(
                application_id=application.id,
                discovery_run_id=discovery_run.id,
                name=name,
                identity_key=identity_key(run.external_id),
                attempt=1,
            )
        else:  # this same request again (after "Not a bug"): its own rows only
            journey.attempt += 1
            _retire(session, journey.id)
            for step in session.exec(
                select(JourneyStep).where(JourneyStep.journey_id == journey.id)
            ).all():
                session.delete(step)
        journey.description = (run.prompt or name)[:2000]
        journey.status = "candidate"
        journey.generation_error = None
        session.add(journey)
        session.flush()

        _add_steps(session, application.id, discovery_run.id, journey.id, run_id, tests)

        for test in tests:
            session.add(
                Scenario(
                    journey_id=journey.id,
                    type=_SCENARIO_TYPE.get(test.kind, "happy"),
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
                        "proven": True,
                        "requires_auth": requires_auth
                        and not (test.script and test.script[0].get("signed_out")),
                        "check": test.check,
                        "captured_flow": captured_flow(test.script),
                        "proven_code": test.code,
                        "one_at_a_time": shared_state,
                    },
                )
            )
        session.commit()
        journey_id = str(journey.external_id)
    journal.event(
        "summary",
        f"{len(tests)} scenarios added — writing their test cases",
        "They appear under Test cases → Author test cases when ready.",
    )
    return [journey_id]


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
