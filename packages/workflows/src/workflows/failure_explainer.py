"""Plain-language explanations of test failures, for people who don't read
Playwright errors.

Presentation only: everything here *reads* `TestResult.error_message` and
never changes it — self-healing (`heal_policy`, HealTestActivity, the heal
endpoint) keeps seeing exactly the text it always did. The run page shows
this explanation on a "Summary" tab next to the untouched raw error.

Deterministic rules first (no cost, no latency): each recognised failure
gets a short title and one sentence on what happened, naming the element the
way a person would ("the Submit button", not a CSS selector). Anything no rule
recognises is `unknown` — the API asks the LLM about it once, cached by
`error_fingerprint`, sending only `redact_for_llm` output.

`run_root_cause` flags a run where most failures share one environment-level
cause (sign-in failed, the app didn't load, ...), so one banner can say "fix
this first" instead of the same message repeated on every test.

ponytail: English-only, and rule coverage is the Playwright messages seen so
far — a new kind of error lands in `unknown` (LLM-explained) until a rule is
added here. A fuller version would localise the strings.

Pure string/regex logic, no I/O — safe to import from workflow code and from
both the API and the execution worker.
"""

import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from workflows.heal_policy import HEAL_ASSERTION_GUARD_ERROR_PREFIX, HEAL_TYPECHECK_ERROR_PREFIX

EXPLAINED_STATUSES = frozenset({"failed", "timed_out", "errored", "cancelled"})
UNKNOWN = "unknown"


@dataclass(frozen=True)
class FailureExplanation:
    category: str
    title: str
    detail: str


@dataclass(frozen=True)
class RootCause:
    category: str
    title: str
    affected: int
    total: int


# --- Cleaning ------------------------------------------------------------------

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# The execution fixture's own retry note, appended to a real failure — internal
# machinery, never something a user should read.
_AUTH_RETRY_NOTE_RE = re.compile(r"\n*\s*(?:Error: )?AUTH_SESSION_INVALID:.*", re.DOTALL)
# Code frame lines ("  57 |  ...", "> 59 |  ...", "     |   ^") and stack lines.
_CODE_FRAME_RE = re.compile(r"^\s*(?:>\s*)?\d*\s*\|.*$", re.MULTILINE)
_STACK_LINE_RE = re.compile(r"^\s*at .*$", re.MULTILINE)


def clean_error(error_message: str | None) -> str:
    """The error with terminal colours, the internal auth-retry note, code
    frames and stack/file-path lines removed — what's left is Playwright's own
    description plus its call log."""
    if not error_message:
        return ""
    text = _ANSI_RE.sub("", error_message)
    text = _AUTH_RETRY_NOTE_RE.sub("", text)
    text = _CODE_FRAME_RE.sub("", text)
    text = _STACK_LINE_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _first_line(cleaned: str) -> str:
    line = next((ln.strip() for ln in cleaned.splitlines() if ln.strip()), "")
    line = re.sub(r"^(?:Error|TimeoutError):\s*", "", line)
    return line[:200] + ("…" if len(line) > 200 else "")


# --- Pieces pulled out of the message ------------------------------------------

_ROLE_NOUNS = {
    "button": "button",
    "link": "link",
    "textbox": "field",
    "searchbox": "search field",
    "checkbox": "checkbox",
    "radio": "option",
    "combobox": "dropdown",
    "listbox": "list",
    "option": "option",
    "heading": "heading",
    "tab": "tab",
    "menuitem": "menu item",
    "row": "table row",
    "cell": "table cell",
    "dialog": "dialog",
    "img": "image",
    "switch": "switch",
}
_QUOTED = r"""(['"`])(?P<v>(?:(?!\1).)*)\1"""
_REGEX_LITERAL = r"/(?P<rx>(?:\\/|[^/])+)/[a-z]*"


def _readable(value: str) -> str:
    # A regex literal (/^Pay Bills$/i) or plain string -> just its words.
    value = re.sub(r"\\(.)", r"\1", value)
    return value.strip("^$").strip()


def _locator_text(cleaned: str) -> str | None:
    for pattern in (
        r"^\s*Locator:\s*(.+)$",
        r"Element matched by locator (.+?) is not visible",
        r"strict mode violation:\s*(.+?) resolved to",
        r'Expect "\w+" (.+?) with timeout',
        r"waiting for (.+)$",
    ):
        match = re.search(pattern, cleaned, re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def _variable_from_code_frame(error_message: str) -> str | None:
    # "> 59 |   await submitButton.click({" -> "submitButton"
    match = re.search(
        r"^\s*>\s*\d+\s*\|\s*(?:await\s+)?(?:expect\()?\s*([A-Za-z_]\w*)",
        error_message,
        re.MULTILINE,
    )
    if not match or match.group(1) in {"page", "expect", "await", "const", "let"}:
        return None
    return match.group(1)


def _humanize_identifier(name: str) -> str:
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name).replace("_", " ").lower().split()
    return " ".join(words)


GENERIC_ELEMENT = "an element on the page"


def describe_element(error_message: str | None, cleaned: str | None = None) -> str:
    """ "the Submit button", "the Amount (USD) field", ... — falling back to
    a CSS name/id attribute, then the failing line's variable name, then to
    GENERIC_ELEMENT."""
    cleaned = clean_error(error_message) if cleaned is None else cleaned
    locator = _locator_text(cleaned) or ""
    role = re.search(rf"getByRole\(\s*{_QUOTED}", locator)
    if role:
        noun = _ROLE_NOUNS.get(role.group("v"), "element")
        name = re.search(rf"name:\s*(?:{_QUOTED}|{_REGEX_LITERAL})", locator)
        if name:
            label = _readable(name.group("v") if name.group("v") is not None else name.group("rx"))
            return f'the "{label}" {noun}'
        return f"a {noun}"
    for method, template in (
        ("getByLabel", 'the "{}" field'),
        ("getByPlaceholder", 'the "{}" field'),
        ("getByText", 'the text "{}"'),
        ("getByTestId", 'the "{}" element'),
        ("getByTitle", 'the "{}" element'),
        ("getByAltText", 'the "{}" image'),
    ):
        found = re.search(rf"{method}\(\s*(?:{_QUOTED}|{_REGEX_LITERAL})", locator)
        if found:
            value = found.group("v") if found.group("v") is not None else found.group("rx")
            return template.format(_readable(value))
    # locator('[name="coverAmount"]') / locator('#coverAmount') -> "the cover amount field"
    attribute = re.search(
        r"""\[(?:name|id|aria-label|placeholder)\s*=\s*["']?([^"'\]]+)""", locator
    ) or re.search(r"#([A-Za-z][\w-]*)", locator)
    if attribute:
        return f"the {_humanize_identifier(attribute.group(1).replace('-', '_'))} field"
    variable = _variable_from_code_frame(error_message or "")
    if variable:
        return f"the {_humanize_identifier(variable)}"
    return GENERIC_ELEMENT


def _field(cleaned: str, label: str) -> str | None:
    match = re.search(
        rf"^\s*{label}(?: string| pattern| substring)?:\s*(.+)$", cleaned, re.MULTILINE
    )
    return match.group(1).strip() if match else None


def _seconds(cleaned: str) -> str | None:
    match = re.search(r"(?:Timeout|Timed out)\s*:?\s*(\d+)\s*ms", cleaned)
    if not match:
        return None
    seconds = int(match.group(1)) // 1000
    return f"{seconds} second{'' if seconds == 1 else 's'}"


_ACTION_VERBS = {
    "click": "click",
    "dblclick": "double-click",
    "fill": "type into",
    "type": "type into",
    "pressSequentially": "type into",
    "press": "press a key in",
    "check": "tick",
    "uncheck": "untick",
    "selectOption": "choose an option in",
    "hover": "hover over",
    "setInputFiles": "upload a file to",
    "focus": "focus",
    "scrollIntoViewIfNeeded": "scroll to",
}


# --- Rules -----------------------------------------------------------------------


def explain_failure(status: str, error_message: str | None) -> FailureExplanation | None:
    """None for anything that didn't fail. Otherwise the first matching rule's
    plain title and one-sentence detail; `unknown` (no rule matched) carries
    the cleaned first line, to show until/unless the LLM explains it."""
    if status not in EXPLAINED_STATUSES:
        return None
    if status == "cancelled":
        return FailureExplanation(
            "cancelled",
            "Run cancelled",
            "This test was stopped because the run was cancelled before it finished.",
        )
    raw = error_message or ""
    cleaned = clean_error(raw)
    lowered = cleaned.lower()

    if raw.startswith((HEAL_TYPECHECK_ERROR_PREFIX, HEAL_ASSERTION_GUARD_ERROR_PREFIX)):
        return FailureExplanation(
            "heal_rejected",
            "Self-healing couldn't produce a valid fix",
            "Self-healing tried to repair this test, but its fix was rejected, so the original test was kept.",
        )
    if "failed to prepare the test project" in lowered:
        if "auth.setup" in lowered:
            return _sign_in()
        if "secret/data" in lowered or "vault" in lowered:
            return FailureExplanation(
                "credentials",
                "Couldn't load this app's saved login details",
                "Vantage couldn't read the stored login details for this application, so the test never started.",
            )
        return FailureExplanation(
            "setup",
            "Couldn't set up the test run",
            "Vantage couldn't prepare the test project for this run, so the test never started.",
        )
    if "its setup dependency likely failed" in lowered:
        return _sign_in()
    if any(
        marker in lowered
        for marker in (
            "playwright produced no parseable json report",
            "test did not complete (activity failed after retries)",
            "playwright report contained no suite matching",
        )
    ):
        return FailureExplanation(
            "internal",
            "The test stopped because of a problem in Vantage",
            "Something went wrong in Vantage while running this test — it isn't a problem with your app.",
        )
    if "exceeded the execution timeout" in lowered:
        return FailureExplanation(
            "too_long",
            "The test took too long and was stopped",
            "The whole test ran for more than 8 minutes, so Vantage stopped it.",
        )
    if "page.goto:" in lowered or "failed to load page" in lowered or "net::err_" in lowered:
        seconds = _seconds(cleaned)
        status_code = re.search(r"HTTP status:\s*(\d{3})", cleaned)
        if status_code:
            detail = (
                f"The app answered with an error (HTTP {status_code.group(1)}) instead of the page."
            )
        elif seconds:
            detail = f"The page didn't finish loading within {seconds}."
        else:
            detail = "The page couldn't be opened."
        return FailureExplanation("page_load", "The page didn't load", detail)

    element = describe_element(raw, cleaned)
    named = element != GENERIC_ELEMENT
    expected = _field(cleaned, "Expected")
    received = _field(cleaned, "Received")
    seconds = _seconds(cleaned)
    waited = f"waited {seconds}" if seconds else "waited"
    not_found = "element(s) not found" in lowered

    if "tohaveurl" in lowered:
        if expected and received:
            detail = f"It expected to be on {expected}, but the app showed {received}."
        else:
            detail = "The app didn't go to the page the test expected."
        return FailureExplanation("wrong_page", "Ended up on the wrong page", detail)
    if "tobevisible" in lowered or "is not visible even after" in lowered:
        reason = "it couldn't be found on the page" if not_found else "it didn't appear"
        if named:
            return FailureExplanation(
                "not_visible",
                f"Expected {element} to be on screen",
                f"The test {waited} for {element} to show, but {reason}.",
            )
        return FailureExplanation(
            "not_visible",
            "Something the test expected wasn't on screen",
            f"The test {waited} for something to show on the page, but {reason}.",
        )
    if "tohavetext" in lowered or "tocontaintext" in lowered:
        subject = element if named else "an element"
        if not_found:
            detail = (
                f"It expected {subject} to say {expected}, but it wasn't on the page."
                if expected
                else f"{subject.capitalize()} wasn't on the page."
            )
        elif expected and received:
            detail = f"It expected {subject} to say {expected}, but it said {received}."
        else:
            detail = f"{subject.capitalize()} didn't show the text the test expected."
        return FailureExplanation("wrong_text", "The page showed different text", detail)
    if "tohavevalue" in lowered and expected is not None and received is not None:
        subject = element if named else "a field"
        return FailureExplanation(
            "wrong_value",
            "A field had a different value",
            f"It expected {subject} to contain {expected}, but it had {received}.",
        )
    if "tohavecount" in lowered and expected is not None and received is not None:
        return FailureExplanation(
            "wrong_value",
            "Found a different number of items",
            f"The test expected {expected} matching items on the page, but found {received}.",
        )
    if (
        re.search(r"expect\([^)]*\)\.(?:not\.)?to(?:Have|Be|Equal|Contain|Match)", cleaned)
        or "expect(received)" in lowered
    ):
        if expected is not None and received is not None:
            detail = f"It expected {expected}, but got {received}."
        else:
            detail = "A value on the page wasn't what the test expected."
        return FailureExplanation("wrong_value", "A check didn't match", detail)
    strict = re.search(r"strict mode violation.*?resolved to (\d+) elements", cleaned, re.DOTALL)
    if strict:
        target = element if named else "what the test was looking for"
        return FailureExplanation(
            "multiple_matches",
            "Found more than one match",
            f"{strict.group(1)} things on the page matched {target}, so the test couldn't tell which one to use.",
        )
    action = re.search(r"locator\.(\w+): Timeout", cleaned)
    if action:
        verb = _ACTION_VERBS.get(action.group(1), "use")
        if named:
            return FailureExplanation(
                "action_timeout",
                f"Couldn't {verb} {element}",
                f"The test {waited} for {element}, but it never appeared or wasn't ready to use.",
            )
        return FailureExplanation(
            "action_timeout",
            f"Couldn't {verb} an element on the page",
            f"The test {waited} for the element it needed, but it never appeared or wasn't ready to use.",
        )
    if not_found or "locator not found" in lowered or "element not found" in lowered:
        if named:
            return FailureExplanation(
                "not_found",
                f"Couldn't find {element}",
                f"{element.capitalize()} wasn't on the page when the test looked for it.",
            )
        return FailureExplanation(
            "not_found",
            "Couldn't find what the test was looking for",
            "The element the test needed wasn't on the page.",
        )

    first = _first_line(cleaned)
    return FailureExplanation(UNKNOWN, first or "The test failed", "")


def _sign_in() -> FailureExplanation:
    return FailureExplanation(
        "sign_in",
        "Couldn't sign in to the app",
        "Vantage couldn't log in to the application with the saved credentials, so the test never started.",
    )


# --- Run-level root cause ----------------------------------------------------------

# Causes that sit outside any one test — when they dominate a run, fixing the
# cause fixes the run. Assertion/element failures are test-specific and an
# `unknown` (AI-explained) one isn't certain enough, so neither ever qualifies.
# Standalone phrases — shown as "N of M failed tests have the same cause —
# <title>." (email) and as a banner line (run page).
_SHARED_CAUSES = {
    "credentials": "This app's saved login details couldn't be loaded",
    "sign_in": "Vantage couldn't sign in to the app",
    "setup": "The test run couldn't be set up",
    "internal": "A problem in Vantage stopped the tests",
    "page_load": "The app's pages didn't load",
}
ROOT_CAUSE_MIN_SHARE = 0.6
ROOT_CAUSE_MIN_COUNT = 3


def run_root_cause(categories: Iterable[str]) -> RootCause | None:
    """`categories`: one per failed/errored/timed-out result of a run.
    Conservative on purpose — one shared cause must cover at least 60% of the
    failures and at least 3 of them."""
    categories = list(categories)
    shared = [c for c in categories if c in _SHARED_CAUSES]
    if not shared:
        return None
    category, affected = Counter(shared).most_common(1)[0]
    total = len(categories)
    if affected < ROOT_CAUSE_MIN_COUNT or affected / total < ROOT_CAUSE_MIN_SHARE:
        return None
    return RootCause(category, _SHARED_CAUSES[category], affected, total)


# --- LLM fallback support (the API makes the call; nothing here does I/O) --------

_KEY_VALUE_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|apikey|authorization|cookie|session(?:id|_id)?)"
    r"(\s*[\"']?\s*[:=]\s*)([\"']?)[^\s\"',;&)]+"
)
_TYPED_VALUE_RE = re.compile(r"\b(fill|type|pressSequentially|press)\(\s*(['\"`])(?:(?!\2).)*\2")
_URL_USERINFO_RE = re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@")
_URL_QUERY_RE = re.compile(r"(https?://[^\s\"'?#]+)\?[^\s\"'#]*")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_OPAQUE_RE = re.compile(
    r"\b(?=[A-Za-z0-9+/_=-]*\d)(?=[A-Za-z0-9+/_=-]*[A-Za-z])[A-Za-z0-9+/_=-]{24,}\b"
)
_LONG_NUMBER_RE = re.compile(r"\d{8,}")
LLM_INPUT_MAX_CHARS = 2000


def redact_for_llm(text: str, known_secrets: Iterable[str] = ()) -> str:
    """What may leave Vantage: typed values, this app's own saved login, URL
    credentials and query strings, secret-looking key=value pairs, bearer
    tokens/JWTs/long opaque strings, emails and long digit runs are all
    replaced with [redacted]. Truncated to LLM_INPUT_MAX_CHARS."""
    for secret in sorted((s for s in known_secrets if s and len(s) >= 3), key=len, reverse=True):
        text = text.replace(secret, "[redacted]")
    text = _TYPED_VALUE_RE.sub(lambda m: f"{m.group(1)}({m.group(2)}[redacted]{m.group(2)}", text)
    text = _URL_USERINFO_RE.sub(r"\1[redacted]@", text)
    text = _URL_QUERY_RE.sub(r"\1?[redacted]", text)
    # Before key=value: "Authorization: Bearer <token>" — the key=value rule
    # alone would redact only the word "Bearer" and leave the token.
    text = _BEARER_RE.sub("Bearer [redacted]", text)
    text = _KEY_VALUE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}[redacted]", text)
    text = _JWT_RE.sub("[redacted]", text)
    text = _EMAIL_RE.sub("[redacted]", text)
    text = _OPAQUE_RE.sub("[redacted]", text)
    text = _LONG_NUMBER_RE.sub("[redacted]", text)
    return text[:LLM_INPUT_MAX_CHARS]


def error_fingerprint(redacted: str) -> str:
    """Cache key for an LLM explanation — the redacted text with numbers
    normalised, so the same error at a different duration/line/port isn't a
    new call (and the key never derives from a raw secret)."""
    normalised = re.sub(r"\d+", "0", re.sub(r"\s+", " ", redacted)).strip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


UNDETERMINED_TITLE = "The test failed for a reason Vantage couldn't identify"
UNDETERMINED_DETAIL = "See the Raw error tab for the full details."
