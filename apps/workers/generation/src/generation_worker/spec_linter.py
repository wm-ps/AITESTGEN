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

from domain import Application, Form, FormField, Page
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
    """Feature 1 backstop — the prompt tells the LLM to call the shared
    `fillCredentials` helper instead of writing raw login fill-steps whenever
    a Scenario needs an authenticated session as a precondition; this is the
    deterministic check for whether it actually did."""
    if not requires_auth:
        return []
    if "fillCredentials" in code and "support/auth" in code:
        return []
    return [
        "scenario requires an authenticated session but the generated spec does not "
        "import/call the shared fillCredentials helper from '../support/auth'"
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


def apply_auth_tag(code: str, requires_auth: bool) -> str:
    """Feature 4 — deterministically rewrite the first `test(...)`/
    `test.describe(...)` call to carry `{ tag: '@auth' }`/`{ tag: '@public' }`,
    overriding whatever (if anything) the LLM wrote — ground truth beats an
    LLM guess here the same way it does for locators. The exported project's
    Playwright config (`test_suite_export.py`) filters projects on this tag,
    so it must always be correct, never merely "usually right"."""
    tag = "@auth" if requires_auth else "@public"
    match = _TEST_CALL_RE.search(code)
    if match is None:
        return code
    call, quote, name = match.group(1), match.group(2), match.group(3)
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
    session: Session, application: Application, primary_page: Page | None
) -> bool:
    """Feature 4's app-level heuristic (per plan sign-off — no true per-page
    "reached without session" capture exists in Discovery today, and adding
    it would mean crawler changes out of scope here): a login page was
    actually captured for this Application AND this Scenario's primary page
    isn't that login page itself."""
    login_url = _find_login_page_url(session, application.id)
    if login_url is None:
        return False
    if primary_page is not None and primary_page.url == login_url:
        return False
    return True


def required_fields_for_page(session: Session, page_id: uuid.UUID) -> dict[str, bool]:
    """Feature 3's manifest — Discovery's own `FormField.required` for every
    field captured on this page, keyed by field name."""
    forms = session.exec(select(Form).where(Form.page_id == page_id)).all()
    if not forms:
        return {}
    fields = session.exec(
        select(FormField).where(FormField.form_id.in_([f.id for f in forms]))  # type: ignore[attr-defined]
    ).all()
    return {field.name: field.required for field in fields if field.name}
