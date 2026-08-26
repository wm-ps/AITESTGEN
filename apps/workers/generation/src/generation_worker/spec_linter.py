"""spec_linter — post-generation, ground-truth checks for a generated Playwright spec.

Flag-only (never blocks a spec from shipping — an imperfect regex-over-code
heuristic isn't trustworthy enough to reject on): every finding here becomes
one `TestAsset.warnings` entry and flips `TestAsset.status` to "needs_review"
for a human to look at, nothing more.

`resolve_requires_auth`'s login-page heuristic mirrors
`apps/api/src/api/test_suite_export.py::find_login_page_evidence` (the
captured `Form` with a password-type `FormField` is the login form) —
duplicated rather than shared, same reasoning `_resolve_known_application_model_sync`
already gives for its own duplication of `scenario_generation_activity`'s
steps->pages resolution: different caller, not worth the coupling.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from domain import Application, Form, FormField, Page, Scenario
from sqlmodel import Session, select


@dataclass(frozen=True)
class LocatorUsage:
    call: str
    value: str


_GET_BY_ROLE_RE = re.compile(
    r"getByRole\(\s*['\"](?P<role>\w+)['\"]"
    r"(?:\s*,\s*\{[^}]*?name:\s*(?:['\"](?P<lit>[^'\"]+)['\"]|/[^/]+/))?"
)
_GET_BY_TEXT_LIKE_RE = re.compile(
    r"(?P<call>getByLabel|getByText|getByTestId|getByPlaceholder)\(\s*"
    r"(?:['\"](?P<lit>[^'\"]+)['\"]|/[^/]+/)"
)
_LOCATOR_RE = re.compile(r"\.locator\(\s*['\"](?P<sel>[^'\"]+)['\"]")


def extract_locator_usages(code: str) -> list[LocatorUsage]:
    """Every accessible-name-based or raw-selector locator call in `code`.
    A `/regex/` argument is intentionally skipped (the prompt's own
    Multi-fragment rule tells the LLM to use a partial regex precisely
    because the full text is never stable — flagging those would just be
    noise, not a real "invented text" finding)."""
    usages: list[LocatorUsage] = []
    for m in _GET_BY_ROLE_RE.finditer(code):
        lit = m.group("lit")
        if lit:
            usages.append(LocatorUsage(f"getByRole:{m.group('role')}", lit))
    for m in _GET_BY_TEXT_LIKE_RE.finditer(code):
        lit = m.group("lit")
        if lit:
            usages.append(LocatorUsage(m.group("call"), lit))
    for m in _LOCATOR_RE.finditer(code):
        usages.append(LocatorUsage("locator", m.group("sel")))
    return usages


def _known_accessible_names(known_locators: list[dict[str, str]]) -> set[str]:
    names: set[str] = set()
    for loc in known_locators:
        strategy = loc.get("strategy")
        selector = loc.get("selector", "")
        if strategy == "label":
            names.add(selector.strip().lower())
        elif strategy == "aria":
            m = re.search(r'name="([^"]+)"', selector)
            if m:
                names.add(m.group(1).strip().lower())
        elif strategy == "text":
            m = re.search(r'text="([^"]+)"', selector)
            if m:
                names.add(m.group(1).strip().lower())
    return names


def lint_locator_provenance(code: str, known_locators: list[dict[str, str]]) -> list[str]:
    """Feature 2 — flag an accessible-name locator whose text has no match
    among Discovery's captured names for this journey. Raw `.locator(...)`
    selector strings are skipped: those are the deterministic CSS-attribute
    forms the prompt tells the LLM to build itself per field type, not
    "invented text" the way a made-up `getByRole(..., {name: 'Sign In'})`
    would be."""
    known_names = _known_accessible_names(known_locators)
    if not known_names:
        return []
    warnings = []
    for usage in extract_locator_usages(code):
        if usage.call == "locator":
            continue
        if usage.value.strip().lower() not in known_names:
            warnings.append(
                f"locator text {usage.value!r} ({usage.call}) has no match among Discovery's "
                "captured accessible names for this journey — verify it wasn't invented"
            )
    return warnings


def lint_required_fields(code: str, required_fields: dict[str, bool]) -> list[str]:
    """Feature 3 — flag a Discovery-captured required field this spec never
    references at all (by field name appearing anywhere in the code, case-
    insensitive — a cheap but effective proxy: a spec that never mentions a
    required field's name almost certainly never fills or asserts on it)."""
    code_lower = code.lower()
    return [
        f"required field {name!r} (per Discovery's captured FormField.required) is not "
        "referenced anywhere in the generated spec"
        for name, required in required_fields.items()
        if required and name and name.lower() not in code_lower
    ]


def lint_uses_shared_auth_helper(code: str, requires_auth: bool) -> list[str]:
    """Feature 1 backstop — the prompt tells the LLM never to call the shared
    `fillCredentials` helper (or write raw login fill-steps) in a spec whose
    target page already requires an authenticated session, since the
    exported project's `authenticated` Playwright project already supplies
    one via `storageState` (set up once by `tests/auth.setup.ts`) before this
    spec's body ever runs; this is the deterministic check for whether it
    actually complied.

    `[FIXED]` inverted from its original sense — that version flagged a
    `requires_auth=True` spec for *not* calling `fillCredentials`, rewarding
    exactly the bug this now catches: every such spec ended up calling
    `fillCredentials(page)` right after `page.goto(<base_url>)` (the prompt's
    own separate "visit the base URL first" rule), timing out hunting for a
    login field that only exists on the real login page, not the base URL a
    fresh, already-authenticated session never needs to visit first at all."""
    if not requires_auth:
        return []
    if "fillCredentials" not in code and "support/auth" not in code:
        return []
    return [
        "scenario's target page already requires an authenticated session (supplied by "
        "storageState via tests/auth.setup.ts) but the generated spec still imports/calls "
        "the shared fillCredentials helper — this re-authenticates redundantly and, since "
        "the login form only exists on the dedicated login page, times out if the spec's "
        "own navigation ever lands elsewhere first"
    ]


def lint_sibling_consistency(code: str, sibling_code: str) -> list[str]:
    """Feature 7 — diff this spec's locator usage against the most recent
    sibling TestAsset for the same primary Page: a locator value the sibling
    targets but this spec never does (a possibly-dropped step), and a
    locator value both target but via a different call type (a possibly
    inconsistent locator strategy)."""
    new_usages = {(u.call, u.value.lower()) for u in extract_locator_usages(code)}
    sibling_usages = {(u.call, u.value.lower()) for u in extract_locator_usages(sibling_code)}
    new_values = {v for _, v in new_usages}
    sibling_values = {v for _, v in sibling_usages}

    warnings = [
        f"sibling spec for this page also targets {value!r}, missing here — verify no step "
        "was dropped"
        for value in sorted(sibling_values - new_values)
    ]
    for value in sorted(sibling_values & new_values):
        sib_calls = sorted({c for c, v in sibling_usages if v == value})
        new_calls = sorted({c for c, v in new_usages if v == value})
        if sib_calls != new_calls:
            warnings.append(
                f"sibling spec targets {value!r} via {sib_calls} but this spec uses "
                f"{new_calls} — verify the locator strategy wasn't changed inconsistently"
            )
    return warnings


_TEST_CALL_RE = re.compile(r"(test(?:\.describe)?)\(\s*(['\"])(.*?)\2\s*,\s*(?:\{[^}]*?\}\s*,\s*)?")


_INLINE_TAG_RE = re.compile(r"\s*@(?:auth|public)\b")


def apply_auth_tag(code: str, requires_auth: bool) -> str:
    """Feature 4 — deterministically rewrite the first `test(...)`/
    `test.describe(...)` call to carry `{ tag: '@auth' }`/`{ tag: '@public' }`,
    overriding whatever (if anything) the LLM wrote — ground truth beats an
    LLM guess here the same way it does for locators. The exported project's
    Playwright config (`test_suite_export.py`) filters projects on this tag,
    so it must always be correct, never merely "usually right".

    `[FIXED]` The LLM sometimes bakes its own guess for the tag literally
    into the test's name string itself (e.g. `test('Session expires while
    opening accounts @auth', async (...`) instead of a proper `{ tag: ... }`
    second argument. Left alone, this function's rewrite only added the
    correct tag metadata alongside it, leaving a name that visibly disagreed
    with the (correct) tag actually applied — stripped here so the name
    can't contradict it."""
    tag = "@auth" if requires_auth else "@public"
    match = _TEST_CALL_RE.search(code)
    if match is None:
        return code
    call, quote, name = match.group(1), match.group(2), match.group(3)
    name = _INLINE_TAG_RE.sub("", name).strip()
    replacement = f"{call}({quote}{name}{quote}, {{ tag: '{tag}' }}, "
    return code[: match.start()] + replacement + code[match.end() :]


def _find_login_page_url(session: Session, application_id: uuid.UUID) -> str | None:
    pages = session.exec(select(Page).where(Page.application_id == application_id)).all()
    page_by_id = {p.id: p for p in pages}
    if not pages:
        return None
    forms = session.exec(
        select(Form).where(Form.page_id.in_(page_by_id.keys()))  # type: ignore[attr-defined]
    ).all()
    if not forms:
        return None
    fields = session.exec(
        select(FormField).where(FormField.form_id.in_([f.id for f in forms]))  # type: ignore[attr-defined]
    ).all()
    fields_by_form: dict[uuid.UUID, list[FormField]] = {}
    for field in fields:
        fields_by_form.setdefault(field.form_id, []).append(field)
    for form in forms:
        if any(f.input_type == "password" for f in fields_by_form.get(form.id, [])):
            page = page_by_id.get(form.page_id)
            return page.url if page else None
    return None


def resolve_requires_auth(
    session: Session,
    application: Application,
    primary_page: Page | None,
    scenario: Scenario | None = None,
) -> bool:
    """Feature 4's app-level heuristic: a login page was actually captured
    for this Application AND this Scenario's primary page isn't that login
    page itself.

    `[REMOVED]` This used to also override to `False` (no pre-applied
    `storageState`) whenever the Scenario's name/steps named a "no valid
    session" intent — session-expired, unauthenticated access, post-logout
    access, never having logged in. Verified against real generated specs
    for every one of those phrasings (not just the logout case): each one's
    OWN steps first navigate to an authenticated page and assert reaching
    it successfully, THEN simulate losing the session (clearing cookies,
    clicking logout) before checking the now-blocked page — e.g.
    "Unauthenticated access to the profile" reaches `/Dashboard` and clicks
    a `Logout` button before ever touching `/Account/Profile`. None of
    this generator's own output is a scenario that starts genuinely
    anonymous — every "arrives without a session" Scenario still needs the
    real, pre-applied `storageState` to reach the authenticated state it
    starts from. Tagging any of them `@public` breaks that first half:
    the test was never authenticated to begin with, so navigating straight
    to the authenticated page it needs as a precondition redirects to
    login and fails immediately — the exact same bug class as the logout
    one, just for a sibling set of phrasings. `scenario` is kept as a
    parameter (unused) rather than dropped, in case a future phrasing
    genuinely never establishes a session and needs a fresh, real
    override — not to be reintroduced from words alone without the same
    against-real-generated-code verification this removal was based on."""
    login_url = _find_login_page_url(session, application.id)
    if login_url is None:
        return False
    if primary_page is not None and primary_page.url == login_url:
        return False
    return True


def required_fields_for_pages(session: Session, page_ids: list[uuid.UUID]) -> dict[str, bool]:
    """Feature 3's manifest — Discovery's own `FormField.required` for every
    field captured across a Journey's pages, keyed by field name.

    `[FIXED]` Used to take a single `page_id` (the Journey's primary page —
    the first one its steps visit). A multi-page Journey (e.g. Dashboard ->
    a Loans page with the actual form) has its real fields on a LATER page,
    so that page's metadata was never looked up at all — every field on it
    silently lost its `required`/`input_type` awareness below, for any
    application, not just one."""
    if not page_ids:
        return {}
    forms = session.exec(select(Form).where(Form.page_id.in_(page_ids))).all()  # type: ignore[attr-defined]
    if not forms:
        return {}
    fields = session.exec(
        select(FormField).where(FormField.form_id.in_([f.id for f in forms]))  # type: ignore[attr-defined]
    ).all()
    return {field.name: field.required for field in fields if field.name}


def field_input_types_for_pages(session: Session, page_ids: list[uuid.UUID]) -> dict[str, str]:
    """Mirrors `required_fields_for_pages`'s query exactly, returning each
    field's captured HTML `input_type` by name instead of its `required`
    flag. Lets `_default_test_data_value`'s generation-time fallback stay
    type-aware the same way Discovery's own crawler (`_generic_value` in
    `discovery_worker/crawler.py`) already is, instead of guessing purely
    from the field's name."""
    if not page_ids:
        return {}
    forms = session.exec(select(Form).where(Form.page_id.in_(page_ids))).all()  # type: ignore[attr-defined]
    if not forms:
        return {}
    fields = session.exec(
        select(FormField).where(FormField.form_id.in_([f.id for f in forms]))  # type: ignore[attr-defined]
    ).all()
    return {field.name: field.input_type for field in fields if field.name}


_UNICODE_INTENT_RE = re.compile(
    r"unicode|non-ascii|non ascii|emoji|accented|internationali[sz]|multilingual",
    re.IGNORECASE,
)
_NUMERIC_INTENT_RE = re.compile(
    r"\bnumeric\b|\bnumber\b|\bquantity\b|\bdecimal\b|\binteger\b", re.IGNORECASE
)
_DATE_INTENT_RE = re.compile(r"\bdate\b|\bdated\b", re.IGNORECASE)
# Deliberately its own category, not folded into `_UNICODE_INTENT_RE` above:
# "special character"/"markup" scenarios are satisfied by plain-ASCII
# markup (`<test>&"'`), so validating them against `_NON_ASCII_RE` would
# false-positive on a correctly-generated, pure-ASCII markup value.
_MARKUP_INTENT_RE = re.compile(r"markup|special character", re.IGNORECASE)
_NON_ASCII_RE = re.compile(r"[^\x00-\x7F]")
_HAS_DIGIT_RE = re.compile(r"\d")
_DATE_LIKE_RE = re.compile(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}")
_HAS_MARKUP_CHAR_RE = re.compile(r"[<>&]")

_SCENARIO_DATA_INTENT_CHECKS = (
    (_UNICODE_INTENT_RE, _NON_ASCII_RE, "non-ASCII/Unicode data"),
    (_NUMERIC_INTENT_RE, _HAS_DIGIT_RE, "a numeric value"),
    (_DATE_INTENT_RE, _DATE_LIKE_RE, "a date-like value"),
    (_MARKUP_INTENT_RE, _HAS_MARKUP_CHAR_RE, "markup-like special characters (e.g. <, >, &)"),
)


def lint_scenario_data_intent(
    scenario_name: str, scenario_steps: list[str], test_data: list[dict]
) -> list[str]:
    """Features 1+3 — once a Scenario's own name/steps explicitly call for a
    specific data property (Unicode, a numeric value, a date), the resolved
    `test_data` values actually used for this test (the prompt tells the
    LLM to use these exact values verbatim, see `_describe_test_data` in
    `ai_provider/hosted.py`) must exhibit that property. Otherwise a still-
    blank field's deterministic fallback (or an unrelated reviewer-entered
    value) silently substituted a generic placeholder that doesn't actually
    exercise what the Scenario claims to test at all (e.g. "Sign in with a
    Unicode password" backed by a plain ASCII "Password123").

    Only flags when this Scenario actually has `test_data` fields to check —
    a read-only/navigation Scenario whose name happens to mention "date"
    (e.g. "Verify transaction date is displayed") has no fields to validate
    and is correctly left alone."""
    values = [str(f.get("value") or "") for f in test_data if f.get("value")]
    if not values:
        return []
    intent_text = f"{scenario_name} {' '.join(scenario_steps)}"
    return [
        f"scenario name/steps indicate this test needs {label}, but none of the resolved "
        "test_data values contain one — the generated test doesn't actually exercise what "
        "the scenario claims to test"
        for intent_re, data_re, label in _SCENARIO_DATA_INTENT_CHECKS
        if intent_re.search(intent_text) and not any(data_re.search(v) for v in values)
    ]


_PASSWORD_FIELD_RE = re.compile(r"pass(word)?", re.IGNORECASE)
_PASSWORD_BOUNDARY_INTENT_RE = re.compile(
    r"password.*(?:unicode|non-ascii|non ascii|maximum[- ]length|minimum[- ]length)|"
    r"(?:unicode|non-ascii|non ascii|maximum[- ]length|minimum[- ]length).*password",
    re.IGNORECASE,
)
_BARE_FILL_CREDENTIALS_RE = re.compile(r"fillCredentials\(\s*page\s*\)")


def lint_password_boundary_ignored(
    scenario_name: str, scenario_steps: list[str], test_data: list[dict], code: str
) -> list[str]:
    """A Scenario about a password boundary/character-set property (Unicode,
    a length boundary) needs its specific `test_data` password value passed
    explicitly to `fillCredentials(page, username, password)` — the bare
    `fillCredentials(page)` call always submits the shared CREDENTIALS
    registry's default password (see `support/config.ts`), silently
    ignoring whatever specific value this Scenario resolved. Only flags
    when this Scenario's own test_data actually holds a password value —
    if a reviewer never provided one and no default applied, there's
    nothing for the spec to have ignored."""
    intent_text = f"{scenario_name} {' '.join(scenario_steps)}"
    if not _PASSWORD_BOUNDARY_INTENT_RE.search(intent_text):
        return []
    has_password_value = any(
        _PASSWORD_FIELD_RE.search(f.get("name") or "") and f.get("value")
        for f in test_data
    )
    if not has_password_value:
        return []
    if _BARE_FILL_CREDENTIALS_RE.search(code):
        return [
            "scenario name/steps describe a password boundary/character-set property, but "
            "the generated spec calls fillCredentials(page) with no explicit password "
            "argument — this always submits the shared default password instead of this "
            "scenario's specific one, so the boundary/property is never actually exercised"
        ]
    return []


_ASSERTION_TEXT_RE = re.compile(
    r"(?:getByText|toHaveText|toContainText)\(\s*['\"]([^'\"]{4,})['\"]"
)
_FILL_TEXT_RE = re.compile(r"\.fill\(\s*['\"]([^'\"]{4,})['\"]")


def lint_asserted_data_not_entered(code: str, test_data: list[dict]) -> list[str]:
    """Discovery never captures an application's actual rendered row/cell
    data (only structure — pages, forms, field names/types, selectors; see
    `Component`/`ComponentLocator`) — so a `test_data` value this generator
    resolved (a default, or a reviewer's placeholder) is never verified
    real, pre-existing content anywhere else in the application. A spec
    that searches for/asserts one of these values on a page WITHOUT this
    same test ever having filled it in first (e.g. "the Cards page shows a
    card ending in 4111111111", when nothing in this test ever entered
    that number) is asserting a fabricated expectation, not a real one —
    this is exactly the failure mode the Existing-data assertion rule in
    `ai_provider/hosted.py`'s prompt targets; this is its deterministic
    backstop, the same layering `lint_uses_shared_auth_helper` established
    for the storageState rule."""
    values = {str(f.get("value") or "") for f in test_data if f.get("value")}
    asserted = {m.group(1) for m in _ASSERTION_TEXT_RE.finditer(code)}
    filled = {m.group(1) for m in _FILL_TEXT_RE.finditer(code)}
    return [
        f"generated spec asserts test_data value {value!r} is displayed on the page, but this "
        "test never fills/enters that value itself — Discovery never captures real, pre-"
        "existing page content, so this looks like a generator default being asserted as if it "
        "were real seeded data; verify this isn't a hallucinated expectation"
        for value in sorted(values & asserted - filled)
    ]


_TAUTOLOGY_NOT_RE = re.compile(
    r"if\s*\(\s*([\w.\[\]'\"]+)\s*!==\s*([\w.\[\]'\"]+)\s*\)\s*\{\s*"
    r"(?:await\s+)?expect\(\s*\1\s*\)\.not\.toBe\(\s*\2\s*\)"
)
_TAUTOLOGY_EQ_RE = re.compile(
    r"if\s*\(\s*([\w.\[\]'\"]+)\s*===\s*([\w.\[\]'\"]+)\s*\)\s*\{\s*"
    r"(?:await\s+)?expect\(\s*\1\s*\)\.toBe\(\s*\2\s*\)"
)


def lint_tautological_assertion(code: str) -> list[str]:
    """Feature 6 — flags a generated spec's `if (x !== y) { expect(x).not.toBe(y) }`
    fallback (or its `===`/`.toBe` mirror): the `expect(...)` only ever runs
    inside the branch where the comparison is already known true, so it can
    never fail and verifies nothing. This is the generator's own tell that
    it couldn't derive a meaningful assertion — flagged for human review
    rather than silently shipped as if it were a real check."""
    if _TAUTOLOGY_NOT_RE.search(code) or _TAUTOLOGY_EQ_RE.search(code):
        return [
            "generated spec contains a tautological assertion (an `if (x !== y) { "
            "expect(x).not.toBe(y) }` pattern, or its `===`/`.toBe` mirror) that can never "
            "fail — this indicates the generator could not derive a meaningful assertion for "
            "this scenario; treat it as unverifiable and review/replace it by hand"
        ]
    return []


_COUNT_ASSERTION_RE = re.compile(
    r"(?:getByRole\(\s*['\"]\w+['\"](?:\s*,\s*\{[^}]*?name:\s*['\"](?P<role_name>[^'\"]+)"
    r"['\"][^}]*\})?\)|getByText\(\s*['\"](?P<text_name>[^'\"]+)['\"]\)|"
    r"locator\(\s*['\"](?P<sel>[^'\"]+)['\"]\))"
    r"[^;]{0,120}?\.toHaveCount\(\s*(?P<count>\d+)\s*[,)]",
    re.DOTALL,
)


def _count_assertions(code: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for m in _COUNT_ASSERTION_RE.finditer(code):
        key = (m.group("role_name") or m.group("text_name") or m.group("sel") or "").strip().lower()
        if key:
            result[key] = int(m.group("count"))
    return result


_GENERIC_ERROR_GUESS_RE = re.compile(
    r'role="alert"|aria-live|\.toast\b|\.modal\b|class\*="error"|class\*="failure"|'
    r'class\*="failed"|data-state="error"|data-status="error"',
    re.IGNORECASE,
)
_LOCATOR_VAR_ASSIGN_RE = re.compile(
    r"(?:const|let)\s+(\w+)\s*=\s*page[\s\S]{0,30}?\.locator\(([\s\S]{0,400}?)\)"
)


def lint_ungrounded_error_container_assertion(code: str) -> list[str]:
    """Discovery never captures an alert/toast/modal CONTAINER as such (see
    `Component`'s own type list — only buttons, links, and form fields).
    A locator string guessing at one via a generic, multi-convention CSS/
    role selector (`[role="alert"]`, `.error`, `[aria-live]`, `.toast`,
    `.modal`, ...) is therefore never grounded in anything Known locators
    actually gave the LLM — it's always an invented guess, even when it
    looks like idiomatic Playwright. Flags a HARD, must-pass \
    `toBeVisible()` assertion on such a locator: if the real application \
    never renders one of these conventions, the test times out and fails \
    even though a real, already-queryable signal (URL/form-state) may \
    already have proved the same outcome. A soft, log-only \
    `.count() === 0` check on the same variable is fine and not flagged —
    this is the deterministic backstop for the prompt's own Failure-
    outcome assertion rules."""
    warnings = []
    for match in _LOCATOR_VAR_ASSIGN_RE.finditer(code):
        var_name, locator_arg = match.group(1), match.group(2)
        if not _GENERIC_ERROR_GUESS_RE.search(locator_arg):
            continue
        hard_assert_re = re.compile(rf"expect\(\s*{re.escape(var_name)}\b[^)]*\)\.toBeVisible\(")
        if not hard_assert_re.search(code):
            continue
        soft_check_re = re.compile(rf"{re.escape(var_name)}\b[^;]*\.count\(\)\s*===?\s*0")
        if soft_check_re.search(code):
            continue
        warnings.append(
            f"generated spec hard-asserts that a generic, ungrounded error/alert-container "
            f"guess ({var_name!r}) is visible — this locator has no basis in Known locators, "
            "so if the application never renders one of these conventions, the test times out "
            "and fails even though a real signal (URL/form-state) may already have proved the "
            "expected failure; this should be a soft, log-only check instead"
        )
    return warnings


def lint_shared_state_contradiction(code: str, sibling_code: str) -> list[str]:
    """Feature 5 — flags an obvious contradiction between this spec and its
    most recent sibling TestAsset for the same primary Page (Feature 7's
    existing sibling lookup, reused as-is): both assert `toHaveCount(N)` on
    the exact same locator, but with a different N. Since both specs run
    against the same account/seeded state, two different expected counts
    for the identical resource can't both be right — this doesn't decide
    which one is wrong, only that they disagree, same as
    `lint_sibling_consistency`'s existing precision level."""
    this_counts = _count_assertions(code)
    sibling_counts = _count_assertions(sibling_code)
    return [
        f"this spec asserts toHaveCount({count}) on {key!r} but the sibling spec for the "
        f"same page asserts toHaveCount({sibling_counts[key]}) on the same locator — verify "
        "these aren't contradictory assumptions about the same shared account/state"
        for key, count in this_counts.items()
        if key in sibling_counts and sibling_counts[key] != count
    ]
