"""Turning Codegen's recorded output into the `@playwright/test` spec shape
every other `TestAsset` has — run after `uncomment_codegen_assertions` and
before the typecheck gate/`apply_auth_tag`, for both fresh recordings and
the one-off legacy conversion (`convert_legacy_recordings.py`).

Two input shapes:

- `--target playwright-test` (what `codegen_session.py` passes now):
  `import { test, expect } from '@playwright/test';` + `test('test', async
  ({ page }) => { ... });`, plus a `test.use({ storageState: '<temp path>' })`
  line when Codegen was started with `--load-storage` (authenticated mode).
  That path is a temp file inside the recording container, meaningless
  anywhere else — the exported project's `authenticated` Playwright project
  supplies `storageState` itself, so the line is dropped.
- Legacy `--target javascript` (every recording persisted before the switch):
  `const { chromium } = require('playwright');` + an `(async () => { ... })();`
  IIFE that launches its own headed browser. Codegen's template for this is
  fixed — the recorded steps always sit between `const page = await
  context.newPage();` and the `// ---------------------` separator Codegen
  writes ahead of its own `context.close()`/`browser.close()` teardown — so
  the body is sliced out by those two markers and rewrapped in a `test()`.

Idempotent: running it on its own output is a no-op.
"""

import re

_LEGACY_MARKER_RE = re.compile(r"require\(['\"]playwright['\"]\)")
_LEGACY_BODY_START_RE = re.compile(r"^\s*const page = await context\.newPage\(\);\s*$")
_LEGACY_BODY_END_RE = re.compile(r"^\s*(?://\s*-{5,}|await context\.close\(\);)\s*$")

# Codegen writes this across several lines (`test.use({\n  storageState:
# '...'\n});`); `[^}]*` spans them. Also eats the blank line after it.
_TEST_USE_STORAGE_STATE_RE = re.compile(
    r"^[ \t]*test\.use\(\{\s*storageState:[^}]*\}\);[ \t]*\n(?:[ \t]*\n)?", re.MULTILINE
)
# Codegen's own default title. Only this exact default is renamed — a title
# already set (a re-run, or anything a human edited) is left alone.
_DEFAULT_TITLE_RE = re.compile(r"""\btest\((['"])test\1\s*,""")

_PASSWORD_FILL_RE = re.compile(r"password[^\n]*\.fill\(", re.IGNORECASE)
_SUBMIT_RE = re.compile(r"\.click\(|\.press\(\s*['\"]Enter['\"]\s*\)")
_STEP_LINE_RE = re.compile(r"^[ \t]*await page\.")
_BODY_INDENT = "  "


def is_legacy_standalone_script(code: str) -> bool:
    return _LEGACY_MARKER_RE.search(code) is not None


def normalize_recorded_spec(code: str, *, name: str, requires_auth: bool) -> str:
    if is_legacy_standalone_script(code):
        code = _convert_legacy_script(code, name=name)
    code = _TEST_USE_STORAGE_STATE_RE.sub("", code)
    code = _DEFAULT_TITLE_RE.sub(lambda m: f"test({_quote(name)},", code, count=1)
    if requires_auth:
        code = _strip_recorded_login(code)
    return code


def _quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _convert_legacy_script(code: str, *, name: str) -> str:
    lines = code.splitlines()
    start = next((i for i, line in enumerate(lines) if _LEGACY_BODY_START_RE.match(line)), None)
    if start is None:
        raise ValueError("legacy recording has no `const page = await context.newPage();` line")
    end = next(
        (i for i in range(start + 1, len(lines)) if _LEGACY_BODY_END_RE.match(lines[i])), None
    )
    if end is None:
        raise ValueError("legacy recording has no Codegen teardown separator")

    body = lines[start + 1 : end]
    while body and not body[-1].strip():
        body.pop()
    while body and not body[0].strip():
        body.pop(0)

    return (
        "import { test, expect } from '@playwright/test';\n"
        "\n"
        f"test({_quote(name)}, async ({{ page }}) => {{\n"
        + "".join(f"{line}\n" for line in body)
        + "});\n"
    )


def _strip_recorded_login(code: str) -> str:
    """For an `@auth` spec, the `setup` project has already signed in (with
    the Vault credential) before this test runs — a recorded login here is
    redundant at best, and at worst persists the typed password into
    `TestAsset.code`/the exported zip. Removes everything from the first
    recorded step through the first click/Enter after the first password
    fill (the goto to the login page, the username/password fills, the
    submit). No password fill → no change.

    ponytail: a line heuristic over Codegen's text output (same "a password
    field is the login form" signal `spec_linter`/`find_login_page_evidence`
    use), not a structured action trace. A fuller version would record from
    Codegen's trace/Inspector event stream and drop login actions by the
    page they ran on rather than by matching locator text."""
    lines = code.splitlines(keepends=True)
    password_idx = next((i for i, line in enumerate(lines) if _PASSWORD_FILL_RE.search(line)), None)
    if password_idx is None:
        return code
    submit_idx = next(
        (i for i in range(password_idx + 1, len(lines)) if _SUBMIT_RE.search(lines[i])), None
    )
    if submit_idx is None:
        return code
    first_step_idx = next((i for i, line in enumerate(lines) if _STEP_LINE_RE.match(line)), None)
    if first_step_idx is None or first_step_idx > password_idx:
        return code

    remaining = lines[:first_step_idx] + lines[submit_idx + 1 :]
    next_step = next((line for line in remaining[first_step_idx:] if line.strip()), "")
    if not next_step.lstrip().startswith("await page.goto("):
        # baseURL comes from the exported playwright.config.ts.
        remaining.insert(first_step_idx, f"{_BODY_INDENT}await page.goto('/');\n")
    return "".join(remaining)
