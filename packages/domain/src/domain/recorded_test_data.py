"""Edit Test Data for recorded (record-and-play) tests — the typed values in
a recording's own code, as `Scenario.test_data` fields, and the direct
literal swap that writes an edited value back. No AI: unlike a generated
test (whose fields have no link to the line their value ended up in), each
recorded field *is* one specific typed call, so its literal can be replaced
in place without touching anything else.

Fields map to typed calls **by order** — `test_data[i]` is the i-th editable
typed call in the code — so a heal that rewrites a locator (into a variable,
across lines) doesn't break the mapping; names are display-only. Password
calls are never editable and never part of that order, so skipping one can
never shift which literal a username or later field writes to.

The account's own login username/email stays in that order (so the
mapping never shifts) but is marked `"login": True` — see
`domain.login_fields`; the API never shows or accepts it.

ponytail: a regex over Playwright source, the same Codegen-vocabulary
approach `recording_worker.steps_parser` takes, not a TypeScript AST — a
hand-edited or unusual call (a value built from variables, a template
string) simply isn't a field. `selectOption` is deliberately left out:
Codegen records option *values* (often UUIDs) that mean nothing to edit; add
it once the editor can offer the dropdown's real choices.

`apply_recorded_test_data` is the whole save, run inline by the API — no
Temporal, no generation worker: a recorded save needs neither.
"""

import re
from dataclasses import dataclass

from sqlmodel import Session, select

from domain.login_fields import is_login_identity_name, is_new_or_confirm, is_password_name
from domain.scenario import Scenario
from domain.test_asset import TestAsset, supersede_test_asset

_TYPED_CALL_RE = re.compile(
    r"\.\s*(?:fill|type|pressSequentially)\(\s*"
    r"(?P<lit>'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\")"
    r"\s*[,)]"
)
# Same locator vocabulary as `recording_worker.steps_parser._LOCATOR_RE`.
_LOCATOR_RE = re.compile(
    r"getBy(?P<kind>Role|Label|Text|Placeholder|TestId|AltText|Title)\(\s*"
    r"(?:['\"](?P<role>\w+)['\"]\s*,\s*)?"
    r"(?:\{[^}]*?name:\s*['\"](?P<name>[^'\"]+)['\"][^}]*\}|['\"](?P<lit>[^'\"]+)['\"])?"
)
_CSS_LOCATOR_RE = re.compile(
    r"locator\(\s*['\"](?:#(?P<id>[\w-]+)|[^'\"]*\[name=\\?['\"]?(?P<name>[\w-]+))"
)
# `statement` ends right before the typed call's own `.`, so this is the
# bare identifier the call is made on (`amountInput` in `amountInput.fill`).
_RECEIVER_RE = re.compile(r"(?P<name>[A-Za-z_$][\w$]*)\s*$")
_IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")
# Ends the form a typed value belongs to: a click (submit, "Next"), a page
# load, or Enter pressed into a field.
_FORM_BREAK_RE = re.compile(r"\.\s*(?:click|dblclick)\(|\.goto\(|\.press\(\s*['\"]Enter")
_STATEMENT_BREAK_RE = re.compile(r";|=>\s*\{")
_MAX_VARIABLE_HOPS = 3


class RecordedFieldsChanged(Exception):
    """The code's editable typed calls no longer line up with the recorded
    `test_data` (a heal or hand edit added/removed one), so which literal
    a field belongs to can't be trusted — nothing is written."""


@dataclass(frozen=True)
class RecordedInput:
    description: str | None  # locator / variable wording, before de-duping
    value: str
    start: int  # span of the string literal, quotes included
    end: int
    is_password: bool


def _decode_literal(literal: str) -> str:
    out: list[str] = []
    body = literal[1:-1]
    i = 0
    while i < len(body):
        char = body[i]
        if char == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out)


def _encode_literal(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f"'{escaped}'"


def _locator_description(text: str) -> str | None:
    """The last named locator in `text` (closest to the call in a chain),
    else the last role-only one."""
    named = None
    role = None
    for m in _LOCATOR_RE.finditer(text):
        if m.group("name") or m.group("lit"):
            named = m.group("name") or m.group("lit")
        elif m.group("role"):
            role = m.group("role")
    if named or role:
        return named or role
    css = None
    for m in _CSS_LOCATOR_RE.finditer(text):
        css = m.group("id") or m.group("name")
    return _humanize(css.replace("-", "_")) if css else None


def _variable_definition(code: str, name: str, before: int) -> str | None:
    """The right-hand side of the nearest `const|let|var <name> = …;` above
    `before` — where a healed spec keeps the locator a typed call uses."""
    pattern = re.compile(rf"(?:const|let|var)\s+{re.escape(name)}\s*=\s*(?P<expr>[^;]*);")
    matches = [m for m in pattern.finditer(code, 0, before)]
    return matches[-1].group("expr") if matches else None


def _humanize(identifier: str) -> str:
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", identifier).replace("_", " ").split()
    return " ".join(words).capitalize() if words else identifier


def _describe_call(code: str, statement: str, statement_start: int) -> tuple[str | None, bool]:
    """(description, is_password) for the typed call ending `statement`."""
    description = _locator_description(statement)
    password_evidence = [statement]
    receiver = _RECEIVER_RE.search(statement)
    if description is None and receiver and receiver.group("name") != "page":
        variable = receiver.group("name")
        password_evidence.append(variable)
        # Follow e.g. `const field = await ensureVisible(amountInput)` back to
        # the variable that actually holds a locator.
        names = [variable]
        for _ in range(_MAX_VARIABLE_HOPS):
            if not names:
                break
            expr = _variable_definition(code, names[0], statement_start)
            if expr is None:
                break
            password_evidence.append(expr)
            description = _locator_description(expr)
            if description is not None:
                break
            names = [n for n in _IDENT_RE.findall(expr) if n not in {"await", "page"}]
            names = [n for n in names if _variable_definition(code, n, statement_start)]
        if description is None:
            description = _humanize(variable)
    is_password = any(is_password_name(text) for text in password_evidence)
    return description, is_password


def find_recorded_inputs(code: str) -> list[RecordedInput]:
    """Every typed call (`fill`/`type`/`pressSequentially`) with a plain
    string literal, in code order — passwords included, flagged."""
    inputs: list[RecordedInput] = []
    for m in _TYPED_CALL_RE.finditer(code):
        breaks = list(_STATEMENT_BREAK_RE.finditer(code, 0, m.start()))
        statement_start = breaks[-1].end() if breaks else 0
        # Password evidence never includes the typed value itself, so
        # typing "password" into a search box stays editable.
        statement = code[statement_start : m.start()]
        description, is_password = _describe_call(code, statement, statement_start)
        inputs.append(
            RecordedInput(
                description=description,
                value=_decode_literal(m.group("lit")),
                start=m.start("lit"),
                end=m.end("lit"),
                is_password=is_password,
            )
        )
    return inputs


def _editable_inputs(code: str) -> list[RecordedInput]:
    return [i for i in find_recorded_inputs(code) if not i.is_password]


def _forms(code: str, inputs: list[RecordedInput]) -> list[list[RecordedInput]]:
    """Typed calls grouped by form: consecutive calls with no click, page
    load, or Enter between them."""
    forms: list[list[RecordedInput]] = []
    for recorded in inputs:
        if forms and not _FORM_BREAK_RE.search(code, forms[-1][-1].end, recorded.start):
            forms[-1].append(recorded)
        else:
            forms.append([recorded])
    return forms


def _is_identity(recorded: RecordedInput) -> bool:
    return not recorded.is_password and is_login_identity_name(recorded.description or "")


def _login_inputs(code: str, inputs: list[RecordedInput]) -> set[int]:
    """Spans (`start`) of the account's own username/email: the identity
    fields on the form the login password is typed into, or — for a
    multi-step login whose password form holds nothing else — on the form
    just before it.

    ponytail: inferred from the code alone (Codegen records no "this was
    the login" marker), so it's deliberately strict: a form with any other
    kind of field (signup's "First name") or a new/confirm password (signup,
    reset) is never a login form, and a login form with an unusual extra
    field (a company code) leaves its username editable. A fuller version
    would have the recorder mark the login steps while they're recorded."""
    forms = _forms(code, inputs)
    marked: set[int] = set()
    for index, form in enumerate(forms):
        passwords = [i for i in form if i.is_password]
        if not passwords or any(is_new_or_confirm(i.description or "") for i in passwords):
            continue
        others = [i for i in form if not i.is_password]
        if others:
            if all(_is_identity(i) for i in others):
                marked.update(i.start for i in others)
        elif index > 0 and all(_is_identity(i) for i in forms[index - 1]):
            marked.update(i.start for i in forms[index - 1])
    return marked


def extract_recorded_test_data(code: str) -> list[dict]:
    """`Scenario.test_data` fields for a recording — same `{name,
    mandatory, value}` shape generation writes, one per editable typed
    call, in code order, the login username/email marked `"login": True`.
    Repeated names (Codegen records a correction as a second fill) become
    `Name (2)`."""
    login = _login_inputs(code, find_recorded_inputs(code))
    fields: list[dict] = []
    seen: dict[str, int] = {}
    for position, recorded in enumerate(_editable_inputs(code), start=1):
        base = recorded.description or f"Field {position}"
        seen[base] = seen.get(base, 0) + 1
        name = base if seen[base] == 1 else f"{base} ({seen[base]})"
        field = {"name": name, "mandatory": recorded.value != "", "value": recorded.value}
        if recorded.start in login:
            field["login"] = True
        fields.append(field)
    return fields


def swap_recorded_values(code: str, fields: list[dict]) -> tuple[str, list[tuple[str, str]]]:
    """Writes each field's value into its own typed call's literal (by
    order) and returns (new code, [(old, new)] for the values that
    changed). Everything else in the code stays byte-identical."""
    editable = _editable_inputs(code)
    if len(editable) != len(fields):
        raise RecordedFieldsChanged(
            f"{len(editable)} editable typed values in the code, {len(fields)} test data fields"
        )
    changes: list[tuple[str, str]] = []
    new_code = code
    # Right to left, so earlier spans stay valid as later ones change length.
    for recorded, field in reversed(list(zip(editable, fields, strict=True))):
        new_value = str(field.get("value") or "")
        if new_value == recorded.value:
            continue
        assert not recorded.is_password
        new_code = (
            new_code[: recorded.start] + _encode_literal(new_value) + new_code[recorded.end :]
        )
        changes.append((recorded.value, new_value))
    changes.reverse()
    return new_code, changes


def update_recorded_steps(steps: list[str], changes: list[tuple[str, str]]) -> list[str]:
    """Rewrites the `Fill in '<old>' …` step chip (as
    `recording_worker.steps_parser` phrases it) for each changed value, in
    order. A step it can't find is left as is — steps are display-only."""
    updated = list(steps)
    cursor = 0
    for old, new in changes:
        prefix = f"Fill in {old!r}"
        for i in range(cursor, len(updated)):
            if updated[i].startswith(prefix):
                updated[i] = f"Fill in {new!r}" + updated[i][len(prefix) :]
                cursor = i + 1
                break
    return updated


def apply_recorded_test_data(session: Session, scenario: Scenario) -> TestAsset:
    """Edit Test Data for a recorded Scenario: writes each edited value into
    its own typed call's literal and supersedes the current TestAsset with
    everything else the recording had — same `requires_auth`/tag (never
    recomputed: a recorded Scenario has no pages to recompute it from), same
    warnings/status (recordings are never linted as generated specs) — and
    updates the step chips' typed values. Returns the current TestAsset
    unchanged when no value differs. Raises `RecordedFieldsChanged` with
    nothing written. Commits."""
    prior = session.exec(
        select(TestAsset).where(
            TestAsset.scenario_id == scenario.id,
            TestAsset.current.is_(True),  # type: ignore[attr-defined]
        )
    ).one()
    code, changes = swap_recorded_values(prior.code, scenario.test_data)
    if not changes:
        return prior

    new_asset = supersede_test_asset(
        session,
        prior,
        code=code,
        requires_auth=prior.requires_auth,
        warnings=list(prior.warnings),
        status=prior.status,
        primary_page_id=prior.primary_page_id,
    )
    scenario.steps = update_recorded_steps(scenario.steps, changes)
    session.add(scenario)
    session.commit()
    session.refresh(new_asset)
    return new_asset
