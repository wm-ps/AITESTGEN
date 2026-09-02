"""AnalyzePromptActivity / IdentifyScenariosActivity / CreateJourneyActivity /
CreateScenarioActivity — NLM "Add Test Case" feature.

Reads/writes only the existing `journey`/`journey_step`/`scenario`/
`test_data_entry` tables (explicit product decision: no new table backs this
feature's own request state — see `AddTestCaseWorkflow`'s own docstring).
`EnsureTestSuiteActivity`/`PlaywrightGenerationActivity` (this same package's
`activities.py`) are reused unmodified by the workflow for the rest of the
pipeline — nothing here duplicates them.

A single prompt can decompose into several Scenarios (Multiple Test Cases):
`IdentifyScenariosActivity` does that decomposition once; `CreateJourneyActivity`
creates a brand-new Journey exactly once per distinct group of Scenarios that
share one (planned holistically, not once per Scenario — see
`AddTestCaseWorkflow`'s own docstring on why); `CreateScenarioActivity` then
only ever handles `reuse_scenario`/`new_scenario` — by the time it runs, every
Scenario's `journey_id` is already resolved to a real Journey.

Test data is never asked of the user: `CreateScenarioActivity` resolves each
required field from user-supplied data first (mandatory, always wins), then
the existing Test Data Pool, and leaves anything still unresolved for
`PlaywrightGenerationActivity`'s own existing default-value synthesis
(`_resolve_scenario_defaults_sync`) to fill in — exactly how every
normal-flow Scenario already gets its test data.

Every DB-only helper below runs in `asyncio.to_thread(...)`, and no DB session
is ever held open across an `await` of an AI call — same convention (and same
reasoning) as `ensure_test_suite_activity`/`playwright_generation_activity` in
this package's `activities.py`.
"""

import asyncio
import hashlib
import json
import logging
import re
import uuid

from ai_provider.hosted import HostedAIProvider
from ai_provider.journey_plan_candidate import JourneyPlanCandidate
from ai_provider.scenario_candidate import ScenarioCandidate
from ai_provider.scenario_match_candidate import ScenarioMatchCandidate
from ai_provider.test_case_prompt_candidate import TestCasePromptCandidate
from domain import (
    Application,
    DiscoveryRun,
    Journey,
    JourneyStep,
    Page,
    Scenario,
    TestAsset,
    TestDataEntry,
)
from safety_classifier import classify_scenario_steps
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from temporalio import activity
from workflows import (
    AnalyzePromptActivityInput,
    CreateJourneyActivityInput,
    CreateJourneyActivityResult,
    CreateScenarioActivityInput,
    CreateScenarioResult,
    IdentifyScenariosActivityInput,
    PromptAnalysisResult,
    ScenarioRequirement,
)

from generation_worker.activities import (
    _is_existing_credential_field,
    resolve_known_application_model_sync,
)
from generation_worker.db import engine

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _normalize_label(text: str) -> str:
    return "-".join(sorted(_WORD_RE.findall(text.lower())))


def _lookup(name: str, mapping: dict[str, str]) -> str | None:
    target = _normalize_label(name)
    for key, value in mapping.items():
        if value and _normalize_label(key) == target:
            return value
    return None


def _dedupe_name(base: str, existing: list[str]) -> str:
    """Duplicate Prevention for a name with no DB uniqueness constraint
    behind it (`Scenario.name`, and a non-crawl `Journey.name` — see
    `journey.py`'s own docstring on why `identity_key`, not `name`, is what's
    actually unique). Case-insensitive; appends " (2)", " (3)", ... on a
    collision instead of silently creating a same-named duplicate."""
    base = (base or "Untitled test case").strip() or "Untitled test case"
    existing_lower = {e.strip().lower() for e in existing}
    if base.lower() not in existing_lower:
        return base
    n = 2
    while f"{base} ({n})".lower() in existing_lower:
        n += 1
    return f"{base} ({n})"


def _to_prompt_candidate(result: PromptAnalysisResult) -> TestCasePromptCandidate:
    return TestCasePromptCandidate(
        is_relevant=result.is_relevant,
        functionality_summary=result.functionality_summary,
        actions=result.actions,
        expected_result=result.expected_result,
        rejection_reason=result.rejection_reason,
        provided_test_data=result.provided_test_data,
    )


def _requirement_to_prompt_candidate(requirement: ScenarioRequirement) -> TestCasePromptCandidate:
    """One Scenario's own description — distinct from `_to_prompt_candidate`,
    which converts the *overall* prompt understanding. A single request can
    decompose into several Scenarios, each generated from its own
    functionality/actions/expected_result, never the whole original request
    repeated for every one of them."""
    return TestCasePromptCandidate(
        is_relevant=True,
        functionality_summary=requirement.functionality_summary,
        actions=requirement.actions,
        expected_result=requirement.expected_result,
    )


@activity.defn(name="AnalyzePromptActivity")
async def analyze_prompt_activity(input: AnalyzePromptActivityInput) -> PromptAnalysisResult:
    candidate = await HostedAIProvider().analyze_test_case_prompt(input.prompt)
    return PromptAnalysisResult(
        is_relevant=candidate.is_relevant,
        functionality_summary=candidate.functionality_summary,
        actions=candidate.actions,
        expected_result=candidate.expected_result,
        rejection_reason=candidate.rejection_reason,
        provided_test_data=candidate.provided_test_data,
    )


def _load_journeys_with_scenarios_sync(application_id: str) -> list[dict]:
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(application_id))
        ).one()
        journeys = session.exec(
            select(Journey).where(
                Journey.application_id == application.id, Journey.status == "candidate"
            )
        ).all()
        journey_ids = [j.id for j in journeys]
        scenarios = (
            session.exec(
                select(Scenario).where(
                    Scenario.journey_id.in_(journey_ids),  # type: ignore[attr-defined]
                    Scenario.current.is_(True),  # type: ignore[attr-defined]
                )
            ).all()
            if journey_ids
            else []
        )
        scenarios_by_journey: dict[uuid.UUID, list[Scenario]] = {}
        for scenario in scenarios:
            scenarios_by_journey.setdefault(scenario.journey_id, []).append(scenario)

        return [
            {
                "journey_id": str(journey.external_id),
                "name": journey.name,
                "description": journey.description or "",
                "scenarios": [
                    {
                        "scenario_id": str(s.external_id),
                        "name": s.name,
                        "type": s.type,
                        "expected_result": s.expected_result,
                    }
                    for s in scenarios_by_journey.get(journey.id, [])
                ],
            }
            for journey in journeys
        ]


def _build_scenario_requirements(
    candidates: list[ScenarioMatchCandidate], journeys_with_scenarios: list[dict]
) -> list[ScenarioRequirement]:
    """Pure — no I/O — so this is independently unit-testable without
    mocking the DB or the AI provider (`test_identify_scenarios_activity.py`
    exercises the Duplicate Prevention fix below directly)."""
    # Hallucination guard — the AI's own `mode`/id combination is only
    # trusted once checked against what was actually offered to it (same
    # spirit as `InferenceActivity`'s `page_index` bounds check).
    valid_journey_ids = {j["journey_id"] for j in journeys_with_scenarios}
    valid_scenario_ids = {
        s["scenario_id"] for j in journeys_with_scenarios for s in j["scenarios"]
    }

    # `[FIXED]` Deterministic Duplicate Prevention — observed live: two
    # separate NLM requests (submitted minutes apart, not concurrently) both
    # ended up creating their own "Calculate loan EMI" Scenario, because
    # `match_test_case_scenarios`' own semantic judgment on `reuse_scenario`
    # is best-effort and simply didn't recognize the second request as
    # matching the first request's already-created Scenario. This is *not*
    # scoped to the Journey the AI happened to pick for either request — an
    # exact (normalized) name match against ANY existing Scenario in the
    # Application always overrides the AI's own new_scenario/new_journey
    # choice below, closing the gap its semantic matching can miss. Word-
    # order/case/punctuation-insensitive (`_normalize_label`, same helper
    # `_dedupe_name`'s own collision check uses) — not a fuzzy/semantic
    # matcher, deliberately, so this stays predictable: a real wording
    # difference between two prompts still creates two Scenarios, only an
    # exact-content match is caught here.
    existing_by_name: dict[str, tuple[str, str]] = {}
    for journey in journeys_with_scenarios:
        for scenario in journey["scenarios"]:
            existing_by_name.setdefault(
                _normalize_label(scenario["name"]), (journey["journey_id"], scenario["scenario_id"])
            )

    # Duplicate Prevention within this same batch — the AI can propose the
    # same reused Scenario twice, or two "new" entries for what's really one
    # Scenario under the same (existing-or-proposed) Journey; only the first
    # of each survives.
    seen_reuse: set[str] = set()
    seen_new_names: set[str] = set()

    requirements: list[ScenarioRequirement] = []
    for candidate in candidates:
        mode = candidate.mode
        journey_id = candidate.journey_id
        scenario_id = candidate.scenario_id
        if mode in ("reuse_scenario", "new_scenario") and journey_id not in valid_journey_ids:
            mode, journey_id, scenario_id = "new_journey", None, None
        if mode == "reuse_scenario" and scenario_id not in valid_scenario_ids:
            mode, scenario_id = "new_scenario", None

        name_key = _normalize_label(candidate.proposed_scenario_name or "")
        if mode != "reuse_scenario" and name_key and name_key in existing_by_name:
            mode = "reuse_scenario"
            journey_id, scenario_id = existing_by_name[name_key]

        if mode == "reuse_scenario":
            if scenario_id in seen_reuse:
                continue
            seen_reuse.add(scenario_id)  # type: ignore[arg-type]
        else:
            if name_key and name_key in seen_new_names:
                # An earlier requirement in this same batch already claims
                # this exact name for a new Scenario — that one will create
                # it, this one would otherwise be an exact duplicate of a
                # Scenario that doesn't exist yet.
                continue
            seen_new_names.add(name_key)

        requirements.append(
            ScenarioRequirement(
                mode=mode,
                journey_id=journey_id,
                scenario_id=scenario_id,
                proposed_journey_name=candidate.proposed_journey_name,
                proposed_capability_name=candidate.proposed_capability_name,
                proposed_scenario_name=candidate.proposed_scenario_name,
                functionality_summary=candidate.functionality_summary,
                actions=candidate.actions,
                expected_result=candidate.expected_result,
                rationale=candidate.rationale,
            )
        )
    return requirements


@activity.defn(name="IdentifyScenariosActivity")
async def identify_scenarios_activity(
    input: IdentifyScenariosActivityInput,
) -> list[ScenarioRequirement]:
    journeys_with_scenarios = await asyncio.to_thread(
        _load_journeys_with_scenarios_sync, input.application_id
    )
    candidates = await HostedAIProvider().match_test_case_scenarios(
        input.prompt, _to_prompt_candidate(input.prompt_analysis), journeys_with_scenarios
    )
    return _build_scenario_requirements(candidates, journeys_with_scenarios)


def _resolve_test_data_values(
    field_names: list[str], user_provided_data: dict[str, str], pool: dict[str, str]
) -> dict[str, str]:
    """Test Data Priority: user-provided always wins when present (mandatory,
    per the request — never overridden); the existing Test Data Pool is
    checked next. Anything still unresolved is simply left out — never
    invented here (No Data Invention) — `PlaywrightGenerationActivity`'s own
    existing `_resolve_scenario_defaults_sync` synthesizes a sensible default
    for it later, exactly as it already does for every normal-flow Scenario.
    No "ask the user" step: matches how Test Suite generation already works."""
    resolved: dict[str, str] = {}
    for name in field_names:
        value = _lookup(name, user_provided_data) or _lookup(name, pool)
        if value:
            resolved[name] = value
    return resolved


def _load_test_data_pool_sync(application_id: str) -> dict[str, str]:
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(application_id))
        ).one()
        entries = session.exec(
            select(TestDataEntry).where(TestDataEntry.application_id == application.id)
        ).all()
        # ponytail: matched by label word-overlap, not `TestDataEntry`'s real
        # `normalized_key` (`aggregation_key(name, input_type, route_family)`,
        # see `key_normalization.py`) — this ad hoc, single-field request has
        # no captured input_type/route_family to compute a real aggregation
        # key with before a page is even chosen. A fuller version would
        # derive those once `CreateScenarioActivity` knows the field's
        # eventual page/component, the same way `_resolve_scenario_defaults_sync`
        # does for the normal generation flow, and match on the real key.
        # Secret-ref-only entries (`value is None`) are skipped — there's no
        # safe way to inline a Vault-backed value as plain scenario test data.
        return {entry.label: entry.value for entry in entries if entry.value}


def _reuse_scenario_sync(
    input: CreateScenarioActivityInput, pool: dict[str, str]
) -> CreateScenarioResult:
    with Session(engine) as session:
        scenario = session.exec(
            select(Scenario).where(Scenario.external_id == uuid.UUID(input.requirement.scenario_id))
        ).one()
        journey = session.get(Journey, scenario.journey_id)
        assert journey is not None

        updated = [dict(f) for f in scenario.test_data]
        changed = False
        for field_dict in updated:
            if not field_dict.get("value"):
                # Test Data Priority: user-provided first, then the existing
                # Test Data Pool — never invented, never asked of the user.
                value = _lookup(field_dict["name"], input.user_provided_data) or _lookup(
                    field_dict["name"], pool
                )
                if value:
                    field_dict["value"] = value
                    changed = True
        if changed:
            scenario.test_data = updated
            session.add(scenario)
            session.commit()
            session.refresh(scenario)

        # Duplicate Prevention / "already exists" fast path — a reused
        # Scenario very often already has a current TestAsset (it was
        # matched precisely because it already covers this request). When it
        # does, the workflow skips PlaywrightGenerationActivity and
        # execution entirely instead of redundantly regenerating/re-running
        # an already-attached test case.
        existing_asset = session.exec(
            select(TestAsset).where(
                TestAsset.scenario_id == scenario.id,
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).first()

        return CreateScenarioResult(
            journey_id=str(journey.external_id),
            scenario_id=str(scenario.external_id),
            journey_name=journey.name,
            scenario_name=scenario.name,
            existing_test_asset_id=str(existing_asset.external_id) if existing_asset else None,
        )


def _load_existing_journey_context_sync(
    journey_external_id: str,
) -> tuple[Journey, list[dict[str, str]], list[str]]:
    with Session(engine) as session:
        journey = session.exec(
            select(Journey).where(Journey.external_id == uuid.UUID(journey_external_id))
        ).one()
        known_pages, _known_locators, _primary_page_id, _known_page_ids = (
            resolve_known_application_model_sync(session, journey.id)
        )
        existing_scenarios = session.exec(
            select(Scenario).where(
                Scenario.journey_id == journey.id,
                Scenario.current.is_(True),  # type: ignore[attr-defined]
            )
        ).all()
        return journey, known_pages, [s.name for s in existing_scenarios]


def _load_new_journey_context_sync(
    application_id: str,
) -> tuple[Application, list[Page], list[str]]:
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(application_id))
        ).one()
        # ponytail: pages are handed to `plan_new_journey` bare — no
        # forms/components/api_endpoints attached the way `InferenceActivity`
        # attaches them before `infer_journeys` (`_describe_page` tolerates
        # their absence via `getattr(..., [])`). A fuller version would
        # attach the same transient context so page selection for a
        # brand-new Journey is as richly grounded as the original crawl-time
        # inference is.
        pages = list(session.exec(select(Page).where(Page.application_id == application.id)).all())
        existing_journeys = session.exec(
            select(Journey).where(
                Journey.application_id == application.id, Journey.status == "candidate"
            )
        ).all()
        return application, pages, [j.name for j in existing_journeys]


def _create_journey_sync(
    application: Application,
    pages: list[Page],
    plan: JourneyPlanCandidate,
    existing_journey_names: list[str],
    proposed_journey_name: str | None,
    description: str,
) -> Journey:
    pages_by_id = {p.id: p for p in pages}
    with Session(engine) as session:
        # `Journey.discovery_run_id` is NOT NULL and immutable once set
        # (journey.py) — an NLM-created Journey isn't tied to a fresh crawl,
        # so it's anchored to the Application's most recent DiscoveryRun,
        # the most representative snapshot of what Discovery actually
        # captured, rather than adding a nullable-FK schema change.
        discovery_run = session.exec(
            select(DiscoveryRun)
            .where(DiscoveryRun.application_id == application.id)
            .order_by(DiscoveryRun.created_at.desc())  # type: ignore[arg-type]
        ).first()
        if discovery_run is None:
            raise ValueError(
                "Application has no DiscoveryRun yet to anchor a new Journey to — "
                "run Discovery before adding a test case that needs a brand-new Journey."
            )

        name = _dedupe_name(proposed_journey_name or description, existing_journey_names)
        page_ids_in_plan = sorted(
            {step.page_id for step in plan.steps if uuid.UUID(step.page_id) in pages_by_id}
        )
        if not page_ids_in_plan:
            raise ValueError("plan_new_journey selected no valid pages for this request")
        # Deterministic fingerprint keeping `UNIQUE(application_id,
        # identity_key)` meaningful (journey.py) — hashes the chosen page
        # set + the request itself, never the AI-generated Journey `name`
        # (AD-13, same rule crawl-derived Journeys already follow). Computed
        # once per group (not per Scenario) so two Scenarios sharing one new
        # Journey hash to the exact same key.
        identity_key = hashlib.sha256(
            json.dumps({"pages": page_ids_in_plan, "prompt": description}, sort_keys=True).encode()
        ).hexdigest()

        journey = Journey(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            name=name,
            description=description,
            identity_key=identity_key,
            attempt=1,
        )
        session.add(journey)
        try:
            session.flush()
        except IntegrityError:
            # Lost the race to a concurrent identical request — reuse the
            # Journey the other call created, same pattern
            # `_ensure_test_suite_sync` already uses for `TestSuite`.
            session.rollback()
            journey = session.exec(
                select(Journey).where(
                    Journey.application_id == application.id,
                    Journey.identity_key == identity_key,
                )
            ).one()
            return journey

        for order, step in enumerate(plan.steps):
            page_uuid = uuid.UUID(step.page_id)
            if page_uuid not in pages_by_id:
                continue
            session.add(
                JourneyStep(
                    journey_id=journey.id,
                    page_id=page_uuid,
                    step_order=order,
                    stage_label=step.stage_label,
                )
            )
        session.commit()
        session.refresh(journey)
        return journey


@activity.defn(name="CreateJourneyActivity")
async def create_journey_activity(input: CreateJourneyActivityInput) -> CreateJourneyActivityResult:
    """Creates ONE brand-new Journey for a whole group of Scenarios that
    share it (New Journey grouping — see `AddTestCaseWorkflow`'s own
    docstring) — planning pages holistically from the combined
    functionality/actions across the group, not from just one Scenario's own
    narrow description."""
    application, pages, existing_journey_names = await asyncio.to_thread(
        _load_new_journey_context_sync, input.application_id
    )
    combined_summary = "; ".join(
        dict.fromkeys(
            r.functionality_summary for r in input.requirements if r.functionality_summary
        )
    )
    combined_actions = [a for r in input.requirements for a in r.actions]
    combined_candidate = TestCasePromptCandidate(
        is_relevant=True,
        functionality_summary=combined_summary,
        actions=combined_actions,
        expected_result="",
    )
    plan = await HostedAIProvider().plan_new_journey(combined_candidate, pages)
    proposed_name = input.requirements[0].proposed_journey_name
    journey = await asyncio.to_thread(
        _create_journey_sync,
        application,
        pages,
        plan,
        existing_journey_names,
        proposed_name,
        combined_summary,
    )
    return CreateJourneyActivityResult(
        journey_id=str(journey.external_id), journey_name=journey.name
    )


def _persist_new_scenario_sync(
    journey: Journey,
    candidate: ScenarioCandidate,
    scenario_name: str,
    resolved_test_data: dict[str, str],
) -> CreateScenarioResult:
    safety_classification, safety_classification_reason = classify_scenario_steps(candidate.steps)
    with Session(engine) as session:
        scenario = Scenario(
            journey_id=journey.id,
            type=candidate.type,
            name=scenario_name,
            steps=candidate.steps,
            expected_result=candidate.expected_result,
            # Same exclusion `scenario_generation_activity` applies to every
            # AI-proposed field (activities.py) — belt-and-suspenders with the
            # prompt's own instruction not to name one.
            test_data=[
                {"name": f.name, "mandatory": f.mandatory, "value": resolved_test_data.get(f.name)}
                for f in candidate.test_data
                if not _is_existing_credential_field(f.name)
            ],
            generation_run_id=journey.attempt,
            current=True,
            safety_classification=safety_classification,
            safety_classification_reason=safety_classification_reason,
            # NLM Test Case Label — every Scenario this activity creates is
            # genuinely new, ad hoc from a user's prompt (the `reuse_scenario`
            # branch never reaches here — see `_reuse_scenario_sync`, which
            # leaves an existing Scenario's `source` untouched).
            source="nlm",
        )
        session.add(scenario)
        session.commit()
        session.refresh(scenario)
        return CreateScenarioResult(
            journey_id=str(journey.external_id),
            scenario_id=str(scenario.external_id),
            journey_name=journey.name,
            scenario_name=scenario.name,
        )


@activity.defn(name="CreateScenarioActivity")
async def create_scenario_activity(input: CreateScenarioActivityInput) -> CreateScenarioResult:
    """Only ever handles `reuse_scenario`/`new_scenario` — a `new_journey`
    requirement is always rewritten to `new_scenario` (with a real
    `journey_id`) by `CreateJourneyActivity` before this ever runs, see
    `AddTestCaseWorkflow`'s own docstring."""
    pool = await asyncio.to_thread(_load_test_data_pool_sync, input.application_id)

    if input.requirement.mode == "reuse_scenario":
        return await asyncio.to_thread(_reuse_scenario_sync, input, pool)

    provider = HostedAIProvider()
    prompt_candidate = _requirement_to_prompt_candidate(input.requirement)
    journey, known_pages, existing_scenario_names = await asyncio.to_thread(
        _load_existing_journey_context_sync, input.requirement.journey_id
    )

    scenario_name = _dedupe_name(
        input.requirement.proposed_scenario_name or input.requirement.functionality_summary,
        existing_scenario_names,
    )
    # No test-data values are known yet at generation time — same order the
    # normal flow already uses (`generate_scenarios` names fields, values are
    # resolved afterward) — see `generate_scenario_from_prompt`'s own doc.
    candidate = await provider.generate_scenario_from_prompt(journey, prompt_candidate, known_pages)
    resolved = _resolve_test_data_values(
        [f.name for f in candidate.test_data], input.user_provided_data, pool
    )
    return await asyncio.to_thread(
        _persist_new_scenario_sync, journey, candidate, scenario_name, resolved
    )
