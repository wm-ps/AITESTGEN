"""Codegen's Inspector toolbar has an "assert" button that inserts the
assertion into the generated file as a COMMENTED-OUT line — e.g. `// await
expect(page.getByText('Welcome')).toBeVisible();` — rather than an
executable one, presumably so a human can review/delete it before it runs.
Before persisting a recording as a `TestAsset`, those lines need to become
real statements, or the assertion silently never executes and (per
`steps_parser.py`'s own `line.startswith("await ")` gate) never even shows
up in `Scenario.steps` either.

Matcher-agnostic by construction: rather than enumerating matcher names
(`toBeVisible`, `toHaveText`, `toHaveValue`, `toBeChecked`, `toHaveTitle`,
`toHaveURL`, `toHaveScreenshot`, ...) — a list Codegen's own Inspector can
extend across Playwright versions without this app's knowledge — the regex
below matches the *structural* shape Codegen always emits: `// await
expect(<anything>).<anything>(<anything>);` (optionally with a `.not.` in
the matcher chain, which falls naturally out of the non-whitespace matcher
pattern permitting internal dots), at whatever indentation the surrounding
recorded lines use. A human comment essentially never has that exact shape
starting immediately after
`// ` — `// TODO: await expect(...)` does not match, since "TODO:" sits
between `//` and `await`.

Known, accepted tradeoff: a human who writes a genuinely commented-out
`// await expect(...)...(...);` debug line in a *fresh* recording would
also get uncommented. Codegen is the only realistic source of exactly this
shape in a fresh recording, so this is accepted collateral rather than
guarded against.

Single-line only, matching `steps_parser.py`'s own same assumption
(Codegen always emits one assertion per line) — `re.MULTILINE` operates
line-by-line rather than any manual splitting.

`codegen_session.py` now passes `--target playwright-test`, whose output
already has `import { test, expect } from '@playwright/test'` — so for a
fresh recording the expect-availability step below is a no-op. It still
matters for recordings persisted before that switch, in Playwright's
STANDALONE/library format (`const { chromium } = require('playwright');
(async () => { ... })();`, from the old `--target javascript`), where
`expect` is never in scope: uncommenting an assertion alone would leave it
undefined (a real `tsc` failure: `Cannot find name 'expect'`, confirmed
live), so a require line for it is added, exactly once, only when an
assertion was actually uncommented. `spec_normalizer.py` then rewrites that
legacy shape into a `test()` anyway.
"""

import re

# `.\S+\(` (rather than an enumerated `(?:toBeVisible|toHaveText|...)`) is
# the matcher-agnostic part: it accepts *any* single dotted call chain
# after `expect(...)` — including an optional `.not.` — without knowing
# any matcher's name. Anchored on `//` immediately followed by `await
# expect(` (mod optional space) so a human comment merely mentioning
# `expect(` further into the line never matches.
_COMMENTED_ASSERTION_RE = re.compile(
    r"^(?P<indent>[ \t]*)//[ \t]*(?P<stmt>await expect\(.+\)\.\S+\(.*\);?)[ \t]*$",
    re.MULTILINE,
)

# The standalone/library format's own top-of-file line — `const { chromium }
# = require('playwright');` (or `firefox`/`webkit`, and possibly `devices`
# alongside if device emulation is used; `[^}]*` covers any of those without
# naming them). `expect`'s own require line goes right after this one.
_BROWSER_REQUIRE_RE = re.compile(r"^const \{[^}]*\} = require\(['\"]playwright['\"]\);[ \t]*$", re.MULTILINE)
_EXPECT_ALREADY_AVAILABLE_RE = re.compile(r"require\(['\"]@playwright/test['\"]\)|from ['\"]@playwright/test['\"]")
_EXPECT_REQUIRE_LINE = "const { expect } = require('@playwright/test');"


def uncomment_codegen_assertions(code: str) -> str:
    """Strips only the `// ` comment prefix Codegen adds ahead of an
    assert-toolbar-generated line — a targeted per-line substitution, not
    a reformat/reserialize of `code` (preserves indentation and every
    other line byte-for-byte). No-op if nothing matches. When at least one
    assertion is actually uncommented, also ensures `expect` is available
    (see module docstring) — never touched otherwise, so a recording with
    no assertions at all gets zero diff from this function."""
    uncommented, activated_count = _COMMENTED_ASSERTION_RE.subn(r"\g<indent>\g<stmt>", code)
    if activated_count == 0:
        return uncommented
    return _ensure_expect_available(uncommented)


def _ensure_expect_available(code: str) -> str:
    if _EXPECT_ALREADY_AVAILABLE_RE.search(code):
        return code
    match = _BROWSER_REQUIRE_RE.search(code)
    if match is None:
        return f"{_EXPECT_REQUIRE_LINE}\n{code}"
    return code[: match.end()] + "\n" + _EXPECT_REQUIRE_LINE + code[match.end() :]
