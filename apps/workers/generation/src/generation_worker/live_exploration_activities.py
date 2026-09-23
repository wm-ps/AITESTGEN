"""LiveExploreActivity / LiveHealActivity — the Temporal activities backing
`LiveExplorationTestWorkflow`.

Registered on `LIVE_EXPLORATION_TASK_QUEUE` — heavy, spawn a Playwright MCP
subprocess — never `GENERATION_TASK_QUEUE`'s existing lightweight AI-only
activities' queue, so a live exploration in flight can't starve normal
scenario/code generation (see `worker.py`).
"""

import asyncio
import hashlib
import json
import logging
import uuid

from ai_provider.hosted import HostedAIProvider
from domain import (
    Application,
    Journey,
    JourneyStep,
    Page,
    Scenario,
    TestAsset,
    TestResult,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from temporalio import activity
from workflows import (
    AUTO_HEAL_ATTEMPT_CAP,
    LiveExploreActivityInput,
    LiveExploreActivityResult,
    LiveHealActivityInput,
    LiveHealActivityResult,
)

from generation_worker import spec_linter
from generation_worker.activities import _resolve_scenario_defaults_sync, supersede_test_asset
from generation_worker.db import engine
from generation_worker.live_exploration.agent import run_exploration
from generation_worker.live_exploration.auth_bootstrap import bootstrap_storage_state
from generation_worker.live_exploration.live_flow import LiveFlowModel
from generation_worker.live_exploration.materialize import materialize_live_flow_sync
from generation_worker.live_exploration.mcp_client import PlaywrightMCPClient
from generation_worker.typecheck import typecheck_playwright_code

logger = logging.getLogger(__name__)

_EXPLORE_MAX_TURNS = 30
_HEAL_MAX_TURNS = 10


def _load_application_sync(application_id: str) -> Application:
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(application_id))
        ).one()
        session.expunge(application)
        return application


def _captured_flow_from(live_flow: LiveFlowModel) -> list[dict]:
    """The literal, ordered transcript persisted onto `Journey.captured_flow`
    — grounds `ScenarioGenerationActivity` in what actually happened instead
    of the crawler-shaped Form/Component reinterpretation, which has no way
    to represent a plain navigation click. Also carries each step's resolved
    `locator_candidate` (when there is one) so `PlaywrightGenerationActivity`
    can pass the ordered sequence to `generate_playwright` the same way
    `LiveHealActivity` already does — an earlier entry (opening a dropdown/
    combobox) is very often a prerequisite the final target only becomes
    interactable after; a flat locator list alone silently drops that."""
    return [
        {
            "tool_name": step.tool_name,
            "element_description": step.tool_args.get("element"),
            "typed_value": step.tool_args.get("text") if step.tool_name == "browser_type" else None,
            "page_url": step.page_url,
            "page_heading": step.page_heading,
            "rationale": step.rationale,
            "semantic_target": step.semantic_target,
            **(step.locator_candidate or {}),
        }
        for step in live_flow.steps
    ]


def _create_live_journey_sync(
    *,
    application_id: uuid.UUID,
    discovery_run_id: uuid.UUID,
    page_ids: list[uuid.UUID],
    requirement: str,
    functionality_summary: str,
    captured_flow: list[dict],
) -> tuple[str, str]:
    with Session(engine) as session:
        existing_names = [
            j.name
            for j in session.exec(
                select(Journey).where(Journey.application_id == application_id)
            ).all()
        ]
        # A business-language summary (AnalyzePromptActivity) names the
        # Journey properly — falling back to a truncated first line only
        # when that's blank (e.g. a very short/atypical prompt).
        base_name = (
            functionality_summary.strip()
            or requirement.strip().splitlines()[0][:80]
            or "Untitled live journey"
        )
        name = base_name
        n = 2
        existing_lower = {e.lower() for e in existing_names}
        while name.lower() in existing_lower:
            name = f"{base_name} ({n})"
            n += 1

        identity_key = hashlib.sha256(
            json.dumps(
                {
                    "discovery_run_id": str(discovery_run_id),
                    "pages": [str(p) for p in page_ids],
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

        journey = Journey(
            application_id=application_id,
            discovery_run_id=discovery_run_id,
            name=name,
            description=requirement,
            identity_key=identity_key,
            attempt=1,
            captured_flow=captured_flow,
        )
        session.add(journey)
        try:
            session.flush()
        except IntegrityError:
            # Lost the race to a concurrent identical request (Temporal
            # at-least-once retry) — reuse what the other attempt created,
            # same pattern `_create_journey_sync`/`_ensure_test_suite_sync`
            # already use.
            session.rollback()
            journey = session.exec(
                select(Journey).where(
                    Journey.application_id == application_id, Journey.identity_key == identity_key
                )
            ).one()
            return str(journey.external_id), journey.name

        pages = {
            page.id: page
            for page in session.exec(select(Page).where(Page.id.in_(page_ids))).all()
        }
        for order, page_id in enumerate(page_ids):
            page = pages.get(page_id)
            session.add(
                JourneyStep(
                    journey_id=journey.id,
                    page_id=page_id,
                    step_order=order,
                    stage_label=(page.heading if page and page.heading else f"Step {order + 1}"),
                )
            )
        session.commit()
        session.refresh(journey)
        return str(journey.external_id), journey.name


@activity.defn(name="LiveExploreActivity")
async def live_explore_activity(input: LiveExploreActivityInput) -> LiveExploreActivityResult:
    application = await asyncio.to_thread(_load_application_sync, input.application_id)
    storage_state_path = await bootstrap_storage_state(application)
    try:
        async with PlaywrightMCPClient(storage_state_path=str(storage_state_path)) as mcp_client:
            live_flow = await run_exploration(
                mcp_client=mcp_client,
                ai_provider=HostedAIProvider(),
                requirement=input.requirement,
                start_url=application.url,
                max_turns=_EXPLORE_MAX_TURNS,
                heartbeat=activity.heartbeat,
                application_context=application.application_context,
            )
    finally:
        storage_state_path.unlink(missing_ok=True)

    result = await asyncio.to_thread(materialize_live_flow_sync, application.id, live_flow)
    logger.info(
        "LiveExploreActivity: application_id=%s requirement=%r goal_satisfied=%s pages=%d",
        input.application_id,
        input.requirement,
        live_flow.goal_satisfied,
        len(result.pages),
    )
    journey_id, journey_name = await asyncio.to_thread(
        _create_live_journey_sync,
        application_id=application.id,
        discovery_run_id=result.discovery_run_id,
        # Post-merge ids, not `result.pages`' own — a JourneyStep built from
        # the pre-merge id would find zero Components for a URL Discovery
        # already knew about (see `MaterializeResult.canonical_page_ids`).
        page_ids=result.canonical_page_ids,
        requirement=input.requirement,
        functionality_summary=input.functionality_summary,
        captured_flow=_captured_flow_from(live_flow),
    )
    return LiveExploreActivityResult(
        discovery_run_id=str(result.discovery_run_id),
        page_ids=[str(pid) for pid in result.canonical_page_ids],
        goal_satisfied=live_flow.goal_satisfied,
        journey_id=journey_id,
        journey_name=journey_name,
    )


def _load_heal_context_sync(
    test_result_id: str,
) -> tuple[Application, TestResult, TestAsset, int, str] | None:
    with Session(engine) as session:
        test_result = session.exec(
            select(TestResult).where(TestResult.external_id == uuid.UUID(test_result_id))
        ).one()
        test_asset = session.get(TestAsset, test_result.test_asset_id)
        if test_asset is None:
            return None
        scenario = session.get(Scenario, test_asset.scenario_id)
        journey = session.get(Journey, scenario.journey_id) if scenario else None
        application = session.get(Application, journey.application_id) if journey else None
        if application is None or scenario is None:
            return None
        # `[FIXED]` This is the automatic heal path (no user clicked "Retry
        # with self-healing") — `TestResult.heal_attempt_count` was split
        # into `auto_heal_attempt_count`/`manual_heal_attempt_count`
        # (execution_worker/activities.py), each with its own cap; the
        # automatic one is the fixed `AUTO_HEAL_ATTEMPT_CAP`, never the
        # admin-configurable `DiscoverySettings.max_heal_attempts` (that
        # governs only the manual path).
        max_heal_attempts = AUTO_HEAL_ATTEMPT_CAP
        # `[FIXED]` `test_asset.scenario_id` is the internal PK (used above
        # via `session.get`, which takes a PK) — `_resolve_scenario_defaults_sync`
        # (generation_worker/activities.py) needs the *external* id instead,
        # captured here while the session is still open rather than passing
        # the internal one and crashing with NoResultFound.
        scenario_external_id = str(scenario.external_id)
        session.expunge(test_result)
        session.expunge(test_asset)
        session.expunge(application)
        return application, test_result, test_asset, max_heal_attempts, scenario_external_id


def _supersede_heal_result_sync(
    test_asset_id: uuid.UUID,
    test_result_id: uuid.UUID,
    *,
    code: str,
    requires_auth: bool,
    warnings: list[str],
    primary_page_id: uuid.UUID | None,
) -> str:
    with Session(engine) as session:
        prior = session.get(TestAsset, test_asset_id)
        assert prior is not None
        new_asset = supersede_test_asset(
            session,
            prior,
            code=code,
            requires_auth=requires_auth,
            warnings=warnings,
            status="needs_review",
            primary_page_id=primary_page_id,
        )
        test_result = session.get(TestResult, test_result_id)
        assert test_result is not None
        test_result.auto_heal_attempt_count += 1
        test_result.healed_test_asset_id = new_asset.id
        session.add(test_result)
        session.commit()
        session.refresh(new_asset)
        return str(new_asset.external_id)


@activity.defn(name="LiveHealActivity")
async def live_heal_activity(input: LiveHealActivityInput) -> LiveHealActivityResult:
    context = await asyncio.to_thread(_load_heal_context_sync, input.test_result_id)
    if context is None or context[0] is None:
        logger.warning(
            "LiveHealActivity: could not resolve heal context for %s", input.test_result_id
        )
        return LiveHealActivityResult(healed=False, test_asset_id="")

    application, test_result, test_asset, max_heal_attempts, scenario_external_id = context
    if test_result.auto_heal_attempt_count >= max_heal_attempts:
        logger.info(
            "LiveHealActivity: test_result_id=%s already at max_heal_attempts=%d, skipping",
            input.test_result_id,
            max_heal_attempts,
        )
        return LiveHealActivityResult(healed=False, test_asset_id=str(test_asset.external_id))

    (
        scenario,
        known_pages,
        known_locators,
        _required_fields,
        _field_input_types,
        requires_auth,
        primary_page_id,
        _captured_flow,
        # Unused here — `application` above (from `_load_heal_context_sync`)
        # is the same row and already in scope, so `application.
        # application_context` is used directly below instead of this one.
        _application_context,
    ) = await asyncio.to_thread(_resolve_scenario_defaults_sync, scenario_external_id)

    goal = (
        f"The Playwright step(s) for scenario '{scenario.name}' failed with: "
        f"{test_result.error_message or 'unknown error'}. The scenario's steps are: "
        f"{'; '.join(scenario.steps)}."
    )

    storage_state_path = await bootstrap_storage_state(application)
    try:
        async with PlaywrightMCPClient(storage_state_path=str(storage_state_path)) as mcp_client:
            live_flow = await run_exploration(
                mcp_client=mcp_client,
                ai_provider=HostedAIProvider(),
                requirement=goal,
                # Same known-page fallback `execution_worker/activities.py`'s
                # own live-inspection heal path already uses — heal a step
                # from wherever the scenario's own flow actually reaches,
                # not always the bare application root.
                start_url=known_pages[-1]["url"] if known_pages else application.url,
                is_heal=True,
                max_turns=_HEAL_MAX_TURNS,
                heartbeat=activity.heartbeat,
                application_context=application.application_context,
            )
    finally:
        storage_state_path.unlink(missing_ok=True)

    if not live_flow.goal_satisfied or not live_flow.steps:
        logger.info(
            "LiveHealActivity: test_result_id=%s — live re-exploration did not converge",
            input.test_result_id,
        )
        return LiveHealActivityResult(healed=False, test_asset_id=str(test_asset.external_id))

    # The FULL ordered replay, not just the final target's locator — a step
    # earlier in this list is very often a prerequisite (opening a dropdown/
    # menu/tab) the final target only becomes interactable after. Passing
    # only the last step's locator (the original approach here) silently
    # dropped that prerequisite: the regenerated code got "here's the right
    # locator" with no signal that it must also replicate the interaction
    # that revealed it, so it kept failing on the exact same
    # not-visible-until-a-prior-action error the heal was meant to fix.
    # `element` (the decide-agent's own free-text account of what it acted
    # on, e.g. "Tenant dropdown in the Filters dialog") is the only evidence
    # that distinguishes two steps whose locator `value` is otherwise
    # identical — see the sibling comprehension in `activities.py`'s
    # `PlaywrightGenerationActivity` for the full rationale.
    action_sequence = [
        {
            "tool_name": step.tool_name,
            "element_description": step.tool_args.get("element"),
            "semantic_target": step.semantic_target,
            **step.locator_candidate,
        }
        for step in live_flow.steps
        if step.locator_candidate is not None
    ]
    if not action_sequence:
        return LiveHealActivityResult(healed=False, test_asset_id=str(test_asset.external_id))

    code = await HostedAIProvider().generate_playwright(
        scenario,
        known_pages,
        known_locators,
        requires_auth=requires_auth,
        previous_code=test_asset.code,
        failure_error_message=test_result.error_message,
        failure_stack_trace=test_result.stack_trace,
        failure_console_output=test_result.console_output,
        live_action_sequence=action_sequence,
        application_context=application.application_context,
    )
    typecheck_errors = await typecheck_playwright_code(code.code)
    if typecheck_errors:
        logger.warning(
            "LiveHealActivity: test_result_id=%s — healed candidate failed typecheck: %s",
            input.test_result_id,
            "; ".join(typecheck_errors),
        )
        return LiveHealActivityResult(healed=False, test_asset_id=str(test_asset.external_id))

    tagged_code = spec_linter.apply_auth_tag(code.code, requires_auth)
    new_test_asset_id = await asyncio.to_thread(
        _supersede_heal_result_sync,
        test_asset.id,
        test_result.id,
        code=tagged_code,
        requires_auth=requires_auth,
        warnings=["Healed via live re-exploration."],
        primary_page_id=primary_page_id,
    )
    return LiveHealActivityResult(healed=True, test_asset_id=new_test_asset_id)
