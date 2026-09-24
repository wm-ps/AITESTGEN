"""Deterministic, non-LLM parser: Codegen's generated source -> human-
readable `Scenario.steps` phrases (plan §6). Display metadata only — never
consumed at execution time, and a miss here must never block saving; the
generic fallback phrase covers any line this doesn't recognize, and
`TestAsset.code` (the file content itself) is the sole source of truth for
what actually runs.

Regex over Codegen's own limited, consistent output vocabulary — the same
kind of heuristic-over-code approach `generation_worker.spec_linter`
already uses elsewhere in this codebase, just mapping to a phrase instead
of a warning.
"""

import re

_FALLBACK_PHRASE = "Perform recorded action"

_LOCATOR_RE = re.compile(
    r"getBy(?P<kind>Role|Label|Text|Placeholder|TestId|AltText|Title)\(\s*"
    r"(?:['\"](?P<role>\w+)['\"]\s*,\s*)?"
    r"(?:\{[^}]*?name:\s*['\"](?P<name>[^'\"]+)['\"][^}]*\}|['\"](?P<lit>[^'\"]+)['\"])?"
)

_GOTO_RE = re.compile(r"\.goto\(\s*['\"](?P<url>[^'\"]+)['\"]")
_CLICK_RE = re.compile(r"\.click\(")
_DBLCLICK_RE = re.compile(r"\.dblclick\(")
_FILL_RE = re.compile(r"\.fill\(\s*['\"](?P<value>[^'\"]*)['\"]")
_TYPE_RE = re.compile(r"\.(?:type|pressSequentially)\(\s*['\"](?P<value>[^'\"]*)['\"]")
_CHECK_RE = re.compile(r"\.check\(")
_UNCHECK_RE = re.compile(r"\.uncheck\(")
_SELECT_RE = re.compile(r"\.selectOption\(\s*['\"](?P<value>[^'\"]+)['\"]")
_PRESS_RE = re.compile(r"\.press\(\s*['\"](?P<key>[^'\"]+)['\"]")

_EXPECT_VISIBLE_RE = re.compile(r"expect\(.*?\)\.toBeVisible\(")
_EXPECT_HIDDEN_RE = re.compile(r"expect\(.*?\)\.toBeHidden\(")
_EXPECT_TEXT_RE = re.compile(
    r"expect\(.*?\)\.(?:toHaveText|toContainText)\(\s*['\"](?P<value>[^'\"]+)['\"]"
)
_EXPECT_VALUE_RE = re.compile(r"expect\(.*?\)\.toHaveValue\(\s*['\"](?P<value>[^'\"]+)['\"]")
_EXPECT_URL_RE = re.compile(r"expect\(.*?\)\.toHaveURL\(")


def _locator_description(line: str) -> str | None:
    m = _LOCATOR_RE.search(line)
    if not m:
        return None
    return m.group("name") or m.group("lit") or m.group("role")


def _phrase_for_line(line: str) -> str | None:
    m = _GOTO_RE.search(line)
    if m:
        return f"Navigate to {m.group('url')}"

    desc = _locator_description(line)

    m = _FILL_RE.search(line) or _TYPE_RE.search(line)
    if m:
        target = f" into {desc!r}" if desc else ""
        return f"Fill in {m.group('value')!r}{target}"

    if _SELECT_RE.search(line):
        m = _SELECT_RE.search(line)
        assert m is not None
        target = f" in {desc!r}" if desc else ""
        return f"Select {m.group('value')!r}{target}"

    if _CHECK_RE.search(line):
        return f"Check {desc!r}" if desc else "Check the box"
    if _UNCHECK_RE.search(line):
        return f"Uncheck {desc!r}" if desc else "Uncheck the box"

    if _DBLCLICK_RE.search(line):
        return f"Double-click {desc!r}" if desc else "Double-click"
    if _CLICK_RE.search(line):
        return f"Click {desc!r}" if desc else "Click"

    m = _PRESS_RE.search(line)
    if m:
        return f"Press {m.group('key')}"

    m = _EXPECT_TEXT_RE.search(line)
    if m:
        return f"Assert text equals {m.group('value')!r}"
    m = _EXPECT_VALUE_RE.search(line)
    if m:
        return f"Assert value equals {m.group('value')!r}"
    if _EXPECT_VISIBLE_RE.search(line):
        return f"Assert {desc!r} is visible" if desc else "Assert element is visible"
    if _EXPECT_HIDDEN_RE.search(line):
        return f"Assert {desc!r} is hidden" if desc else "Assert element is hidden"
    if _EXPECT_URL_RE.search(line):
        return "Assert the page URL"

    return None


def parse_steps(code: str) -> list[str]:
    """One phrase per recognized statement line, in source order; an
    unrecognized-but-clearly-an-action line (contains `await page.` or
    `await expect(`) still gets the generic fallback phrase rather than
    being silently dropped, so the step count stays a reasonable proxy for
    what the recording actually did."""
    steps: list[str] = []
    for raw_line in code.splitlines():
        line = raw_line.strip()
        if not line.startswith("await "):
            continue
        phrase = _phrase_for_line(line)
        if phrase is None and ("page." in line or "expect(" in line):
            phrase = _FALLBACK_PHRASE
        if phrase is not None:
            steps.append(phrase)
    return steps
