"""Stage 8 — Explorer feeds Vantage (PLAN.md §9).

When Explorer finishes, its results land automatically in the existing
Journeys / Scenarios / Test cases, so Test runs, Schedules, CI and Download
work unchanged:
- one Journey per business area, its steps the screens Explorer understood
  (each a Page with its screenshot, as the Journeys tab expects);
- one Scenario per proven (or known-bug) scenario, carrying everything the
  test-case generator needs to get it right first time: the exact recorded
  actions (as `grounding.captured_flow`, the generator's own live-flow
  shape), whether sign-in is needed, and the on-screen proof of success.
Writing the test code is Vantage's job, not Explorer's: "Generate test
cases" on the Scenarios tab turns these into Test cases.
Re-running Explorer replaces its own earlier results the way regeneration
does elsewhere in Vantage: older rows stay (test history points at them)
but are no longer `current`.
"""

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from domain import (
    Application,
    Component,
    ComponentLocator,
    DiscoveryRun,
    Form,
    FormField,
    Journey,
    JourneyStep,
    Page,
    Scenario,
    TestAsset,
    TestSuite,
)
from domain.login_fields import is_saved_credential_value
from explorer_core import ExplorerRun, ExplorerScreen, ExplorerShot, ExplorerTestCase
from object_store import ObjectStore
from sqlalchemy import update
from sqlmodel import Session, col, select

from explorer_worker.db import engine
from explorer_worker.journal import Journal
from explorer_worker.missions import one_at_a_time
from explorer_worker.session import needs_sign_in

MAX_STEPS = 12
# Vantage's scenario types: positive flows vs. rule/error checks.
_SCENARIO_TYPE = {
    "navigation": "happy",
    "data_load": "happy",
    "form_submission": "happy",
    "validation": "negative",
    "error_state": "negative",
    "page_quality": "negative",
    "journey": "happy",
}


def identity_key(business_thing: str) -> str:
    """Explorer's journeys are recognisable (and replaceable) by this key."""
    return "explorer:" + (
        re.sub(r"[^a-z0-9]+", "-", business_thing.lower()).strip("-") or "general"
    )


def _claim_number(session: Session, application_id: uuid.UUID) -> int:
    return session.execute(
        update(Application)
        .where(col(Application.id) == application_id)
        .values(next_test_case_number=Application.next_test_case_number + 1)
        .returning(Application.next_test_case_number - 1)  # type: ignore[arg-type,call-overload]
    ).scalar_one()


async def promote(run_id: uuid.UUID) -> dict[str, int]:
    return await asyncio.to_thread(_promote, run_id)


def _promote(run_id: uuid.UUID) -> dict[str, int]:
    journal = Journal(run_id)
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None:
            return {}
        application = session.get(Application, run.application_id)
        if application is None:
            return {}
        tests = session.exec(
            select(ExplorerTestCase)
            .where(
                ExplorerTestCase.run_id == run_id,
                # Only what works: a possible bug never becomes a test case.
                # It turns into one when you say "Not a bug" (it is then proven).
                ExplorerTestCase.status == "proven",
            )
            .order_by(col(ExplorerTestCase.created_at))
        ).all()
        if not tests:
            journal.event(
                "thought", "Nothing to send to Journeys yet", "No proven test cases in this run."
            )
            return {"journeys": 0, "scenarios": 0}
        screens = [
            s
            for s in session.exec(
                select(ExplorerScreen)
                .where(ExplorerScreen.run_id == run_id)
                .order_by(col(ExplorerScreen.created_at))
            ).all()
            if not (s.condition or "").startswith("Simulated")
        ]
        requires_auth = needs_sign_in(
            application.auth_method, application.secret_ref, application.requires_login
        )
        # Same per-login-state check Explorer uses for its own missions; the
        # test runner reads it to run these tests one at a time.
        shared_state = one_at_a_time(session, run_id)

        # The discovery record Journeys hang off: the one onboarding created.
        discovery_run = session.exec(
            select(DiscoveryRun)
            .where(DiscoveryRun.application_id == application.id, DiscoveryRun.source == "crawler")
            .order_by(col(DiscoveryRun.created_at).desc())
        ).first()
        if discovery_run is None:
            discovery_run = DiscoveryRun(
                application_id=application.id, status="running", stage="explorer"
            )
            session.add(discovery_run)
            session.flush()

        # One Journey per screen, named after it: as scenarios multiply, each
        # stays with the screen it tests.
        groups: dict[str, list[ExplorerTestCase]] = {}
        for test in tests:
            # A whole-flow scenario is a Journey of its own, named after the task.
            key = test.title if test.kind == "journey" else test.start_screen or "General"
            groups.setdefault(key, []).append(test)
        purposes = {s.name.lower(): s.purpose or "" for s in screens}

        store: ObjectStore | None
        try:
            store = ObjectStore()
        except Exception:
            store = None
        page_for_screen: dict[uuid.UUID, uuid.UUID] = {}
        scenarios = 0
        for thing, group in groups.items():
            journey = session.exec(
                select(Journey).where(
                    Journey.application_id == application.id,
                    Journey.identity_key == identity_key(thing),
                )
            ).first()
            if journey is None:
                journey = Journey(
                    application_id=application.id,
                    discovery_run_id=discovery_run.id,
                    name=thing,
                    identity_key=identity_key(thing),
                    attempt=1,
                )
            else:
                journey.attempt += 1
                journey.discovery_run_id = discovery_run.id
                _retire(session, journey.id)
                for step in session.exec(
                    select(JourneyStep).where(JourneyStep.journey_id == journey.id)
                ).all():
                    session.delete(step)
            journey.description = (
                purposes.get(thing.lower()) or f"{thing}: explored and proven by Vantage Explorer."
            )
            journey.status = "candidate"
            journey.generation_error = None
            session.add(journey)
            session.flush()

            # Step: the screen itself, as a Page with its screenshot.
            area = [s for s in screens if s.name.lower() == thing.lower()][:1] or screens[:1]
            for order, screen in enumerate(area[:MAX_STEPS], start=1):
                page_id = page_for_screen.get(screen.id)
                if page_id is None:
                    key = None
                    if store is not None and screen.shot_id is not None:
                        shot = session.get(ExplorerShot, screen.shot_id)
                        if shot is not None:
                            try:
                                key = store.put(
                                    shot.data, discovery_run.id, content_type="image/jpeg"
                                )
                            except Exception:
                                key = None
                    page = Page(
                        application_id=application.id,
                        discovery_run_id=discovery_run.id,
                        url=screen.url,
                        title=screen.name,
                        heading=screen.name,
                        object_storage_key=key,
                    )
                    session.add(page)
                    session.flush()
                    page_id = page_for_screen[screen.id] = page.id
                    _persist_screen_model(session, application.id, discovery_run.id, page, screen)
                session.add(
                    JourneyStep(
                        journey_id=journey.id,
                        page_id=page_id,
                        step_order=order,
                        stage_label=screen.name[:120],
                    )
                )

            for test in group:
                scenario = Scenario(
                    journey_id=journey.id,
                    type=_SCENARIO_TYPE.get(test.kind, "happy"),
                    name=test.title,
                    steps=route_steps(test.script) or list(test.steps),
                    expected_result=test.expected + _proof_sentence(test.check),
                    test_data=_test_data(test.script),
                    generation_run_id=journey.attempt,
                    test_case_number=_claim_number(session, application.id),
                    safety_classification="SAFE",
                    source="discovery",
                    grounding={
                        "explorer_test": str(test.external_id),
                        "kind": test.kind,
                        "proven": True,
                        # Sign-in tests start signed out (their own session).
                        "requires_auth": requires_auth
                        and not (test.script and test.script[0].get("signed_out")),
                        "check": test.check,
                        "captured_flow": captured_flow(test.script),
                        # The house-style test Explorer already proved in the
                        # app. Generate tests uses it as the test case when it
                        # compiles (same tag/lint/persist pipeline as any
                        # generated test) instead of having the AI rewrite it.
                        "proven_code": test.code,
                        "one_at_a_time": shared_state,
                    },
                )
                session.add(scenario)
                scenarios += 1

        # Areas an earlier run promoted but this run has nothing proven for
        # keep stale tests otherwise: retire them too.
        promoted = {identity_key(thing) for thing in groups}
        for journey in session.exec(
            select(Journey).where(Journey.application_id == application.id)
        ).all():
            if journey.identity_key in promoted:
                continue
            if any(
                (old.grounding or {}).get("explorer_test")
                for old in session.exec(
                    select(Scenario).where(Scenario.journey_id == journey.id)
                ).all()
            ):
                _retire(session, journey.id)
                journey.status = "retired"  # out of every "candidate" list and count
                session.add(journey)

        discovery_run.status = "complete"
        discovery_run.stage = "analyzed"
        session.add(discovery_run)
        session.commit()
    journal.event(
        "summary",
        f"{scenarios} scenarios ready to become tests",
        "Press “Generate tests” on Explorer's Scenarios tab to turn them into tests.",
    )
    return {"journeys": len(groups), "scenarios": scenarios}


def _retire(session: Session, journey_id: uuid.UUID) -> None:
    """Mark a journey's scenarios, suites and test code as no longer current."""
    for older in session.exec(select(Scenario).where(Scenario.journey_id == journey_id)).all():
        older.current = False
        session.add(older)
    for older_suite in session.exec(
        select(TestSuite).where(TestSuite.journey_id == journey_id)
    ).all():
        older_suite.current = False
        session.add(older_suite)
        # Retire the old code too: a current asset under a retired
        # scenario breaks the Test cases list.
        for older_asset in session.exec(
            select(TestAsset).where(TestAsset.test_suite_id == older_suite.id)
        ).all():
            older_asset.current = False
            session.add(older_asset)


def route_steps(script: list[dict[str, Any]] | None) -> list[str]:
    """The test's steps as a person reads them: every action its proven code
    takes, in order, from opening the app to the last press — so a test deep
    in a wizard shows the whole route to its screen, not only its last
    screen's purpose. Saved logins stay placeholders, never the secret."""
    steps: list[str] = []
    for step in script or []:
        action = step.get("do")
        if action == "goto":
            text = f"Open {step.get('url')}"
        elif action == "fill":
            value = str(step.get("value") or "")
            shown = {"{{username}}": "the saved username", "{{password}}": "the saved password"}
            value = shown.get(value.strip().lower(), f"“{value}”") if value.strip() else "nothing"
            text = f"Enter {value} in “{step.get('field')}”"
        elif action == "choose":
            field = step.get("field")
            text = f"Choose “{step.get('option')}”" + (f" for “{field}”" if field else "")
        elif action == "click":
            text = f"Press “{step.get('label')}”"
        elif action == "upload":
            field = step.get("field")
            text = f"Attach a sample {step.get('kind') or 'image'} file" + (
                f" to “{field}”" if field else ""
            )
        elif action in ("back", "reload"):
            text = f"Press the browser's {'Back' if action == 'back' else 'Refresh'} button"
        else:
            continue
        # Screens that only show sometimes (a saved-draft prompt) are optional.
        if step.get("optional"):
            text = f"If it's shown: {text[0].lower()}{text[1:]}"
        steps.append(text)
    return steps


def _py_locator(step: dict[str, Any]) -> str | None:
    """The locator Explorer actually used on this step (browser.locate), in
    the generator's own `get_by_*` form — so a fallback generation finds the
    same element too, never a re-guess from the step's words."""
    spec = step.get("locator")
    if not spec:
        return None
    by, q, exact = spec.get("by"), json.dumps, bool(spec.get("exact"))
    if by == "role":
        return f"get_by_role({q(spec['role'])}, name={q(spec['name'])}, exact={exact})"
    if by in ("label", "select_label"):
        return f"get_by_label({q(spec['text'])}, exact={exact})"
    if by == "placeholder":
        return f"get_by_placeholder({q(spec['text'])})"
    if by == "text":
        return f"get_by_text({q(spec['text'])}, exact={exact})"
    if by == "css":
        return f"locator({q(spec['selector'])})"
    return None


def captured_flow(script: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Explorer's recorded actions in the shape Vantage's generator already
    reads from live exploration (`live_action_sequence`: tool_name, value as
    a Playwright locator, element_description, semantic_target). Generic: it
    only uses what a person reads on screen, as Explorer found it."""
    flow: list[dict[str, Any]] = []
    for step in script:
        action = step.get("do")
        if action == "goto":
            flow.append(
                {
                    "tool_name": "browser_navigate",
                    "element_tag": "page",
                    "value": str(step["url"]),
                    "element_description": "Open this address",
                }
            )
        elif action == "fill":
            field, value = str(step.get("field")), str(step.get("value"))
            flow.append(
                {
                    "tool_name": "browser_type",
                    "element_tag": "textbox",
                    "value": _py_locator(step) or f"get_by_label({json.dumps(field)})",
                    "element_description": f"The “{field}” field",
                    "semantic_target": {
                        "action": "fill",
                        "target": {"name": field},
                        "value": value,
                    },
                }
            )
        elif action == "choose":
            option, field = str(step.get("option")), str(step.get("field") or "")
            flow.append(
                {
                    "tool_name": "browser_click",
                    "element_tag": "option",
                    "value": _py_locator(step) or f"get_by_text({json.dumps(option)}, exact=True)",
                    "element_description": f"The “{option}” answer"
                    + (f" to “{field}”" if field else ""),
                    "semantic_target": {"action": "choose", "target": {"name": option}},
                }
            )
        elif action == "click":
            label = str(step.get("label"))
            flow.append(
                {
                    "tool_name": "browser_click",
                    "element_tag": "button",
                    "value": _py_locator(step)
                    or f'get_by_role("button", name={json.dumps(label)})',
                    "element_description": f"The “{label}” button or link",
                    "semantic_target": {"action": "click", "target": {"name": label}},
                }
            )
        elif action == "upload":
            # ponytail: described for Vantage's generator, which has no upload
            # step of its own yet; it writes the setInputFiles call from this.
            # Teach the generator a real file-upload step to make it exact.
            field = str(step.get("field") or "the upload area")
            kind = str(step.get("kind") or "image")
            flow.append(
                {
                    "tool_name": "browser_file_upload",
                    "element_tag": "input",
                    "value": 'locator("input[type=file]")',
                    "element_description": f"Attach a sample {kind} file to “{field}”",
                    "semantic_target": {
                        "action": "upload",
                        "target": {"name": field},
                        "value": kind,
                    },
                }
            )
        elif action in ("back", "reload"):
            flow.append(
                {
                    "tool_name": "browser_navigate_back" if action == "back" else "browser_reload",
                    "element_tag": "page",
                    "value": "page.goBack()" if action == "back" else "page.reload()",
                    "element_description": "Press the browser's "
                    + ("Back" if action == "back" else "Refresh")
                    + " button",
                }
            )
    return flow


# Field type (Explorer's reading) -> the ARIA role Playwright finds it by.
_FIELD_ROLE = {
    "select": "combobox",
    "checkbox": "checkbox",
    "radio": "radio",
    "number": "spinbutton",
}


def _persist_screen_model(
    session: Session,
    application_id: uuid.UUID,
    discovery_run_id: uuid.UUID,
    page: Page,
    screen: ExplorerScreen,
) -> None:
    """What self-healing reads about a page, in the shape the classic
    crawler writes it: each button/link as a Component with a role locator
    (plus a text fallback), and the fields as one Form whose FormFields carry
    their input type and required flag. Persist only: nothing in Explorer
    reads these back."""
    fields = [f for f in screen.fields or [] if isinstance(f, dict) and f.get("label")]
    if fields:
        form = Form(
            application_id=application_id,
            discovery_run_id=discovery_run_id,
            page_id=page.id,
            action_url=screen.url,
            method="POST",
        )
        session.add(form)
        session.flush()
        for field in fields:
            label, kind = str(field["label"])[:200], str(field.get("type") or "text")
            selector = f'get_by_role("{_FIELD_ROLE.get(kind, "textbox")}", name="{_q(label)}")'
            component = _component(session, application_id, page.id, label, kind, "fill", selector)
            component.form_id = form.id
            session.add(
                FormField(
                    form_id=form.id,
                    name=label,
                    input_type=kind,
                    required=bool(field.get("required")),
                    captured_selector=selector,
                    component_id=component.id,
                )
            )
    seen: set[str] = set()
    for action in screen.actions or []:
        label = str(action.get("label") or "").strip() if isinstance(action, dict) else ""
        # A bare "Icon" names nothing a locator can find.
        if not label or label.lower() == "icon" or label in seen:
            continue
        seen.add(label)
        role = "link" if action.get("kind") == "navigate" else "button"
        component = _component(
            session, application_id, page.id, label[:200], role, "click",
            f'get_by_role("{role}", name="{_q(label)}")',
        )
        session.add(
            ComponentLocator(
                component_id=component.id,
                kind="fallback",
                strategy="text",
                value=f'text="{_q(label)}"',
                priority=1,
                durability_score=2,
            )
        )


def _q(label: str) -> str:
    """A label quoted inside a locator string."""
    return label.replace("\\", "\\\\").replace('"', '\\"')


def _component(
    session: Session,
    application_id: uuid.UUID,
    page_id: uuid.UUID,
    name: str,
    type_: str,
    action: str,
    selector: str,
) -> Component:
    component = Component(
        application_id=application_id, page_id=page_id, name=name, type=type_, action=action
    )
    session.add(component)
    session.flush()
    session.add(
        ComponentLocator(
            component_id=component.id,
            kind="preferred",
            strategy="role",
            value=selector,
            priority=0,
            durability_score=1,
        )
    )
    return component


def _proof_sentence(check: dict[str, Any] | None) -> str:
    """How the test proves it passed, as Explorer saw it on screen."""
    if not check or not check.get("value"):
        return ""
    if check.get("kind") == "url_contains":
        return f" Proof of success: the address contains “{check['value']}”."
    return f" Proof of success: the screen shows “{check['value']}”."


def _test_data(script: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # A fill of the saved username/password is the login, not test data:
    # marked so it's never shown to the user or the AI (`domain.login_fields`).
    return [
        {
            "name": str(step.get("field")),
            "mandatory": True,
            "value": str(step.get("value")),
            **({"login": True} if is_saved_credential_value(step.get("value")) else {}),
        }
        for step in script
        if step.get("do") == "fill"
    ][:20]


def mark_discovery_running(application_id: uuid.UUID) -> None:
    """Used when a run starts: the Journeys tab shows discovery as running."""
    with Session(engine) as session:
        run = session.exec(
            select(DiscoveryRun)
            .where(DiscoveryRun.application_id == application_id, DiscoveryRun.source == "crawler")
            .order_by(col(DiscoveryRun.created_at).desc())
        ).first()
        if run is not None and run.status != "running":
            run.status, run.stage = "running", "explorer"
            run.created_at = run.created_at or datetime.now(UTC)
            session.add(run)
            session.commit()
