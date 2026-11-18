"""Field-validation scenarios built from the fields Explorer recorded on each
form: its required flags, the limits the page's code sets (min, max,
minlength, maxlength, pattern, an email type) and the rules it read off the
screen ("Must be a valid email address", "Maximum 255 characters").

The planner is asked for these too, but it plans a few screens at a time and
the scenario cap used to trim them like any other idea; these are written for
every form with something to check, and tried before the planner's ideas."""

import re
from typing import Any

# The 'coverage' of every scenario written here (tests_stage tries these first).
FIELD_CHECK = "F-05 Field rules"

_EMAIL = re.compile(r"valid e-?mail", re.I)
_MIN = re.compile(r"at least (\d+) characters", re.I)
_MAX = re.compile(r"(?:maximum|max\.?|at most|no more than|up to) (\d+) characters", re.I)
_MUST = re.compile(r"^\s*must\b", re.I)
# A form that changes a password is never pressed by a test (the planner's rule too).
CHANGES_PASSWORD = re.compile(r"\b(new|current|old) password\b", re.I)
# Sign-in is planned elsewhere; on a settings screen (a layout builder, a field
# setup) "required" describes the set-up, not a field to fill in; a detail
# view shows a record (its fields are a side panel or composer, no Save).
SKIP_KINDS = {"login", "settings", "detail"}
# Limits the page's own code sets on a field (read by the browser, see
# browser.py); kept with the field so tests can break them.
CODE_LIMITS = ("min", "max", "minlength", "maxlength", "pattern")
# Per form: the empty form, this many required fields left out one at a time
# and this many broken rules. They are tried on top of the scenario cap
# (tests_stage.balanced), so a form-heavy app keeps its behaviour tests.
# None = every one: all field validations are wanted. A number caps it
# (the first ones in form order) when a form-heavy app runs too long.
REQUIRED_PER_FORM: int | None = None
RULES_PER_FORM: int | None = None
# What counts as the app saying so: apps differ, and many name only the
# first missing field. A red * by a name is the marker, not the message.
_TOLD = (
    "a message (next to the field, at the top, or a pop-up that may disappear after a "
    'few seconds), the browser\'s own prompt (such as "Please fill out this field"), or {what} '
    "flagged as not valid"
)
_LABEL_NOISE = re.compile(r"\s*(\*|\(required\))\s*$", re.I)


def plain_label(label: Any) -> str:
    """A label as people read it: "Last Name *" is "Last Name"."""
    return _LABEL_NOISE.sub("", str(label or "")).strip()


def _key(label: Any) -> str:
    """A label to match by: \"Last Name *\" and \"last name\" are one field."""
    return plain_label(label).lower()


def with_code_limits(
    fields: list[dict[str, Any]], seen: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """The model's reading of the fields plus what the page's code says about
    each (matched by label): its limits, an email type, and required."""
    by_label = {_key(f.get("label")): f for f in seen or []}
    out = []
    for field in fields:
        code = by_label.get(_key(field.get("label")))
        if not code:
            out.append(field)
            continue
        extra: dict[str, Any] = {k: str(code[k])[:200] for k in CODE_LIMITS if code.get(k)}
        if code.get("type") == "email":
            extra["type"] = "email"
        if code.get("required") is True:
            extra["required"] = True
        out.append({**field, **extra})
    return out


def _number(value: Any) -> float | None:
    try:
        return float(str(value))
    except ValueError:
        return None


def _past(value: str, by: int) -> str:
    """A number just past `value`; a date (or anything else) is described."""
    n = _number(value)
    if n is None:
        return f"a date {'before' if by < 0 else 'after'} {value}"
    n += by
    return str(int(n)) if n.is_integer() else str(n)


def message_for(field: dict[str, Any], probe: str) -> str | None:
    """The message the form showed when this field got `probe` (field_probe)."""
    for m in field.get("messages") or []:
        if m.get("probe") == probe and m.get("message"):
            return str(m["message"])
    return None




def _length_kind(short: str) -> str | None:
    """'long' / 'short' when broken_rules' short name is a length limit."""
    if short == "too many characters" or short.startswith("more than"):
        return "long"
    if short == "a single character" or short.startswith("fewer than"):
        return "short"
    return None

_PROBE_SHORT = {
    "short": "a single character",
    "long": "too many characters",
    "format": "a value in the wrong format",
    "email": "an invalid email",
    "below": "a value below its range",
    "above": "a value above its range",
}


def broken_rules(field: dict[str, Any]) -> list[tuple[str, str, str, str | None]]:
    """(what the test enters, short name, the rule, the app's own message or
    None) for each rule the field has — first the messages the form itself
    showed for a wrong value (field_probe), then the page's code, then what
    the screen says. One per kind of rule (a maxlength of 255 and "Maximum
    255 characters" are one)."""
    notes = str(field.get("notes") or "").strip()
    found: dict[str, tuple[str, str, str, str | None]] = {}

    def add(kind: str, value: str, short: str, rule: str, message: str | None = None) -> None:
        found.setdefault(kind, (value, short, rule, message))

    for m in field.get("messages") or []:
        probe, message = str(m.get("probe") or ""), str(m.get("message") or "")
        if probe in _PROBE_SHORT and message:
            add(probe, str(m.get("entered") or ""), _PROBE_SHORT[probe], message, message)

    shortest = int(_number(field.get("minlength") or 0) or 0)
    longest = int(_number(field.get("maxlength") or 0) or 0)
    if shortest > 1:
        add(
            "short",
            f"a value of only {shortest - 1} characters",
            f"fewer than {shortest} characters",
            f"at least {shortest} characters",
        )
    if longest > 0:
        add(
            "long",
            f"a value of {longest + 1} characters",
            f"more than {longest} characters",
            f"at most {longest} characters",
        )
    if low := field.get("min"):
        add("below", _past(str(low), -1), f"a value below {low}", f"{low} or more")
    if high := field.get("max"):
        add("above", _past(str(high), 1), f"a value above {high}", f"{high} or less")
    email = "an address without an @ sign (not-an-email)"
    if field.get("type") == "email":
        add("email", email, "an invalid email", "a valid email address")
    if pattern := field.get("pattern"):
        add(
            "pattern",
            f"a value that does not match the pattern {pattern}",
            "a value in the wrong format",
            f"must match {pattern}",
        )
    if m := _MIN.search(notes):
        n = int(m.group(1))
        add("short", f"a value of only {n - 1} characters", f"fewer than {n} characters", notes)
    if m := _MAX.search(notes):
        n = int(m.group(1))
        add("long", f"a value of {n + 1} characters", f"more than {n} characters", notes)
    if _EMAIL.search(notes):
        add("email", email, "an invalid email", notes)
    if _MUST.match(notes) and not found:
        add(
            "must", f"a value that breaks this rule: {notes}", "a value that breaks its rule", notes
        )
    return list(found.values())


def _test(screen: dict[str, Any], title: str, how: str, expected: str, rule: str) -> dict[str, Any]:
    name = str(screen["name"])
    return {
        "kind": "validation",
        "title": title[:200],
        "coverage": FIELD_CHECK,
        "linked_to": None,
        "signed_out": False,
        "purpose": "Checks a field rule this form shows.",
        "technique": "required field" if "required" in rule else "boundary value",
        "business_thing": screen.get("business_thing"),
        "start_screen": name,
        "steps": [f"Open {name}", how, "Press the form's save or submit button"],
        "how_to_run": f"On {name}: {how} Then press the form's save or submit button once.",
        "expected": expected,
        "trust": "standard",
        "rule": rule,
    }


def field_checks(screens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per form: everything empty, each required field left out on its own,
    and each rule a field has broken on purpose."""
    out: list[dict[str, Any]] = []
    for screen in screens:
        # Labels as people read them: "Last Name *" is "Last Name".
        fields = [
            {**f, "label": plain_label(f["label"])}
            for f in screen.get("fields") or []
            if _key(f.get("label"))
        ]
        if screen.get("kind") in SKIP_KINDS or any(
            CHANGES_PASSWORD.search(str(f["label"])) for f in fields
        ):
            continue
        name = str(screen["name"])
        # Required: marked so, or the form said so when the field was left empty.
        said = {str(f["label"]): message_for(f, "required") for f in fields}
        required = [
            str(f["label"]) for f in fields if f.get("required") is True or said[str(f["label"])]
        ]
        listed = ", ".join(required)
        messages = [f"“{said[label]}”" for label in required if said[label]]
        if required:
            out.append(
                _test(
                    screen,
                    f"Empty {name} can't be saved",
                    "Leave every field empty (clear any value already filled in).",
                    "Nothing is saved, the form stays open and the app says a required field "
                    "is missing: " + _TOLD.format(what="the missing fields") + ". Naming only "
                    f"the first missing one is fine. Required fields: {listed}."
                    + (f" The form's own messages: {', '.join(messages)}." if messages else ""),
                    f"Required fields: {listed}",
                )
            )
        if len(required) > 1:
            for label in required[:REQUIRED_PER_FORM]:
                out.append(
                    _test(
                        screen,
                        f"{label} is required on {name}",
                        f"Fill every required field ({listed}) with valid values, except "
                        f"{label}: leave it empty.",
                        f"Nothing is saved and the app shows “{said[label]}” for {label}."
                        if said[label]
                        else f"Nothing is saved and the app says {label} is required: "
                        + _TOLD.format(what=label)
                        + ".",
                        f"{label} is required",
                    )
                )
        others = f" Fill the other required fields ({listed}) with valid values." if listed else ""
        rules = [(str(f["label"]), r) for f in fields for r in broken_rules(f)]
        # Length limits: one test per form (the first field with one), not one
        # per field — 19 near-identical tests crowd out the form's behaviour.
        seen_length: set[str] = set()
        kept = []
        for label, rule in rules:
            length = _length_kind(rule[1])
            if length in seen_length:
                continue
            if length:
                seen_length.add(length)
            kept.append((label, rule))
        rules = kept
        for label, (value, short, rule, message) in rules[:RULES_PER_FORM]:
            out.append(
                _test(
                    screen,
                    f"{label} refuses {short} on {name}",
                    f"Enter {value} in {label}.{others}",
                    # The form's own message is the proof, word for word.
                    f"Nothing is saved with it and the app shows “{message}” for {label}."
                    if message
                    else f"Nothing is saved with it: {label} does not keep the value, or the "
                    f"app explains its rule ({rule}) — " + _TOLD.format(what=label) + ".",
                    f"{label}: {rule}",
                )
            )
    return out
