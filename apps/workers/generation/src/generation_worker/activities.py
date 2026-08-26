"""ScenarioGenerationActivity — Story 4.1's first real Activity dispatch.

Fetches a Journey's attributed canonical rows (via its `JourneyStep`s),
attaches the same kind of transient capture context `InferenceActivity`
attaches to Pages before calling the AI provider, and persists the returned
`ScenarioCandidate`s as `Scenario` rows. Idempotent under Temporal's
at-least-once retry (AD-9): if `Scenario` rows already exist for this
Journey's current `(journey_id, generation_run_id)` pair, returns them
without re-generating.

Each persisted `Scenario` also gets a `safety_classification` (Run All
Tests feature), via `safety_classifier.classify_scenario_steps` — the same
`classify()` `discovery_worker`'s live-crawl `safety_engine.evaluate()`
calls, aggregated across the Scenario's plain-language steps at generation
time, not `evaluate()` itself (there's no live-crawl "posture" to resolve
here; the policy-permission check for a non-`SAFE` classification happens
later, at execution time, via `ExecutionPolicy`).
"""

import asyncio
import logging
import re
import uuid

from ai_provider.hosted import HostedAIProvider
from domain import (
    ApiEndpoint,
    Application,
    Component,
    ComponentLocator,
    DiscoverySettings,
    Form,
    FormField,
    Journey,
    JourneyStep,
    Page,
    Scenario,
    TestAsset,
    TestSuite,
    ValidationRule,
)
from safety_classifier import classify_scenario_steps
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from temporalio import activity
from workflows import (
    EnsureTestSuiteActivityInput,
    EnsureTestSuiteActivityResult,
    FinalizeSuiteGenerationActivityInput,
    PlaywrightGenerationActivityInput,
    ScenarioGenerationActivityInput,
)

from generation_worker import spec_linter
from generation_worker.db import engine
from generation_worker.typecheck import typecheck_playwright_code

logger = logging.getLogger(__name__)

# Non-AI, deterministic default-value generator (Story 4.2) — mirrors
# discovery_worker/crawler.py's `_generic_value` convention: a field's
# reviewer-provided value always wins; a still-blank field gets a sensible
# placeholder matching its own name, never a value the AI invents (Story 4.1
# AC 5's "the AI never fills in `value`" rule extends to this generator too,
# since it's separate, non-AI code).
_EMAIL_FIELD_RE = re.compile(r"user|email|login", re.IGNORECASE)
_PASSWORD_FIELD_RE = re.compile(r"pass(word)?", re.IGNORECASE)
_CARD_FIELD_RE = re.compile(r"card", re.IGNORECASE)
# Same convention discovery_worker/crawler.py's `_generic_value` already uses
# for its own (different, exploratory-crawl) purpose: a field's declared
# HTML `type` isn't a reliable signal on its own (many real quantity boxes
# are `type="text"`), so it's only consulted here once the name-pattern
# checks above find nothing more specific — same precedence crawler.py
# itself uses.
_TYPE_CANDIDATES = {
    "number": ("1", "2", "3"),
    "tel": ("555-0100", "555-0101", "555-0102"),
    "date": ("2026-01-01", "2026-01-02", "2026-01-03"),
    "email": ("test@example.com", "test2@example.com", "test3@example.com"),
}
# Mirrors crawler.py's own `_QUANTITY_FIELD_RE` exactly (a quantity/amount
# box is routinely `type="text"` on real sites, so `input_type` alone
# already misses it) — same field-type-awareness gap, same fix.
_QUANTITY_FIELD_RE = re.compile(r"qty|quantity|count|amount|number", re.IGNORECASE)
# Every literal this generator (both the plain name/type defaults above and
# the scenario-intent defaults below) can ever produce — nothing else ever
# writes one of these exact strings into `test_data`, so a field holding one
# is safe to treat as "still effectively blank" and re-evaluate.
_KNOWN_GENERIC_PLACEHOLDERS = frozenset(
    {"Test value", "Test value 2", "Test value 3"}
    | {"Password1$", "Password2$", "Password3$"}
    | {"4111111111111111", "5555555555554444", "4000000000000002"}
    | {"test@example.com", "test2@example.com", "test3@example.com"}
    | {"1", "2", "3"}
    | {"555-0100", "555-0101", "555-0102"}
    | {"2026-01-01", "2026-01-02", "2026-01-03"}
)


def _default_test_data_value(
    field_name: str, used_values: set[str], input_type: str = "text"
) -> str:
    if _PASSWORD_FIELD_RE.search(field_name):
        candidates = ("Password1$", "Password2$", "Password3$")
    elif _CARD_FIELD_RE.search(field_name):
        candidates = ("4111111111111111", "5555555555554444", "4000000000000002")
    elif _EMAIL_FIELD_RE.search(field_name):
        candidates = ("test@example.com", "test2@example.com", "test3@example.com")
    elif input_type in _TYPE_CANDIDATES:
        candidates = _TYPE_CANDIDATES[input_type]
    elif _QUANTITY_FIELD_RE.search(field_name):
        candidates = ("1", "2", "3")
    else:
        candidates = ("Test value", "Test value 2", "Test value 3")
    # Checklist rule 6: a scenario whose whole point is "X and Y differ"
    # (confirm-mismatch, before/after) needs genuinely distinct literals —
    # reusing the same pattern-matched placeholder for every same-shaped
    # field (e.g. "password" and "confirmPassword" both -> "Password1$")
    # silently destroys that scenario.
    return next((c for c in candidates if c not in used_values), candidates[-1])


# Scenario-intent-driven defaults (Story: generation pipeline hardening,
# scenario-data-intent gap) — checked BEFORE `_default_test_data_value`
# above. That function only ever looks at a field's own name/type, so a
# Scenario whose own name/steps name a specific data property (a numeric
# boundary, Unicode/international content, markup characters, a password
# length/character-set boundary) gets the same generic "Test value"/
# "Password1$" a completely unrelated Scenario for the same field would —
# satisfying the field's shape while missing the property the Scenario's
# own title claims to test (e.g. "Sign in with a Unicode password" backed
# by a plain ASCII default). Returns `None` (falls through to the generic
# default above, unchanged) when nothing in `intent_text` names a property
# this specific field is a plausible target for.
_PASSWORD_UNICODE_INTENT_RE = re.compile(r"unicode|non-ascii|non ascii", re.IGNORECASE)
# Lookahead-based "both words present, any order/distance" — a real
# scenario name rarely puts "maximum" directly next to "length" (e.g.
# "Maximum supported profile name length", "Password at the maximum
# permitted length"), so a literal-adjacency pattern misses most of them.
_PASSWORD_MAX_LEN_INTENT_RE = re.compile(
    r"(?=.*\b(?:maximum|max)\b)(?=.*\blength\b)", re.IGNORECASE | re.DOTALL
)
_PASSWORD_MIN_LEN_INTENT_RE = re.compile(
    r"(?=.*\b(?:minimum|min)\b)(?=.*\blength\b)", re.IGNORECASE | re.DOTALL
)
_BELOW_MIN_INTENT_RE = re.compile(
    r"below the minimum|below minimum|under the minimum|less than the minimum", re.IGNORECASE
)
_ABOVE_MAX_INTENT_RE = re.compile(
    r"above the maximum|above maximum|exceed(?:s|ing)? the maximum|over the maximum",
    re.IGNORECASE,
)
_AT_MIN_INTENT_RE = re.compile(r"\bminimum\b|\bsmallest\b", re.IGNORECASE)
_AT_MAX_INTENT_RE = re.compile(r"\bmaximum\b|\blargest\b", re.IGNORECASE)
_DECIMAL_INTENT_RE = re.compile(r"decimal precision|\bdecimal\b", re.IGNORECASE)
_EMOJI_INTENT_RE = re.compile(r"\bemoji\b", re.IGNORECASE)
_UNICODE_INTENT_RE = re.compile(
    r"unicode|multilingual|international character|non-ascii|non ascii", re.IGNORECASE
)
_NAME_LIKE_FIELD_RE = re.compile(r"name", re.IGNORECASE)
_MARKUP_INTENT_RE = re.compile(r"markup|special character", re.IGNORECASE)
_MAX_LEN_INTENT_RE = re.compile(
    r"(?=.*\b(?:maximum|max)\b)(?=.*\blength\b)", re.IGNORECASE | re.DOTALL
)
_MIN_LEN_INTENT_RE = re.compile(
    r"(?=.*\b(?:minimum|min)\b)(?=.*\blength\b)", re.IGNORECASE | re.DOTALL
)


_CURRENT_PASSWORD_FIELD_RE = re.compile(r"current|old|existing", re.IGNORECASE)

# Deterministic backstop (credential-handling fix): the AI occasionally
# invents a test_data field for a login form's own username/password even
# though the system prompt tells it not to (see hosted.py's
# `_SCENARIO_PROMPT_SYSTEM`). Rather than trust the prompt alone, strip any
# field naming the account's OWN existing credential before persisting —
# that value must only ever come from the user-provided credential source
# (CREDENTIALS/fillCredentials), never an AI-generated placeholder. A
# "new"/"confirm"-qualified field (a change-password form's actual new
# value under test) is a legitimate candidate and is left alone. Deliberately
# does not touch bare "email"/"login" fields beyond this pattern — too many
# non-auth fields use those names.
_USERNAME_FIELD_RE = re.compile(r"\busername\b", re.IGNORECASE)
_NEW_OR_CONFIRM_QUALIFIER_RE = re.compile(r"\bnew\b|\bconfirm", re.IGNORECASE)


def _is_existing_credential_field(field_name: str) -> bool:
    if _NEW_OR_CONFIRM_QUALIFIER_RE.search(field_name):
        return False
    return bool(_USERNAME_FIELD_RE.search(field_name) or _PASSWORD_FIELD_RE.search(field_name))


# `[FIXED]` A "confirm X" field (confirm password, confirm new password, ...)
# used to get its value from the exact same distinct-by-design candidate
# cycling as any other same-shaped field (Checklist rule 6, above) — correct
# for a scenario whose whole point is that two fields DIFFER, but wrong for
# every ordinary scenario, which needs a confirm field to match its
# counterpart exactly or the form's own client-side "doesn't match"
# validation blocks the very outcome the scenario is testing for (e.g. a
# "successfully change password" Scenario silently getting an unusable
# new/confirm pair). Only overridden when the Scenario's own intent
# genuinely calls for a mismatch.
_CONFIRM_FIELD_RE = re.compile(r"\bconfirm(?:ation)?\b", re.IGNORECASE)
_MISMATCH_INTENT_RE = re.compile(
    r"mismatch|don'?t match|does(?:n'?t| not) match|\bdiffer(?:ent|ing|s)?\b", re.IGNORECASE
)


def _confirm_field_counterpart_name(field_name: str) -> str:
    """'confirm new password' -> 'new password'; 'confirm password' ->
    'password'."""
    return _CONFIRM_FIELD_RE.sub("", field_name).strip()


_NUMERIC_BOUNDARY_FIELD_EXCLUSION_RE = re.compile(r"name|subject|comment|holder", re.IGNORECASE)


_SI_PASSWORD_UNICODE = "Pässwörd123$"
_SI_PASSWORD_MAX_LEN = "P4ssw0rd$" + "x" * 119
_SI_PASSWORD_MIN_LEN = "Pw1$"
_SI_MAX_LEN = "x" * 128
_SI_MIN_LEN = "a"
_SI_EMOJI = "🚀😊"
_SI_UNICODE_NAME = "José García"
_SI_UNICODE_GENERIC = "こんにちは 你好 Pässwörd"
_SI_MARKUP = "<test>&\"'</test>"
_SI_BELOW_MIN = "0.00"
_SI_ABOVE_MAX = "1000000.00"
_SI_DECIMAL = "10000.50"
_SI_AT_MIN = "0.01"
_SI_AT_MAX = "999999.99"
# Every literal `_scenario_intent_default_value` below can ever produce —
# unioned into `_KNOWN_GENERIC_PLACEHOLDERS` above so a value from an
# earlier, less-refined pass of this same generator is re-eligible for
# re-evaluation too (not just the plain name/type defaults).
_SCENARIO_INTENT_PLACEHOLDERS = frozenset(
    {
        _SI_PASSWORD_UNICODE,
        _SI_PASSWORD_MAX_LEN,
        _SI_PASSWORD_MIN_LEN,
        _SI_MAX_LEN,
        _SI_MIN_LEN,
        _SI_EMOJI,
        _SI_UNICODE_NAME,
        _SI_UNICODE_GENERIC,
        _SI_MARKUP,
        _SI_BELOW_MIN,
        _SI_ABOVE_MAX,
        _SI_DECIMAL,
        _SI_AT_MIN,
        _SI_AT_MAX,
    }
)
_KNOWN_GENERIC_PLACEHOLDERS = _KNOWN_GENERIC_PLACEHOLDERS | _SCENARIO_INTENT_PLACEHOLDERS


def _password_category_value(text: str) -> str | None:
    if _PASSWORD_UNICODE_INTENT_RE.search(text):
        return _SI_PASSWORD_UNICODE
    if _PASSWORD_MAX_LEN_INTENT_RE.search(text):
        # No maxlength constraint is ever captured by Discovery today (only
        # `required`/`html5_message` — see ValidationRule) — this is a
        # best-effort long value, not a verified app-specific boundary.
        # Closing that gap for real needs a crawler change, out of scope.
        return _SI_PASSWORD_MAX_LEN
    if _PASSWORD_MIN_LEN_INTENT_RE.search(text):
        return _SI_PASSWORD_MIN_LEN
    return None


def _non_password_category_value(text: str, field_name: str) -> str | None:
    # Length-boundary checks before the bare minimum/maximum ones below —
    # "maximum ... length" always also contains the word "maximum", which
    # would otherwise swallow it as a numeric-amount boundary instead.
    if _MAX_LEN_INTENT_RE.search(text):
        return _SI_MAX_LEN
    if _MIN_LEN_INTENT_RE.search(text):
        return _SI_MIN_LEN
    if _EMOJI_INTENT_RE.search(text):
        return _SI_EMOJI
    if _UNICODE_INTENT_RE.search(text):
        return _SI_UNICODE_NAME if _NAME_LIKE_FIELD_RE.search(field_name) else _SI_UNICODE_GENERIC
    if _MARKUP_INTENT_RE.search(text):
        return _SI_MARKUP
    # Numeric-amount categories only ever apply to an amount-shaped field —
    # a scenario like "insurance purchase at the minimum permitted cover
    # amount" also has a "holder name" field that must NOT also get treated
    # as the amount under test just because the scenario mentions "minimum".
    if _NUMERIC_BOUNDARY_FIELD_EXCLUSION_RE.search(field_name):
        return None
    if _BELOW_MIN_INTENT_RE.search(text):
        return _SI_BELOW_MIN
    if _ABOVE_MAX_INTENT_RE.search(text):
        return _SI_ABOVE_MAX
    if _DECIMAL_INTENT_RE.search(text):
        return _SI_DECIMAL
    if _AT_MIN_INTENT_RE.search(text):
        return _SI_AT_MIN
    if _AT_MAX_INTENT_RE.search(text):
        return _SI_AT_MAX
    return None


def _scenario_intent_default_value(intent_text: str, field_name: str) -> str | None:
    """Returns a single, deterministic value when `intent_text` (the
    Scenario's own name + steps) or `field_name` itself names a property
    this field is a plausible target for, else `None`. `field_name` is
    checked FIRST, before the scenario-wide `intent_text` — a Scenario can
    cover more than one distinct property across different fields at once
    (e.g. "Profile containing boundary-length and Unicode details" has one
    field named for length, another for Unicode; each field's OWN name is
    the stronger, disambiguating signal for which property IT needs,
    falling back to the scenario-wide text only when the field's own name
    doesn't say).

    Deliberately not distinctness-checked against sibling fields the way
    `_default_test_data_value` is (Checklist rule 6) — these categories
    describe a property a boundary scenario needs EVERY relevant field to
    exhibit (a "new password"/"confirm password" pair must match exactly,
    three independent loan amount fields each just need to individually be
    "at the minimum"), not a scenario whose point is that two fields
    differ. A genuine mismatch scenario (e.g. "mismatched confirmation")
    never matches any category below, so it still falls through to
    `_default_test_data_value`'s existing distinct-by-design behavior."""
    if _PASSWORD_FIELD_RE.search(field_name):
        # The account's actual current password (a change-password form's
        # "current password" field) isn't the boundary/property under test
        # — it must stay the standard default so the form's own current-
        # password check succeeds; only the new/confirm fields get the
        # scenario-specific value below.
        if _CURRENT_PASSWORD_FIELD_RE.search(field_name):
            return None
        return _password_category_value(field_name) or _password_category_value(intent_text)

    if _CARD_FIELD_RE.search(field_name) or _EMAIL_FIELD_RE.search(field_name):
        return None  # the categories below are never about these fields

    return _non_password_category_value(field_name, field_name) or _non_password_category_value(
        intent_text, field_name
    )


@activity.defn(name="ScenarioGenerationActivity")
async def scenario_generation_activity(input: ScenarioGenerationActivityInput) -> list[str]:
    with Session(engine) as session:
        journey = session.exec(
            select(Journey).where(Journey.external_id == uuid.UUID(input.journey_id))
        ).one()

        existing = session.exec(
            select(Scenario).where(
                Scenario.journey_id == journey.id,
                Scenario.generation_run_id == journey.attempt,
            )
        ).all()
        if existing:
            logger.info(
                "ScenarioGenerationActivity: journey_id=%s already has %d scenarios, skipping",
                input.journey_id,
                len(existing),
            )
            return [str(s.external_id) for s in existing]

        logger.info("ScenarioGenerationActivity: journey_id=%s starting", input.journey_id)

        steps = list(
            session.exec(
                select(JourneyStep)
                .where(JourneyStep.journey_id == journey.id)
                .order_by(JourneyStep.step_order)  # type: ignore[arg-type]
            ).all()
        )

        # Every real JourneyStep today only ever sets page_id (Story 2.6's
        # InferenceActivity) — resolve generically anyway, same reasoning as
        # the Story 3.1 read endpoint: the schema allows all four target
        # types via its CHECK constraint.
        component_ids = {s.component_id for s in steps if s.component_id}
        components_by_id = {
            c.id: c
            for c in (
                session.exec(
                    select(Component).where(Component.id.in_(component_ids))  # type: ignore[attr-defined]
                ).all()
                if component_ids
                else []
            )
        }
        page_ids = {s.page_id for s in steps if s.page_id} | {
            c.page_id for c in components_by_id.values()
        }
        pages_by_id = {
            p.id: p
            for p in (
                session.exec(select(Page).where(Page.id.in_(page_ids))).all()  # type: ignore[attr-defined]
                if page_ids
                else []
            )
        }
        forms = list(
            session.exec(select(Form).where(Form.page_id.in_(page_ids))).all()  # type: ignore[attr-defined]
        ) if page_ids else []
        api_endpoints = list(
            session.exec(
                select(ApiEndpoint).where(ApiEndpoint.page_id.in_(page_ids))  # type: ignore[attr-defined]
            ).all()
        ) if page_ids else []
        form_ids = [f.id for f in forms]
        fields = list(
            session.exec(
                select(FormField).where(FormField.form_id.in_(form_ids))  # type: ignore[attr-defined]
            ).all()
        ) if form_ids else []
        field_ids = [f.id for f in fields]
        rules = list(
            session.exec(
                select(ValidationRule).where(
                    ValidationRule.form_field_id.in_(field_ids)  # type: ignore[attr-defined]
                )
            ).all()
        ) if field_ids else []
        rules_by_field: dict[uuid.UUID, list[ValidationRule]] = {}
        for rule in rules:
            rules_by_field.setdefault(rule.form_field_id, []).append(rule)
        fields_by_form: dict[uuid.UUID, list[FormField]] = {}
        for field_row in fields:
            fields_by_form.setdefault(field_row.form_id, []).append(field_row)

        forms_by_page: dict[uuid.UUID, list[Form]] = {}
        for form in forms:
            # Transient — same `object.__setattr__` technique as `.forms`/
            # `.api_endpoints` below, so `_describe_page` (ai_provider/hosted.py)
            # can show the LLM each field's actual captured validation rules
            # (rule_type + value) generically, instead of it having to guess
            # validation conditions from field names alone.
            object.__setattr__(
                form,
                "fields",
                [
                    {
                        "name": field_row.name,
                        "rules": [
                            {"rule_type": rule.rule_type, "value": rule.value}
                            for rule in rules_by_field.get(field_row.id, [])
                        ],
                    }
                    for field_row in fields_by_form.get(form.id, [])
                ],
            )
            forms_by_page.setdefault(form.page_id, []).append(form)
        api_by_page: dict[uuid.UUID, list[ApiEndpoint]] = {}
        for endpoint in api_endpoints:
            api_by_page.setdefault(endpoint.page_id, []).append(endpoint)

        ordered_pages: list[Page] = []
        for step in steps:
            page = pages_by_id.get(step.page_id) if step.page_id else None
            if page is None and step.component_id:
                component = components_by_id.get(step.component_id)
                page = pages_by_id.get(component.page_id) if component else None
            if page is None:
                continue
            # Transient attributes, same technique InferenceActivity uses —
            # SQLModel/Pydantic rejects direct attribute assignment for
            # undeclared fields.
            object.__setattr__(page, "forms", forms_by_page.get(page.id, []))
            object.__setattr__(page, "api_endpoints", api_by_page.get(page.id, []))
            object.__setattr__(page, "stage_label", step.stage_label)
            ordered_pages.append(page)

        settings = session.exec(select(DiscoverySettings)).one()
        candidates = await HostedAIProvider().generate_scenarios(
            journey, ordered_pages, limit=settings.max_scenarios_per_journey
        )

        scenario_external_ids: list[str] = []
        for candidate in candidates:
            safety_classification, safety_classification_reason = classify_scenario_steps(
                candidate.steps
            )
            scenario = Scenario(
                journey_id=journey.id,
                type=candidate.type,
                name=candidate.name,
                steps=candidate.steps,
                expected_result=candidate.expected_result,
                test_data=[
                    {"name": f.name, "mandatory": f.mandatory, "value": None}
                    for f in candidate.test_data
                    if not _is_existing_credential_field(f.name)
                ],
                generation_run_id=journey.attempt,
                current=True,
                safety_classification=safety_classification,
                safety_classification_reason=safety_classification_reason,
            )
            session.add(scenario)
            session.flush()
            scenario_external_ids.append(str(scenario.external_id))
            logger.info(
                "ScenarioGenerationActivity: journey_id=%s created scenario_id=%s name=%r",
                input.journey_id,
                scenario.external_id,
                scenario.name,
            )

        session.commit()
        logger.info(
            "ScenarioGenerationActivity: journey_id=%s generated %d scenarios",
            input.journey_id,
            len(scenario_external_ids),
        )
        return scenario_external_ids


@activity.defn(name="EnsureTestSuiteActivity")
async def ensure_test_suite_activity(
    input: EnsureTestSuiteActivityInput,
) -> EnsureTestSuiteActivityResult:
    """Idempotent insert-or-fetch of this Journey's current `TestSuite`, run
    once per `SuiteGenerationWorkflow` execution (before the per-Scenario
    fan-out) — so N concurrent `PlaywrightGenerationActivity` calls for the
    same Journey never race to create duplicate `TestSuite` rows. Also
    supersedes the prior attempt's `TestSuite`/`TestAsset` rows atomically
    with the new `TestSuite`'s creation, if `Journey.attempt` is ever bumped
    (no feature does this today — Story 4.3/FR-18 is cut in full, see
    sprint-change-proposal-2026-07-27.md).

    `[FIXED 2026-07-23]` The actual DB work runs in a thread
    (`asyncio.to_thread`) — a real Application's Generate Suite submission
    fans out one `SuiteGenerationWorkflow` per candidate Journey (a dozen or
    more isn't unusual) and each of those fans out one
    `PlaywrightGenerationActivity` per Scenario, so this worker process can
    have dozens of these Activities in flight at once, all sharing one
    event loop. A synchronous, blocking `Session`/`session.commit()` call
    made directly inside an `async def` (the original version of this
    function) freezes that *entire* event loop for its duration — with
    enough concurrent Activities doing this at once, observed live: every
    `TestSuite` got created (this function alone), but the fan-out froze
    solid before a single `TestAsset` was ever written, no crash, no
    timeout, just a silent stall. Exactly the same class of bug
    `discovery_worker`'s `_CaptureSink.add()` already fixed once for this
    codebase's other worker — reused here, not reinvented."""
    return await asyncio.to_thread(_ensure_test_suite_sync, input)


def _ensure_test_suite_sync(input: EnsureTestSuiteActivityInput) -> EnsureTestSuiteActivityResult:
    with Session(engine) as session:
        journey = session.exec(
            select(Journey).where(Journey.external_id == uuid.UUID(input.journey_id))
        ).one()

        existing = session.exec(
            select(TestSuite).where(
                TestSuite.journey_id == journey.id,
                TestSuite.generation_run_id == journey.attempt,
            )
        ).first()
        if existing is not None:
            test_suite = existing
        else:
            test_suite = TestSuite(
                journey_id=journey.id,
                name=f"{journey.name} Test Suite",
                generation_run_id=journey.attempt,
                current=True,
            )
            session.add(test_suite)
            try:
                session.flush()
            except IntegrityError:
                # Lost the race to a concurrent PlaywrightGenerationActivity
                # call for the same Journey/attempt — the unique constraint
                # (not just this select) is what actually prevents the
                # duplicate. Use the row the other call created.
                session.rollback()
                test_suite = session.exec(
                    select(TestSuite).where(
                        TestSuite.journey_id == journey.id,
                        TestSuite.generation_run_id == journey.attempt,
                    )
                ).one()
            else:
                # Atomic with the new TestSuite's creation: supersede the
                # immediately-prior current=true TestSuite (and its
                # TestAssets) for this Journey, in the same commit.
                prior = session.exec(
                    select(TestSuite).where(
                        TestSuite.journey_id == journey.id,
                        TestSuite.id != test_suite.id,
                        TestSuite.current.is_(True),  # type: ignore[attr-defined]
                    )
                ).first()
                if prior is not None:
                    prior.current = False
                    session.add(prior)
                    prior_assets = session.exec(
                        select(TestAsset).where(
                            TestAsset.test_suite_id == prior.id,
                            TestAsset.current.is_(True),  # type: ignore[attr-defined]
                        )
                    ).all()
                    for asset in prior_assets:
                        asset.current = False
                        session.add(asset)
                session.commit()
                session.refresh(test_suite)

        scenarios = session.exec(
            select(Scenario).where(
                Scenario.journey_id == journey.id,
                Scenario.current.is_(True),  # type: ignore[attr-defined]
            )
        ).all()

        logger.info(
            "EnsureTestSuiteActivity: journey_id=%s test_suite_id=%s (%d scenarios)",
            input.journey_id,
            test_suite.external_id,
            len(scenarios),
        )
        return EnsureTestSuiteActivityResult(
            test_suite_id=str(test_suite.external_id),
            scenario_ids=[str(s.external_id) for s in scenarios],
        )


@activity.defn(name="PlaywrightGenerationActivity")
async def playwright_generation_activity(input: PlaywrightGenerationActivityInput) -> str:
    """Converts one Scenario into one TestAsset. Idempotent under Temporal's
    at-least-once retry (AD-9): skips generating — and skips the AI call —
    if a `current=true` TestAsset already exists for this `scenario_id`.

    `[FIXED 2026-07-23]` Every DB step runs in a thread (`asyncio.to_thread`)
    and no DB session is held open across the `await` of the AI call — see
    `ensure_test_suite_activity`'s matching note for why: dozens of these
    can be in flight at once sharing one event loop, and a real AI call can
    take many seconds, so holding a session (and its checked-out connection)
    open for that whole span, on top of blocking the loop synchronously,
    compounds into the exact silent stall observed live (every `TestSuite`
    created, zero `TestAsset`s ever written)."""
    existing_id = await asyncio.to_thread(_existing_test_asset_id_sync, input.scenario_id)
    if existing_id is not None:
        logger.info(
            "PlaywrightGenerationActivity: scenario_id=%s already has a test asset, skipping",
            input.scenario_id,
        )
        return existing_id

    if await asyncio.to_thread(_test_case_limit_reached_sync, input.scenario_id):
        logger.warning(
            "PlaywrightGenerationActivity: max_test_cases_per_application reached — "
            "skipping scenario_id=%s",
            input.scenario_id,
        )
        return ""

    logger.info("PlaywrightGenerationActivity: scenario_id=%s starting", input.scenario_id)

    # Default test-data values, part of this same single flow (Story 4.2
    # AC 1) — never a second trigger. Reviewer-provided values always take
    # precedence; a still-blank field (mandatory or optional) gets a
    # field-name-pattern default, persisted back onto Scenario.test_data
    # before the AI call reads it.
    (
        scenario,
        known_pages,
        known_locators,
        required_fields,
        field_input_types,
        requires_auth,
        primary_page_id,
    ) = await asyncio.to_thread(_resolve_scenario_defaults_sync, input.scenario_id)

    provider = HostedAIProvider()
    repair = None
    # Checklist rule 3: a spec isn't "generated successfully" until it
    # compiles against real @playwright/test types — this catches
    # undefined-variable/hallucinated-matcher bugs at generation time
    # instead of at real-test-run time. A blind Temporal-level retry re-runs
    # this whole activity with zero memory of the previous tsc error, and
    # was observed live repeating the exact same string/number mistake
    # across all 3 attempts — so self-correct with the real compiler
    # feedback here first (up to 2 repair turns), and only let it fall
    # through to Temporal's outer retry (genuine infra failures) if the
    # model still can't fix it.
    for attempt in range(3):
        code = await provider.generate_playwright(
            scenario,
            known_pages,
            known_locators,
            requires_auth=requires_auth,
            field_input_types=field_input_types,
            repair=repair,
        )
        typecheck_errors = await typecheck_playwright_code(code.code)
        if not typecheck_errors:
            break
        logger.error(
            "PlaywrightGenerationActivity: scenario_id=%s failed typecheck (attempt %d): %s",
            input.scenario_id,
            attempt + 1,
            "; ".join(typecheck_errors),
        )
        repair = (code.code, typecheck_errors)
    else:
        raise ValueError(
            "Generated Playwright spec failed typecheck:\n" + "\n".join(typecheck_errors)
        )

    # Ground truth beats an LLM guess for the auth tag the same way it does
    # for locators (Story: generation pipeline hardening) — rewritten
    # deterministically here rather than trusted from the prompt alone.
    tagged_code = spec_linter.apply_auth_tag(code.code, requires_auth)

    test_asset_id = await asyncio.to_thread(
        _persist_test_asset_sync,
        input.scenario_id,
        input.test_suite_id,
        tagged_code,
        requires_auth,
        required_fields,
        known_locators,
        primary_page_id,
    )
    logger.info(
        "PlaywrightGenerationActivity: scenario_id=%s finished test_asset_id=%s",
        input.scenario_id,
        test_asset_id,
    )
    return test_asset_id


@activity.defn(name="FinalizeSuiteGenerationActivity")
async def finalize_suite_generation_activity(input: FinalizeSuiteGenerationActivityInput) -> None:
    await asyncio.to_thread(_finalize_suite_generation_sync, input)


def _finalize_suite_generation_sync(input: FinalizeSuiteGenerationActivityInput) -> None:
    with Session(engine) as session:
        test_suite = session.exec(
            select(TestSuite).where(TestSuite.external_id == uuid.UUID(input.test_suite_id))
        ).one()
        # A user may have already terminated this suite (or a prior Temporal
        # attempt of this same activity already ran) before this write lands
        # — 'terminated' is a stronger, user-made decision than the workflow's
        # own 'complete'/'incomplete' verdict and must never be overwritten.
        if test_suite.status == "terminated":
            logger.info(
                "FinalizeSuiteGenerationActivity: test_suite_id=%s already terminated, skipping",
                input.test_suite_id,
            )
            return
        test_suite.status = input.status
        session.add(test_suite)
        session.commit()
        logger.info(
            "FinalizeSuiteGenerationActivity: test_suite_id=%s finished status=%s",
            input.test_suite_id,
            input.status,
        )


def _existing_test_asset_id_sync(scenario_external_id: str) -> str | None:
    with Session(engine) as session:
        scenario = session.exec(
            select(Scenario).where(Scenario.external_id == uuid.UUID(scenario_external_id))
        ).one()
        existing = session.exec(
            select(TestAsset).where(
                TestAsset.scenario_id == scenario.id,
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).first()
        return str(existing.external_id) if existing is not None else None


def _test_case_limit_reached_sync(scenario_external_id: str) -> bool:
    with Session(engine) as session:
        settings = session.exec(select(DiscoverySettings)).one()
        if settings.max_test_cases_per_application is None:
            return False

        scenario = session.exec(
            select(Scenario).where(Scenario.external_id == uuid.UUID(scenario_external_id))
        ).one()
        journey = session.get(Journey, scenario.journey_id)
        assert journey is not None

        current_count = session.exec(
            select(func.count())
            .select_from(TestAsset)
            .join(Scenario, Scenario.id == TestAsset.scenario_id)  # type: ignore[arg-type]
            .join(Journey, Journey.id == Scenario.journey_id)  # type: ignore[arg-type]
            .where(
                Journey.application_id == journey.application_id,
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
        ).one()
        return current_count >= settings.max_test_cases_per_application


def resolve_known_application_model_sync(
    session: Session, journey_id: uuid.UUID
) -> tuple[list[dict[str, str]], list[dict[str, str]], uuid.UUID | None, list[uuid.UUID]]:
    """Grounds Playwright generation in what Discovery actually captured for
    this Journey, mirroring `scenario_generation_activity`'s own
    steps->components->pages resolution above (duplicated rather than
    shared — that function serves a different Activity and touching it for
    marginal reuse isn't worth the regression risk here).

    Not underscore-private despite the name — also called by
    `execution_worker`'s `HealTestActivity`, which needs the same known
    pages/locators a healed retry's `generate_playwright` call is grounded
    in as the original generation was.

    Returns `(known_pages, known_locators, primary_page_id, known_page_ids)`:
    - `known_pages`/`known_locators`: plain dicts (never ORM objects, so the
      result stays valid once this function's caller's session closes) —
      see below.
    - `known_pages`: one entry per distinct Page actually visited by this
      Journey's steps, in step order, `{"stage_label", "url"}` — a page
      revisited by a later step keeps its first stage_label.
    - `known_locators`: every Component on those same Pages (not just
      step-referenced ones — a real JourneyStep today only ever sets
      `page_id`, never `component_id`, so restricting to step-referenced
      Components would starve this of almost everything) that has at least
      one `ComponentLocator`, picking its `kind="preferred"` row if one
      exists, else the `kind="fallback"` row with the lowest `priority`
      (`discovery_worker/model_builder.py` assigns `priority` in
      already-durability-ranked order, so the lowest-priority fallback is
      always the most durable survivor).
    - `primary_page_id`: the first Page this Journey's steps visit — used
      for the requires_auth heuristic and for grouping sibling TestAssets
      (Story: generation pipeline hardening).
    - `known_page_ids`: every one of `known_pages`' Page ids, same order.
      `[FIXED]` A field's `required`/`input_type` metadata used to only ever
      be looked up on `primary_page_id` — the wrong page for any multi-page
      Journey (e.g. Dashboard -> a Loans page holding the actual form),
      which starves `_default_test_data_value`'s type-aware fallback for
      every field on the real target page. Callers needing that metadata
      should look it up across all of `known_page_ids`, not just the first."""
    steps = list(
        session.exec(
            select(JourneyStep)
            .where(JourneyStep.journey_id == journey_id)
            .order_by(JourneyStep.step_order)  # type: ignore[arg-type]
        ).all()
    )
    if not steps:
        return [], [], None, []

    component_ids = {s.component_id for s in steps if s.component_id}
    components_by_id = {
        c.id: c
        for c in (
            session.exec(
                select(Component).where(Component.id.in_(component_ids))  # type: ignore[attr-defined]
            ).all()
            if component_ids
            else []
        )
    }
    page_ids = {s.page_id for s in steps if s.page_id} | {
        c.page_id for c in components_by_id.values()
    }
    if not page_ids:
        return [], [], None, []

    pages_by_id = {
        p.id: p
        for p in session.exec(select(Page).where(Page.id.in_(page_ids))).all()  # type: ignore[attr-defined]
    }

    known_pages: list[dict[str, str]] = []
    stage_label_by_page_id: dict[uuid.UUID, str] = {}
    for step in steps:
        step_page_id = step.page_id
        if step_page_id is None and step.component_id:
            component = components_by_id.get(step.component_id)
            step_page_id = component.page_id if component else None
        if step_page_id is None or step_page_id not in pages_by_id:
            continue
        if step_page_id not in stage_label_by_page_id:
            stage_label_by_page_id[step_page_id] = step.stage_label
            known_pages.append(
                {"stage_label": step.stage_label, "url": pages_by_id[step_page_id].url}
            )
    # dict preserves insertion order — the first page a step actually
    # resolves to is this Journey's primary page; every key is every page
    # this Journey ever visits, in that same step order.
    known_page_ids = list(stage_label_by_page_id.keys())
    primary_page_id = next(iter(known_page_ids), None)

    all_components = list(
        session.exec(
            select(Component)
            .where(Component.page_id.in_(page_ids))  # type: ignore[attr-defined]
            .order_by(Component.name)  # deterministic prompt/test ordering
        ).all()
    )
    if not all_components:
        return known_pages, [], primary_page_id, known_page_ids

    locators = list(
        session.exec(
            select(ComponentLocator).where(
                ComponentLocator.component_id.in_(  # type: ignore[attr-defined]
                    [c.id for c in all_components]
                )
            )
        ).all()
    )
    locators_by_component: dict[uuid.UUID, list[ComponentLocator]] = {}
    for locator in locators:
        locators_by_component.setdefault(locator.component_id, []).append(locator)

    known_locators: list[dict[str, str]] = []
    for component in all_components:
        candidates = locators_by_component.get(component.id, [])
        preferred = next((loc for loc in candidates if loc.kind == "preferred"), None)
        fallbacks = [loc for loc in candidates if loc.kind == "fallback"]
        chosen = preferred or (min(fallbacks, key=lambda loc: loc.priority) if fallbacks else None)
        if chosen is None:
            continue
        known_locators.append(
            {
                "stage_label": stage_label_by_page_id.get(component.page_id, ""),
                "component_type": component.type,
                "component_name": component.name,
                "selector": chosen.value,
                "strategy": chosen.strategy,
            }
        )
    return known_pages, known_locators, primary_page_id, known_page_ids


_ScenarioDefaults = tuple[
    Scenario,
    list[dict[str, str]],
    list[dict[str, str]],
    dict[str, bool],
    dict[str, str],
    bool,
    uuid.UUID | None,
]


def _resolve_scenario_defaults_sync(scenario_external_id: str) -> _ScenarioDefaults:
    with Session(engine) as session:
        scenario = session.exec(
            select(Scenario).where(Scenario.external_id == uuid.UUID(scenario_external_id))
        ).one()

        (
            known_pages,
            known_locators,
            primary_page_id,
            known_page_ids,
        ) = resolve_known_application_model_sync(session, scenario.journey_id)

        required_fields: dict[str, bool] = {}
        field_input_types: dict[str, str] = {}
        requires_auth = False
        if primary_page_id is not None:
            required_fields = spec_linter.required_fields_for_pages(session, known_page_ids)
            field_input_types = spec_linter.field_input_types_for_pages(session, known_page_ids)
            journey = session.get(Journey, scenario.journey_id)
            application = session.get(Application, journey.application_id) if journey else None
            primary_page = session.get(Page, primary_page_id)
            if application is not None:
                requires_auth = spec_linter.resolve_requires_auth(
                    session, application, primary_page, scenario
                )

        intent_text = f"{scenario.name} {' '.join(scenario.steps)}"
        updated_fields = [dict(field) for field in scenario.test_data]
        changed = False
        # `[FIXED]` A field that was already auto-defaulted by a prior run
        # (before scenario-intent-awareness existed) is indistinguishable
        # here from one a reviewer deliberately typed — except that its
        # value is exactly one of this generator's own known placeholder
        # literals, which nothing else ever writes (the AI never fills in
        # `value`, and no reviewer types "Test value" as real data). Without
        # this, a still-broken field silently stays broken forever, since
        # `if not field.get("value")` below never re-triggers on the exact
        # same already-existing data this whole fix targets. Only these
        # exact literals are eligible for replacement — anything else a
        # reviewer actually entered is left completely untouched.
        used_values = {
            field["value"]
            for field in updated_fields
            if field.get("value") and field["value"] not in _KNOWN_GENERIC_PLACEHOLDERS
        }
        # Confirm-qualified fields are resolved in a second pass, below, so
        # their counterpart's own value has already settled by the time they
        # look it up.
        confirm_ids = {id(f) for f in updated_fields if _CONFIRM_FIELD_RE.search(f["name"])}
        confirm_fields = [f for f in updated_fields if id(f) in confirm_ids]
        other_fields = [f for f in updated_fields if id(f) not in confirm_ids]

        for field in other_fields:
            current_value = field.get("value")
            if not current_value or current_value in _KNOWN_GENERIC_PLACEHOLDERS:
                value = _scenario_intent_default_value(
                    intent_text, field["name"]
                ) or _default_test_data_value(
                    field["name"], used_values, field_input_types.get(field["name"], "text")
                )
                if value != current_value:
                    field["value"] = value
                    changed = True
                used_values.add(value)

        for field in confirm_fields:
            current_value = field.get("value")
            if not current_value or current_value in _KNOWN_GENERIC_PLACEHOLDERS:
                counterpart_name = _confirm_field_counterpart_name(field["name"]).lower()
                counterpart = next(
                    (f for f in other_fields if f["name"].strip().lower() == counterpart_name),
                    None,
                )
                if counterpart is not None and not _MISMATCH_INTENT_RE.search(intent_text):
                    value = counterpart["value"]
                else:
                    value = _scenario_intent_default_value(
                        intent_text, field["name"]
                    ) or _default_test_data_value(
                        field["name"], used_values, field_input_types.get(field["name"], "text")
                    )
                if value != current_value:
                    field["value"] = value
                    changed = True
                used_values.add(value)
        if changed:
            scenario.test_data = updated_fields
            session.add(scenario)
            session.commit()
            session.refresh(scenario)

        # Detach so the caller can read its attributes (name/type/steps/
        # test_data/expected_result — everything generate_playwright needs)
        # after this session closes, without triggering a lazy DB reload.
        session.expunge(scenario)
        return (
            scenario,
            known_pages,
            known_locators,
            required_fields,
            field_input_types,
            requires_auth,
            primary_page_id,
        )


def _persist_test_asset_sync(
    scenario_external_id: str,
    test_suite_external_id: str,
    code: str,
    requires_auth: bool,
    required_fields: dict[str, bool],
    known_locators: list[dict[str, str]],
    primary_page_id: uuid.UUID | None,
) -> str:
    with Session(engine) as session:
        scenario = session.exec(
            select(Scenario).where(Scenario.external_id == uuid.UUID(scenario_external_id))
        ).one()
        test_suite = session.exec(
            select(TestSuite).where(TestSuite.external_id == uuid.UUID(test_suite_external_id))
        ).one()

        # Feature 7 — the most recent other current TestAsset targeting the
        # same primary Page, if any, is this spec's sibling for the
        # structural consistency check below.
        sibling = None
        if primary_page_id is not None:
            sibling = session.exec(
                select(TestAsset)
                .where(
                    TestAsset.primary_page_id == primary_page_id,
                    TestAsset.scenario_id != scenario.id,
                    TestAsset.current.is_(True),  # type: ignore[attr-defined]
                )
                .order_by(TestAsset.created_at.desc())  # type: ignore[arg-type]
            ).first()

        warnings: list[str] = []
        warnings += spec_linter.lint_required_fields(code, required_fields)
        warnings += spec_linter.lint_locator_provenance(code, known_locators)
        warnings += spec_linter.lint_uses_shared_auth_helper(code, requires_auth)
        warnings += spec_linter.lint_scenario_data_intent(
            scenario.name, scenario.steps, scenario.test_data
        )
        warnings += spec_linter.lint_password_boundary_ignored(
            scenario.name, scenario.steps, scenario.test_data, code
        )
        warnings += spec_linter.lint_asserted_data_not_entered(code, scenario.test_data)
        warnings += spec_linter.lint_tautological_assertion(code)
        warnings += spec_linter.lint_ungrounded_error_container_assertion(code)
        if sibling is not None:
            warnings += spec_linter.lint_sibling_consistency(code, sibling.code)
            warnings += spec_linter.lint_shared_state_contradiction(code, sibling.code)

        test_asset = TestAsset(
            scenario_id=scenario.id,
            test_suite_id=test_suite.id,
            code=code,
            current=True,
            requires_auth=requires_auth,
            status="needs_review" if warnings else "ready",
            warnings=warnings,
            primary_page_id=primary_page_id,
        )
        session.add(test_asset)
        session.commit()
        session.refresh(test_asset)
        return str(test_asset.external_id)


def supersede_test_asset(
    session: Session,
    prior: TestAsset,
    *,
    code: str,
    requires_auth: bool,
    warnings: list[str],
    status: str,
    primary_page_id: uuid.UUID | None,
) -> TestAsset:
    """Flips `prior.current` off and inserts a new `current=True` TestAsset
    for the same scenario/suite — the in-place "replace the current asset"
    operation `_persist_test_asset_sync` above never needed (it only ever
    inserts a brand-new current row; whole-suite supersede is handled
    separately by `ensure_test_suite_activity`, on a *new* TestSuite, not by
    flipping an existing row). HealTestActivity (execution worker) is the
    first caller that needs this, every time a healed candidate passes
    typecheck — not only when it also passes execution — so the "latest
    code" for the next heal attempt is simply whatever TestAsset is
    currently `current` for this scenario, with no separate state to thread
    through the heal loop."""
    prior.current = False
    session.add(prior)
    new_asset = TestAsset(
        scenario_id=prior.scenario_id,
        test_suite_id=prior.test_suite_id,
        code=code,
        current=True,
        requires_auth=requires_auth,
        warnings=warnings,
        status=status,
        primary_page_id=primary_page_id,
    )
    session.add(new_asset)
    session.flush()
    return new_asset
