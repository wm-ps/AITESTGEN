"""HostedAIProvider — the first real `AIProvider` adapter (Story 2.6, AD-3).

Backed by a LiteLLM proxy server (not the `litellm` SDK) reached over HTTP —
no AI vendor is named in the PRD or Architecture Spine; the proxy owns
provider routing/credentials entirely, so this file only ever speaks one
OpenAI-compatible `/chat/completions` shape. `AI_MODEL` is the proxy's model
alias, not a code change — this is what lets a future vendor/model swap
touch only proxy config, never this file (AD-3).

Reads canonical `Page` rows (Story 2.5's Application Model), each optionally
carrying transient `.forms`/`.components`/`.api_endpoints`/
`.outgoing_transitions`/`.assertions` attributes that `InferenceActivity`
attaches before calling this — richer context than a bare page URL, but this
provider tolerates their absence (`getattr(..., [])`) so it stays usable
against a plain `list[Page]` in isolation (e.g. tests).

Requires `LITELLM_BASE_URL` and `LITELLM_API_KEY` (the proxy's own virtual
key, not a vendor key). `CustomerEndpointAIProvider` (on-prem) has no story
to build it in — Epic 7 is removed; not built here or anywhere else without
a fresh product decision.
"""

import base64
import json
import logging
import os
import re
from typing import Any

import httpx
from domain import Journey, Page, Scenario

from ai_provider.journey_candidate import JourneyCandidate, JourneyCandidateStep
from ai_provider.live_exploration_decision import LiveExplorationDecision
from ai_provider.scenario_candidate import ScenarioCandidate, TestDataFieldCandidate
from ai_provider.test_asset_code import TestAssetCode
from ai_provider.test_case_prompt_candidate import TestCasePromptCandidate

AI_MODEL = os.environ.get("AI_MODEL", "anthropic/claude-sonnet-5")
LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
# Low, near-deterministic — these calls extract structured data or follow
# prescriptive rules, not creative writing. Some proxy-routed models (e.g.
# reasoning models) reject any non-default temperature — set AI_TEMPERATURE=""
# to omit the field entirely and let the model use its own default.
_AI_TEMPERATURE_RAW = os.environ.get("AI_TEMPERATURE", "0.2")
AI_TEMPERATURE = float(_AI_TEMPERATURE_RAW) if _AI_TEMPERATURE_RAW else None

logger = logging.getLogger(__name__)

# AC1 backstop: a Journey name must be business language, never a raw route/
# page identifier — this regex only catches the obvious case (starts with a
# path separator, or is bare host/URL-shaped); it's a defensive net behind
# prompting, not the primary enforcement mechanism.
_ROUTE_SHAPED_NAME = re.compile(r"^(/|https?://)")

_PROMPT_SYSTEM = """You are analyzing a structured Application Model (canonical pages, their \
forms, automatable components, API calls, and how users actually navigate between \
pages) discovered from a web application, to identify the underlying business \
workflows ("Journeys") a QA engineer would care about.

Each page's "outgoing_transitions" lists the URLs a user actually reached from it \
during crawling (a real navigation path, not a guess) — use this to sequence pages \
into a Journey, not just their titles or URLs.

Group these pages into candidate Journeys, each as an ORDERED sequence of steps in \
the order a user actually moves through the flow. Each Journey needs:
- "name": a short business-language name (e.g. "Add item to list") — never a raw \
route or page identifier
- "capability_name": the broader business capability this Journey belongs to \
(e.g. "Item Management")
- "description": one or two plain-language sentences summarizing what this Journey \
covers and why a QA engineer would care about testing it
- "steps": an ordered list of {{"page_index": <int>, "stage_label": "<short \
business-language stage name, e.g. \\"Login\\" or \\"MFA Verification\\">"}} — one \
entry per page (from the indexed list above) that supports this Journey, in flow order

Respond with ONLY a JSON object of this shape, no prose: \
{{"journeys": [{{"name": "...", "capability_name": "...", "description": "...", "steps": [ \
{{"page_index": 0, "stage_label": "..."}}, {{"page_index": 2, "stage_label": "..."}}]}}, ...]}}"""

_PROMPT_USER = """Pages (indexed):
{page_listing}"""


def _describe_form(form) -> dict:
    # `.fields` is transient, attached by `scenario_generation_activity`
    # (generation_worker/activities.py) the same way `.forms`/`.api_endpoints`
    # are attached below — absent during `infer_journeys`, where a form's
    # action_url alone is enough to sequence pages into a Journey.
    fields = [
        {
            "name": field["name"],
            # rule_type kept alongside value (not just the value alone) so
            # the model can tell a hard constraint ("required") from an
            # informational one ("html5_message") rather than guessing.
            "validation_rules": [
                {"rule_type": rule["rule_type"], "value": rule["value"]}
                for rule in field["rules"]
            ],
        }
        for field in getattr(form, "fields", [])
        if field["rules"]
    ]
    return {"action_url": form.action_url, "fields": fields} if fields else form.action_url


def _describe_page(page: Page) -> str:
    components = [f"{c.type}:{c.name}" for c in getattr(page, "components", [])]
    forms = [_describe_form(f) for f in getattr(page, "forms", [])]
    api_calls = [f"{e.method} {e.path}" for e in getattr(page, "api_endpoints", [])]
    outgoing_transitions = [t.url for t in getattr(page, "outgoing_transitions", [])]
    assertions = [
        f"{a.kind}:{a.expected_value}" for a in getattr(page, "assertions", [])
    ]
    description = {
        "url": page.url,
        "title": page.title,
        "components": components,
        "forms": forms,
        "api_calls": api_calls,
        "outgoing_transitions": outgoing_transitions,
        "assertions": assertions,
    }
    # Story 4.1: ScenarioGenerationActivity attaches each step's business
    # stage label the same way InferenceActivity attaches forms/components
    # above — present only when the page is being described as a Journey
    # step (generate_scenarios), absent during infer_journeys.
    stage_label = getattr(page, "stage_label", None)
    if stage_label is not None:
        description["stage_label"] = stage_label
    return json.dumps(description)


def _describe_captured_flow(captured_flow: list[dict] | None) -> str:
    """Renders `Journey.captured_flow` (the literal, ordered live-exploration
    transcript — see `LiveExploreActivity`) as a numbered listing for
    `generate_scenarios`'s prompt. Empty for a crawler/discovery Journey,
    which never sets this column."""
    if not captured_flow:
        return ""
    lines = []
    for i, step in enumerate(captured_flow):
        parts = [step.get("tool_name", "")]
        if step.get("element_description"):
            parts.append(f'on "{step["element_description"]}"')
        if step.get("typed_value"):
            parts.append(f'typed "{step["typed_value"]}"')
        if step.get("page_url"):
            parts.append(f'(page: {step.get("page_heading") or step["page_url"]})')
        if step.get("rationale"):
            parts.append(f'— {step["rationale"]}')
        lines.append(f"{i + 1}: {' '.join(parts)}")
    return "\n".join(lines)


# A single "generate everything for this Journey" call let the model's own
# output budget silently cap the whole response (observed: a large "digital
# banking" Journey stopped at 40 Scenarios with no error). Splitting by
# Scenario type bounds each call's output separately and isolates a
# truncated/failed type instead of losing the whole Journey's Scenarios.
_SCENARIO_TYPE_DESCRIPTIONS = {
    "happy": "ONLY Happy Path Scenarios — the successful, intended way a user completes this "
    "Journey.",
    "negative": "ONLY Negative Path Scenarios — every validation/error condition a QA engineer "
    "would want covered (e.g. missing required field, invalid format, expired/declined input). "
    "When a field lists \"validation_rules\" (each a {rule_type, value}), ground that condition's "
    "steps/expected_result in the actual rule_type and value captured — e.g. quote an "
    "\"html5_message\" value verbatim as the expected error text — rather than inventing generic "
    "wording; only invent wording for a condition with no captured rule.",
    "edge": "ONLY Edge Case Scenarios — boundary/unusual-but-valid conditions distinct from "
    "both the happy path and plain validation errors (e.g. a boundary value, a race condition, "
    "an unusual but legitimate input).",
}

# Used only when the user's own prompt didn't state an explicit count for
# this type (see `TestCasePromptCandidate.requested_scenario_counts`) — an
# exact count overrides this with "Generate EXACTLY N ..." instead.
_SCENARIO_TYPE_DEFAULT_COUNT_GUIDANCE = {
    "happy": "Usually just one; include more only if there are genuinely distinct successful "
    "paths through this Journey (e.g. two different valid ways to reach the same outcome).",
    "negative": "Cover each meaningfully distinct failure condition implied by the captured "
    "forms/fields; do not pad with near-duplicate variations of the same condition.",
    "edge": "Cover each meaningfully distinct edge condition implied by the captured "
    "forms/fields; do not pad with near-duplicates.",
}

_SCENARIO_PROMPT_SYSTEM = """You are writing integration test Scenarios for a specific business \
Journey in a web application, based on its discovered steps and the underlying captured \
pages/forms/API calls.

Generate {scenario_type_instructions} Each \
Scenario needs:
- "name": a short business-language name (e.g. "Guest checkout with an expired card")
- "type": one of "happy", "negative", "edge"
- "steps": an ordered list of plain-language test steps a QA engineer would follow
- "expected_result": what should happen if the Scenario passes
- "test_data": a list of {{"name": "<field name, e.g. \\"card number\\">", "mandatory": <bool>}} \
— the input values a human tester must supply to run this Scenario (e.g. a card number, an \
expected confirmation value, a new/candidate value a form under test is checking). Do NOT \
include a value — only the field name and whether it's required; a reviewer supplies the \
actual value later. Exception: never include a field for the account's own existing login \
username/password (whether this Scenario's own subject or just a precondition to reach it) \
— that value always comes from the credentials the user already configured for this run, \
never from a Scenario's test_data. A field that is itself a NEW/candidate value under test \
(e.g. "new password", "confirm password" on a change-password form) is not covered by this \
exception and should still be listed normally.

Recorded live session rule — when a "Recorded live browser session" transcript is given below, \
it is the literal, ground-truth record of what actually happened against the real application \
for this Journey — every scenario step must name only elements/pages/values that appear in it \
(or in the Journey's own request text above); never invent a UI element (e.g. a "settings" \
button, a page, a dialog) that isn't evidenced by either. A negative/edge Scenario may still \
describe an action the recorded session didn't itself take (e.g. submitting the same form with \
an invalid value instead of the valid one that was actually typed) — ground the SURROUNDING \
navigation/element steps in the transcript, only vary the specific input under test.

Grounded-outcome rule — Discovery never captures a page's visual layout or presentation \
mechanism (whether results render as a table, a list, cards, or plain text; whether an error \
shows in an alert/toast/modal or as an inline message next to a field) — only its pages, \
forms, fields, buttons/links, and API calls, given to you above. Never describe "steps"/ \
"expected_result" in terms of a SPECIFIC UI mechanism you weren't given evidence for (e.g. \
"results appear in a table", "a confirmation alert is shown", "a modal dialog opens"). \
Describe the outcome in application-agnostic terms instead — what changes or becomes visible, \
not how it's presented — e.g. "the result is displayed" rather than "shown in a table", "the \
user is notified of the error" rather than "an alert appears". Only name a specific mechanism \
if it's actually evidenced by a captured component/assertion given to you above.

Respond with ONLY a JSON object of this shape, no prose: \
{{"scenarios": [{{"name": "...", "type": "happy", "steps": ["...", "..."], \
"expected_result": "...", "test_data": [{{"name": "...", "mandatory": true}}]}}, ...]}}"""

_SCENARIO_PROMPT_USER = """Journey: "{journey_name}"
{journey_description_section}
Steps (in order — each is a business-language stage of this Journey, with the captured \
page/form/API/component detail behind it):
{step_listing}
{live_session_section}"""

_PLAYWRIGHT_PROMPT_USER = """Application base URL: {base_url}

Scenario: "{scenario_name}" ({scenario_type})

Test steps:
{step_listing}

Expected result: {expected_result}

Test data (use these exact values in the generated code, they are already resolved — \
either reviewer-provided or a sensible default):
{test_data_listing}

Known pages (real URLs discovered on this application during crawling, listed as \
"business stage name -> URL"). When a step navigates to, or asserts being on, a page \
matching one of these, use `page.goto("<url>")` / assert against this exact URL — only \
invent your own URL for a step with no match here:
{known_pages_listing}

Known element locators (real locators discovered on this application, listed as "business \
stage name / component type:component name -> locator"). When a step interacts with an \
element matching one of these, use the locator exactly as shown — most entries are a literal \
`page.locator("<selector>")` selector string, use it verbatim; an entry already shown as \
`getByLabel("<text>")` is a ready-to-use `page.getByLabel(...)` call, not a `page.locator(...)` \
selector string — call it directly, do NOT wrap it as `page.locator('getByLabel("...")')` or \
as `page.locator('label="..."')` (`label=` is not a real Playwright selector engine). Only \
invent your own locator (e.g. `page.getByRole(...)`) for an element with no match here.

Exception — do NOT trust a known locator for a form-field component (input/select/textarea) \
whose value is an internal name/id/model-property string rather than real human-readable text \
(e.g. `text="txtUserName"`, `getByLabel("model.email")`). An input/select/textarea never \
renders its internal name as visible text and never has that string as its accessible label, \
so that locator will never resolve — it is discovery-crawl noise, not a real selector/label. \
Ignore it and build the field's locator yourself following the Locator rules below instead.

Exception — do NOT use a known `role=<role>[name="..."]` locator's full quoted `name` as an \
exact match when that name is visibly a concatenation of multiple fragments: an icon/emoji, \
a stable entity/title fragment, a dynamic figure (price, date, count, rating), and/or a \
decorative arrow/chevron glyph (e.g. `role=link[name="🏥\nHealth Plan\nFrom ₹ 12,500/yr · Up \
to ₹50 L cover\n›"]`). That figure changes between runs/environments and the icon/chevron are \
noise, so an exact match on the full string is guaranteed to break. Instead extract only the \
stable entity-name fragment and match it with `getByRole(...)` using a partial/regex `name`, \
e.g. `page.getByRole('link', {{ name: /Health Plan/ }})`. This applies to any card, list item, \
or dashboard tile whose accessible name mixes an icon/title/dynamic-value/chevron this way — \
not just this one example. It also applies to an ordinary icon button: a leading/trailing \
icon glyph (e.g. a "+"/plus, pencil, or trash icon rendered as an `<img>`/`<svg>` sibling \
inside the `<button>`) contributes its own alt text/aria-label to the button's ONE computed \
accessible name, concatenated with the visible label — a human reading the button only sees \
the icon and the word "Add connection", but the browser's accessible name is literally "plus \
Add connection". A known locator captured as `role=button[name="plus Add connection"]` must \
still be matched with `getByRole('button', {{ name: /Add connection/ }})`, never `{{ name: \
'Add connection', exact: true }}` (which matches zero elements) or the literal full string \
with the icon word included (fragile the moment the icon's own alt text changes).

Exception — when calling `getByLabel(...)`/`getByText(...)` with a plain string (no regex), \
always pass `{{ exact: true }}` as well, unless the step genuinely needs a partial/substring \
match. Playwright's default is substring matching, so a shorter known label that is itself a \
substring of a longer one on the same page (e.g. "New password" vs. "Confirm new password", \
"Amount" vs. "Loan Amount") resolves to BOTH elements and fails with a strict-mode violation \
instead of the one you meant. `page.getByLabel("New password", {{ exact: true }})` — never a \
bare `page.getByLabel("New password")` — is what actually isolates the field you want.
{known_locators_listing}{failure_context}{live_inspection_context}{live_action_sequence_context}"""

_PLAYWRIGHT_FAILURE_CONTEXT = """

Prior attempt failed and needs to be fixed. Make the SMALLEST change that
addresses the specific problem below — do not rewrite unrelated parts of
the test, and preserve its original intent, structure, and assertions
except where the failure requires changing them.

--- previous code ---
{previous_code}
--- target URL at time of failure ---
{target_url}
--- error ---
{failure_error_message}
--- stack trace ---
{failure_stack_trace}
--- console output ---
{failure_console_output}

If, after all of the above, you still cannot confidently identify the
correct current locator or root cause (the evidence doesn't tell you what
changed on the page), respond with the single line `NEEDS_LIVE_INSPECTION`
as the very first line of your response, then your best-effort fix below
it as normal. A real browser will inspect the current page and you will
get another attempt with that fresh evidence — use this sparingly, only
when you are genuinely blocked, not as a default reflex."""

# Used instead of _PLAYWRIGHT_FAILURE_CONTEXT when a reviewer edited this
# Scenario's test_data from the Test Suite page and the existing TestAsset
# needs its literal values updated to match — never a failure/diagnosis
# situation, so this deliberately carries none of that framing (no error/
# stack trace/console output, no NEEDS_LIVE_INSPECTION escape hatch).
_PLAYWRIGHT_DATA_UPDATE_CONTEXT = """

This test already exists and its logic is correct. Its test data changed —
make the SMALLEST change that reflects the new value(s) below: update ONLY
the literal(s) in the code that correspond to these field(s). Do not change
selectors, assertions, control flow, navigation, or any other part of the
test, and do not "improve" or restructure anything else.

--- existing code ---
{previous_code}
--- changed test data ---
{changed_data_listing}"""

# Only ever populated during a heal attempt (previous_code is not None) AND
# only when a live inspection actually ran for this attempt — most heal
# attempts never trigger one (the deterministic locator-failure classifier
# in execution_worker gates it), so this is usually "".
_PLAYWRIGHT_LIVE_INSPECTION_CONTEXT = """

## Live Page Inspection (current DOM state, captured just now)
A real browser was launched and navigated to the failing page using this
test's own authenticated session. These locator candidates were observed
on the page at the time of this heal attempt — more reliable than the
possibly-stale known locators above when they disagree:

{live_locator_listing}"""

_PLAYWRIGHT_LIVE_ACTION_SEQUENCE_CONTEXT = """

## Live Exploration — Ordered Action Sequence (observed on the real, current application)
This is the EXACT, ORDERED sequence of interactions actually needed against the real,
current application — the final entry is the actual target, but an earlier entry is very
often a PREREQUISITE (opening a dropdown/menu/accordion/tab) that must happen first before
the target becomes visible or interactable at all. Do not assume the target is directly
interactable on its own — replicate this ENTIRE sequence, in this exact order, in the
generated code. This sequence only tells you WHAT to interact with and in what ORDER —
every one of these interactions, including intermediate/prerequisite ones, must still be
resolved via `page.getByRole(...)`/etc. and routed through `ensureVisible` exactly like any
other interaction in this test, never a raw, unwrapped `.hover()`/`.click()`/`.fill()` call
just because it came from this sequence:

{action_sequence_listing}"""

_PLAYWRIGHT_PROMPT_SYSTEM = """You are converting one integration test Scenario into a single, \
executable Playwright (TypeScript, @playwright/test) test.

Write one complete, runnable test using `import {{ test, expect }} from '@playwright/test'`, \
following the steps in order and asserting the expected result. Use the given test data \
values literally where they'd naturally be used (form fields, query params, etc) — except \
where the Input-type fill rule, Credential rule, or Data-uniqueness rule below require \
reformatting, sourcing from an environment variable, or appending a unique suffix instead.

Input-type fill rule — before calling `.fill(...)`, match the value's format to the field's \
actual input type. A native `<input type="date">` (and `type="month"`/`type="week"`/ \
`type="time"`) only accepts its own format via `.fill(...)` — e.g. `YYYY-MM-DD` for a date \
input — a human-readable string like "Jan 5, 2026" is silently rejected by the browser and \
leaves the field empty. Reformat the given literal to match that specific input's required \
format; never reuse one generic string across fields of different native input types.

Credential rule — this exported project centralizes login in `tests/auth.setup.ts`, which logs \
in once and saves the resulting session as Playwright `storageState`; every `@auth`-tagged test \
(the generated file lives two directories below the exported project's root, at \
tests/<suite>/<name>.spec.ts) already starts with that session applied, before this test's body \
even runs. {auth_precondition_note}
Only write login fill/click steps at all when the Scenario is itself testing the login form's \
own behavior (e.g. asserting a login error, or a genuine login-success assertion that is the \
Scenario's whole point) — never merely to reach some other page as a precondition. Even then:
- Navigate to the real login page URL first (see Known pages above for it) — never the \
application's base URL, and never assume `/` is where the login form lives.
- Prefer the shared helper for the actual submit, so the login flow itself is defined in one \
place, not duplicated per spec (support/ is reached via '../../support/...' from this file, not \
'../support/...'):
import {{ fillCredentials }} from '../../support/auth';
// ...
await fillCredentials(page);
- If the assertion itself needs the literal credential values (e.g. constructing an \
intentionally wrong password), source them from the shared registry instead of hardcoding a \
string or reading `process.env` yourself:
import {{ CREDENTIALS }} from '../../support/config';
// ...
const username = CREDENTIALS.username;
const password = CREDENTIALS.password;
- If this Scenario's Test data above gives an explicit password value (e.g. testing a length \
or Unicode/character-set boundary the Scenario's own name describes), pass it explicitly as \
`fillCredentials`'s third argument instead of calling `fillCredentials(page)` bare — the bare \
call always submits the shared registry's default password, never this Scenario's specific one:
await fillCredentials(page, CREDENTIALS.username, '<the exact password value from Test data above>');
- Never call `.fill(...)` with a literal string on the username field, or on a password field \
representing the account's OWN existing/current password (the login page's password field, or \
a change-password form's "current password" field) — always source that value from CREDENTIALS \
as above, even in a test that also calls `fillCredentials()` elsewhere; never fill it twice with \
two different sources. A change-password form's "new password"/"confirm password" fields are \
different — those ARE the candidate value this Scenario is testing, so fill them with the exact \
literal from Test data, not CREDENTIALS.

Data-uniqueness rule — for a step that creates a new account/record (sign-up, registration, \
"create new X"), never reuse the given test-data literal exactly if doing so risks colliding \
with data left behind by a previous or concurrent run of this same test (e.g. a duplicate-email \
error). Append a runtime-unique suffix built from the given literal's shape instead, e.g.:
const email = `user_${{Date.now()}}@example.com`;
so each run is self-sufficient and safe \
under parallel execution — never assume another test already created, or will clean up, shared \
data. Only skip this when the step authenticates as an EXISTING account (login, not creation), \
where the given literal must be used exactly as provided.

Timeout rules — target applications vary widely in how long they take to load or process \
a submission. Define THREE constants near the top of the file — never reuse one constant for \
another's job, they solve different problems:
const NAVIGATION_TIMEOUT_MS = 30000;
const ASSERTION_TIMEOUT_MS = 15000;
const TEST_TIMEOUT_MS = 180000;
`NAVIGATION_TIMEOUT_MS` is for a full page navigation only: pass it to `page.goto(...)` \
itself and to the `page.waitForLoadState(...)` call that immediately follows it (see the \
Session/navigation rules below) — a full page load (assets, redirects, an SPA's initial data \
fetch) routinely takes longer than any single locator action, so it gets its own, longer \
budget rather than sharing the tighter per-step one. `ASSERTION_TIMEOUT_MS` is the per-step \
wait for everything else: real render/network latency needs a few seconds, but a genuinely \
broken locator should fail fast, not stall — pass `{{ timeout: ASSERTION_TIMEOUT_MS }}` to \
`page.waitForURL(...)`, every locator action (`.click(...)`, `.fill(...)`, `.check(...)`, \
etc), and every polling `expect(locator)` matcher (`toBeVisible()`, `toHaveText()`, \
`toHaveURL()`, etc — anything that polls a locator/page until it matches or times out). \
`TEST_TIMEOUT_MS` is ONLY the overall safety-net ceiling passed to `test.setTimeout()` — \
never pass it to an individual call. Reusing the long constant everywhere turns every broken \
locator into a multi-minute stall instead of a fast failure — across a whole suite that's the \
difference between a run taking minutes versus hours.

Rule — only a polling matcher accepts `{{ timeout }}`. `expect(locator).toBeVisible(...)`, \
`.toHaveText(...)`, `.toHaveURL(...)` (and other locator/page pollers) poll until the \
condition holds or the timeout elapses, so `{{ timeout: ASSERTION_TIMEOUT_MS }}` is correct \
there. A plain-value matcher (`toBeTruthy()`, `toBe(...)`, `toEqual(...)`, \
`toBeGreaterThan(...)`, etc.) checks an already-computed value exactly once — it has no \
polling behavior, so passing it `{{ timeout: ... }}` is a matcher-usage error, not a slower \
check. Never pass `{{ timeout }}` to a plain-value matcher.

Matcher-existence rule — only use `expect(...)` matchers that are part of Playwright's real, \
documented API (`toBeVisible`, `toHaveText`, `toHaveURL`, `toHaveValue`, `toHaveClass`, \
`toHaveAttribute`, `toHaveCount`, `toBeChecked`, `toBeDisabled`, `toBeEnabled`, `toBeEditable`, \
`toBeFocused`, `toBeTruthy`, `toBe`, `toEqual`, etc). Never invent a matcher name that sounds \
plausible by analogy but does not exist (e.g. `toBeInvalid`, `toBeValid`) — if you need to \
check a validity/error state, express it via a real matcher against the actual DOM signal \
(`toHaveAttribute('aria-invalid', 'true')`, a CSS class via `toHaveClass(...)`, or a \
`:invalid`/custom selector combined with `toBeVisible()`), never a matcher you are only \
assuming must exist.

Numeric-argument rule — this is general, not limited to the examples below: ANY Playwright \
argument typed `number` takes a real TypeScript `number`, never a `string` — this is a compile \
error, not a runtime one. Applies to `toHaveCount(n)`, `.nth(n)`, `page.waitForTimeout(n)`, \
`page.setViewportSize({{ width, height }})`, `page.mouse.click(x, y)`, `page.mouse.move(x, y)`, \
`page.mouse.wheel(dx, dy)`, and the `delay` option on `.click(...)`/`.dblclick(...)`/`.type(...)` \
— and any other Playwright call whose signature says `number`. Only \
pass a bare numeric literal (`toHaveCount(1)`, `.nth(0)`) or a variable actually declared as \
`number` (`const n: number = 3;`). Never pass a Test-data value straight into one of these — \
Test data is filled into forms as strings, so a variable holding a Test-data value is typed \
`string` even when its contents look numeric, and reusing that same variable in \
`toHaveCount(...)` will fail to compile. A Test-data entry below tagged `(number)` reflects \
the real captured HTML input's type — declare its const with `Number(...)` right at \
assignment (`const quantity: number = Number(<value>);`) so every later use of that variable \
is already correctly typed, instead of only converting it at the one call site you happen to \
remember: `toHaveCount(quantity)`.

Not every Playwright method accepts a `timeout` option either — do not add a `timeout` \
to a call unless that specific method's signature actually has an options parameter. Most \
notably, `page.content()`, `page.url()`, and `response.status()` take NO arguments at all — \
calling e.g. `page.content({{ timeout: ASSERTION_TIMEOUT_MS }})` is a compile error, not a \
slower call. When in doubt, only pass `{{ timeout: ... }}` to navigation (`page.goto`, with \
`NAVIGATION_TIMEOUT_MS`) and the `page.waitForLoadState(...)` call immediately following it \
(also `NAVIGATION_TIMEOUT_MS`), waiting (`page.waitForURL`, with `ASSERTION_TIMEOUT_MS`), \
locator actions (`.click`, `.fill`, `.check`, etc, with `ASSERTION_TIMEOUT_MS`), and polling \
`expect(...)` matchers (`ASSERTION_TIMEOUT_MS`) — never to a plain getter/accessor method, \
and never to a plain-value matcher.

Critical: Playwright's own overall per-test timeout defaults to 30000ms regardless of any \
`{{ timeout: ASSERTION_TIMEOUT_MS }}` passed to individual calls — a per-assertion timeout \
does NOT extend how long the test as a whole is allowed to run, and the test will still be \
killed at 30 seconds even while an individual `expect(...)` is still legitimately waiting \
within its own budget. There is no `playwright.config.ts` to raise this globally, so every \
generated test MUST raise its own timeout as the very first line inside the test body:
test('...', async ({{ page }}) => {{
  test.setTimeout(TEST_TIMEOUT_MS);
  // ...rest of the test
}});

Session/navigation rules — many target applications are session-dependent and will return \
a server error or broken markup if a deep link is the very first thing opened in a fresh \
browser context with no prior cookies. Follow these rules for every test, not just login \
Scenarios:

1. {initial_navigation_rule}

2. After every `page.goto(...)` call — not just the first one in the test — capture the \
returned response, verify it succeeded, and then wait for the DOM to actually be rendered \
before doing anything else with the page. A page load legitimately takes longer than a \
locator action, so it gets its own, longer `NAVIGATION_TIMEOUT_MS` budget rather than \
`ASSERTION_TIMEOUT_MS`; never locate or assert on an element right after `goto(...)` resolves \
without this wait in between, since the initial HTML can still be mid-parse at that point:
const response = await page.goto(url, {{ timeout: NAVIGATION_TIMEOUT_MS }});
if (!response || response.status() >= 400) {{
  throw new Error(`Failed to load page. HTTP status: ${{response?.status()}}`);
}}
await page.waitForLoadState('domcontentloaded', {{ timeout: NAVIGATION_TIMEOUT_MS }});

3. Before locating or asserting on any element, confirm the page did not render a server \
error page in place of real application markup (this can happen even after a 200 \
response, if the app fails server-side while rendering). Define and call a small helper \
for this, e.g.:
async function assertNoServerError(page) {{
  const bodyText = await page.content();
  const errorMarkers = ['Internal Server Error', 'Exception Report', 'HTTP Status 500', \
'HTTP Status 404', 'Service Unavailable'];
  for (const marker of errorMarkers) {{
    if (bodyText.includes(marker)) {{
      throw new Error(`Server returned an error page instead of the expected content: \
${{marker}}`);
    }}
  }}
}}
Call `await assertNoServerError(page)` right after each navigation, before locating any \
element — this turns a misleading "element not found" failure into a clear, actionable \
error when the real cause is a server-side failure rather than a bad locator.

4. After any step that changes auth/session state (logout, session expiry, a redirect), \
never assume the next page has the element you expect it to. Either navigate to the known \
target URL explicitly (`page.goto(...)` — apply rule 2's response check and \
`waitForLoadState('domcontentloaded', ...)` wait to it too) or verify the landing page first \
— one `expect(page).toHaveURL(..., {{ timeout: ASSERTION_TIMEOUT_MS }})` (or a content check) \
right after the state-changing click, before touching any element on whatever page you land \
on. Never guess a redirect target from convention (e.g. assuming a successful action lands on \
`/` or "the home page") — if the destination isn't given by the Test steps or a Known page \
match, verify the actual landing page via a content check rather than asserting an invented URL.

Selector-collision rule — default `exact: true` on `getByLabel(...)`, `getByText(...)`, and \
`getByRole(..., {{ name }})` whenever the given text/label could plausibly be a substring of \
another label on the same page (e.g. `getByLabel('Password')` also matches "Confirm \
Password" without `exact: true`, causing a strict-mode violation or the wrong field getting \
filled). Only omit `exact: true` when you've confirmed the text is unique on the page, or \
when the Multi-fragment accessible-name rule (below) applies — that rule requires a partial/ \
regex match instead, since there the full name is never stable enough to write an exact \
string at all. Separately: when an element has both an `id`/`name`/`data-testid` attribute \
AND label/text, prefer the attribute — attributes can't collide via substring the way label \
text can.

Locator rules — accessible-name-based locators (`getByLabel`, `getByRole` on non-button \
elements) are NOT safe for form fields: a name/label regex like `/password/i` will also \
match unrelated controls that merely mention the same word (e.g. a "Show password" \
visibility-toggle button), causing a Playwright strict-mode violation ("resolved to N \
elements"). For every form field, prefer a CSS attribute locator restricted to the \
correct element type over any accessibility-based locator, in this priority order:

For a password field: `input[name="password"]`, then `input[type="password"]`, then \
`input[id="password"]`, then `getByPlaceholder(/password/i)`, and only as a last resort \
`getByLabel(/password/i)`.

For a username/email field: `input[name="username"]`, `input[name="email"]`, \
`input[type="email"]`, then `getByPlaceholder(/user|email/i)`, and only as a last resort \
`getByLabel(/user|email/i)`.

Never generate `text="<value>"` (in a `page.locator(...)`) against a form field's internal \
name, id, or model-property string — input/select/textarea elements have no text content, \
so that locator is guaranteed to never resolve, regardless of app state. When you do fall back \
to `getByLabel(...)`, its argument must be the field's real visible label text/accessible \
name (what a sighted user reads next to the field) — never the field's internal name, id, or \
model-property string.

Combine the CSS-attribute options as one comma-separated selector passed to `page.locator(...)` \
and take `.first()`, so any one of them matching resolves the field unambiguously. Before \
interacting with ANY resolved locator (not just this password example), route it through the \
shared `ensureVisible` helper (support/ is reached via '../../support/...' from this file, \
not '../support/...') instead of writing your own visibility check — it scrolls the element \
into view if it isn't already visible and re-verifies, so a genuinely wrong/stale locator (or \
an element hidden behind a fixed header, off-screen in a long page, or inside an unusual \
scroll container) fails with a clear, diagnosable error instead of a confusing fill/click \
timeout. For example, instead of:
await page.getByLabel(/password/i).fill(password);
generate:
import {{ ensureVisible }} from '../../support/interactions';
// ...
const passwordField = await ensureVisible(page.locator(
  'input[name="password"], input[type="password"], input[id="password"]'
).first());
await passwordField.fill(password);

Never treat a button (e.g. `<button aria-label="Show password">`, `<button aria-label="Hide \
password">`, or any other visibility-toggle control) as a candidate for a text/password \
input locator — always constrain field locators to `input` elements only. Only fall back to \
an accessibility-based locator (`getByLabel`/`getByPlaceholder`) for a field when no \
CSS attribute selector for it is available, and even then only if that locator's regex is \
specific enough that it would not plausibly also match a button or other non-field control.

Multi-fragment accessible-name rule — the same "no exact match" reasoning applies whenever \
you build your own `getByRole(...)`/`getByText(...)` locator (not just when reusing a known \
locator, above) for a product card, list item, or dashboard tile whose accessible name \
concatenates an icon/emoji, an entity/title fragment, a dynamic figure (price, date, count, \
rating), and/or a decorative chevron/arrow. Never hard-code the full computed accessible name \
as an exact match — it will break the moment the dynamic figure changes. Match only the \
stable entity-name fragment via partial/regex `name`:
Don't: `page.locator('role=link[name="🏥\nHealth Plan\nFrom ₹ 12,500/yr · Up to ₹50 L cover\n\
›"]')`
Do: `page.getByRole('link', {{ name: /Health Plan/ }})`

This applies just as much to a plain `<button>` with a leading/trailing icon — not just cards \
and tiles. An icon rendered as an `<img>`/`<svg>` sibling inside the button contributes its own \
alt text/aria-label to the button's ONE computed accessible name, merged with the visible \
label: a button showing a "+" icon and the text "Add connection" has the real accessible name \
"plus Add connection", not "Add connection". `getByRole('button', {{ name: 'Add connection', \
exact: true }})` matches ZERO elements against that button — `isVisible()` on a zero-match \
locator returns `false`, not an error, so this fails as a confusing "element not visible" \
rather than an obvious "not found." Always use a partial/regex `name` for any button whose \
accessible name might include an icon's own label:
Don't: `page.getByRole('button', {{ name: 'Add connection', exact: true }})`
Do: `page.getByRole('button', {{ name: /Add connection/ }})`

Search-submit scoping rule — when a step's intended action is submitting a search (fill a \
search input, then trigger the search), do not pick the submit control by name-matching \
anywhere on the page — a page often has more than one candidate (e.g. a global nav search \
plus a page-level search, or an unrelated button that happens to share the word "search"). \
Scope the candidate search to the same `<form>`/logical container as the input you just \
filled, e.g.:
const searchInput = page.locator('input[name="q"], input[type="search"]').first();
await searchInput.fill(query);
const submitButton = page.locator('form:has(input[name="q"])').getByRole('button', {{ name: /search/i }});
if (await submitButton.count() > 0) {{
  await submitButton.first().click({{ timeout: ASSERTION_TIMEOUT_MS }});
}} else {{
  await searchInput.press('Enter');
}}
If no submit control resolves within that same form/container, default to \
`await searchInput.press('Enter')` on the field itself — the safe generic fallback for a \
search box — rather than clicking a page-wide name match that may belong to an unrelated form.

Custom dropdown/combobox rule — `.selectOption(...)` only ever works on a genuine native \
HTML `<select>` element; calling it on anything else fails immediately with "Element is not a \
<select> element", even when every other part of the interaction (opening it, finding the \
option) would have worked. Many real applications instead use a non-native dropdown built from \
a `role="combobox"` trigger (often with `aria-haspopup="listbox"`) plus a separate popup list of \
options — this is the standard pattern behind popular component libraries (e.g. Ant Design, \
MUI, Chakra, React-Select) as well as plenty of custom-built ones, and a known/captured locator \
whose element role is "combobox" (not "select") is your signal that this is what you're dealing \
with. For one of these: click the combobox trigger to open it, then locate and click the \
specific option — routed through `ensureVisible` like any other interaction, never \
`.selectOption(...)`. Only reach for `.selectOption(...)` when you have specific evidence the \
element really is a native `<select>` (e.g. its known/captured locator or element type says so). \
When locating the option itself, never scope the search to inside the trigger element — a \
non-native dropdown's popup content commonly renders elsewhere in the DOM entirely (a portal/ \
overlay), not nested under the trigger — search the page directly instead, preferring the \
option's own known/captured locator verbatim if one was given to you above (see the generic-role \
rule immediately below for why that matters); only build your own locator when none was given, \
and even then prefer `page.getByText(..., {{ exact: true }})` over `page.getByRole('option', \
{{ name: ... }})` unless you have specific evidence the option element genuinely carries \
`role="option"` on the real, visible node (many component libraries keep `role="option"` only on \
a hidden, zero-size accessibility duplicate — see below).

Generic-role rule — a captured/known locator's element role of "generic" (a plain `<div>`/`<span>` \
with no real ARIA semantics — the common shape of a custom dropdown/menu/tab option) is a signal \
to use `page.getByText(name, {{ exact: true }})`, never `page.getByRole('generic', {{ name }})`. \
This is not a style preference: a real browser's accessibility tree treats "generic" as \
name-from-content-prohibited, so `getByRole('generic', ...)` can match ZERO elements even when the \
exact same element is genuinely on screen and clickable — no amount of waiting, scrolling, or \
`.filter({{ visible: true }})` fixes a locator that structurally cannot match anything. \
`getByText(..., {{ exact: true }})` is what actually finds it. If the known/captured locator \
already reads `getByText(...)` for this element, reuse it verbatim — that already reflects this \
rule; never "upgrade" it back to a `getByRole('generic', ...)` guess of your own.

Duplicate/hidden-option-node rule — a role+name match for a dropdown/listbox/menu option is not \
guaranteed to be unique, and not guaranteed to be the real one. Some component libraries \
(e.g. Ant Design's Select) keep a second, permanently hidden, zero-size DOM node with `role="option"` \
purely for assistive tech, separate from the actual, complete, currently-interactable popup \
rendered elsewhere (commonly the portal case above) — waiting does not resolve this, a \
permanently-hidden duplicate never becomes visible no matter how long you wait. If `waitFor`/ \
`ensureVisible` on a `role="option"` match keeps failing "not visible" for an option you can \
otherwise confirm exists, that is the signal to stop retrying that locator and switch to matching \
its visible text directly instead (`page.getByText(name, {{ exact: true }})`) — never assume a \
bare role+name match is already the single, correct, interactable node for this class of element.

Pre-existing-data ambiguity rule — a bare `page.getByText(name, {{ exact: true }})` for a \
dropdown/listbox/menu option is not automatically unique either, and this time BOTH matches can \
be genuinely visible at once: real application data created by an earlier action (in this test or \
a previous run against a real/shared environment) can already display the same text elsewhere on \
the page — e.g. a status tag/badge/label in a table row showing a value that happens to match the \
option's name — and a strict-mode `waitFor`/`ensureVisible` call then fails with a real "resolved \
to N elements" violation, not a visibility problem at all (see `ensureVisible`'s own handling: it \
surfaces this error immediately rather than masking it). Since a non-native dropdown's popup is \
almost always portal-rendered — appended to the end of the DOM, after everything already on the \
page — its real option is reliably the LAST match in document order, not the first. Scope a \
popup-option text locator with both `.filter({{ visible: true }})` AND `.last()` together, e.g. \
`page.getByText(name, {{ exact: true }}).filter({{ visible: true }}).last()`, rather than a bare \
match with no suffix or an arbitrary `.first()` guess.

Field-level validation rules — when a step checks that a field shows a validation/error \
state (e.g. "shows required field error", "marks the field invalid"), do NOT search the \
page for arbitrary validation-message text, and do NOT assume any single mechanism (e.g. \
`aria-invalid`) is how THIS application signals it — apps signal an invalid field wildly \
differently: native `:invalid`, `aria-invalid`, a CSS class, a sibling error element, a \
page-level banner. None of those is a safe universal default. Assert on whichever mechanism \
the step/page context actually implies (e.g. `input[name="..."][aria-invalid="true"]`, \
`input[name="..."][data-validate="..."]`, the native `:invalid` pseudo-class, or an \
application-specific attribute named in the step) — treat any one of these as an unverified \
fallback guess, not a known-good default, and prefer whichever the Test steps/Expected result \
actually name over guessing. Only assert on visible error text if that exact text is given to \
you via the Test data or Expected result above — never invent your own generic message (e.g. \
"This field is required") and search for it.

Native browser validation message rule — an Expected result that quotes wording like "Please \
fill out this field.", "Please match the requested format.", or "Please select a value in the \
list." (the browser's own built-in constraint-validation copy, verbatim from a captured \
`html5_message`) is NEVER part of the page's DOM or accessibility tree, even though the exact \
text was given to you above — it's rendered by the browser's native validation bubble, outside \
the document entirely, so `getByText`/`toContainText`/`page.content()` can never find it and a \
generated assertion that searches for it can never pass. For that exact wording, assert against \
the field's own validity state instead: `await expect(field).toHaveJSProperty('validationMessage', \
'<exact text>')`, or, if only checking that the field is flagged invalid (no exact wording given), \
the native `:invalid` pseudo-class / `field.evaluate(el => el.checkValidity())`.

Form-field value-persistence rule — never assert that a field "retains its value" after a \
submit/postback (or that it was cleared) unless the Test steps or Expected result explicitly \
say so. Frameworks differ deliberately here: some clear password fields for security, some \
clear the whole form, some retain everything. Don't default to "text inputs usually keep \
their value" — if persistence/clearing isn't the thing the Scenario is actually testing, \
don't assert on it at all.

Known-locators-only structural rule — Discovery never captures a page's presentation \
mechanism: Known locators above only ever lists buttons, links, and form fields it actually \
observed — never a table, list, grid, alert, toast, or modal CONTAINER as such (only the real \
interactive elements inside one, if any were captured). Never invent a selector for one of \
these containers (e.g. `table`, `tr`, `.row`, `ul li`, `[role="alert"]`, `.toast`, `.modal`) \
unless either (a) it corresponds to an actual entry in Known locators above, or (b) this same \
test's own earlier steps just interacted with the exact element you're now asserting on. When \
neither holds, ground the assertion in what you actually DO have evidence for instead — a \
Known locator becoming visible, the page's known URL, or text already named in the Test \
steps/Expected result — never a bare structural guess about how the page happens to be built. \
The following rules apply this same principle to specific situations.

Failure-outcome assertion rules — the same "don't invent wording" rule applies to any \
failure/error outcome, not just field validation (e.g. an invalid-login message). Use the \
literal text ONLY if it is explicitly given to you via the Test data or Expected result \
above — copy it verbatim, never paraphrase or invent your own phrasing. If no literal \
expected message text is given, do not assert on any specific fabricated wording at all; \
instead assert on an observable, application-agnostic signal that the action failed. Prefer \
checking that the page did NOT navigate away from where the failing action was attempted \
(e.g. compare `page.url()` before and after, or assert the same form/field is still present) \
as the primary signal — this is always queryable regardless of the application's markup \
conventions. A generic error/alert container guess (e.g. \
`page.locator('[role="alert"], .error, [aria-live]').first()`) is NEVER grounded in anything \
Known locators actually gave you (per the Known-locators-only structural rule above) — it is \
always an invented guess, even when it looks like reasonable, idiomatic Playwright. Never make \
it a hard, must-pass assertion (`await expect(errorContainer).toBeVisible(...)`) — if that \
container never renders on this application, the test times out and fails even though the \
real, already-queryable signal above (URL/form-still-present) already proved the action \
failed exactly as expected. If you want to additionally check for one, make it soft and \
log-only, the same pattern the Empty-result assertion rule below uses, never able to fail the \
test on its own:
const errorContainer = page.locator('[role="alert"], .error, [aria-live]').first();
if (await errorContainer.count() === 0) {{
  console.warn('No generic error container found; relying on the URL/form-state signal only.');
}}
Never hardcode a message like "Invalid username or password" unless that exact string was \
given to you as data.

Empty-result assertion rule — when a Scenario's Expected result is that a search/filter \
yields no results (an empty state), do not assume the application renders a text message \
like "No results found" — many applications simply render an empty result list with no copy \
at all. Treat the structural signal as the authoritative pass condition: \
`await expect(page.locator('<result-item selector>')).toHaveCount(0, {{ timeout: \
ASSERTION_TIMEOUT_MS }})` against the same locator that would match individual result items \
on a non-empty search — this item locator must itself correspond to an actual entry in Known \
locators above (a captured component this page's non-empty state would show); never invent a \
generic `tr`/`.list-item`/`table` selector with no such backing (per the Known-locators-only \
structural rule above). If no such item locator exists in Known locators, fall back to \
asserting the page's known URL/heading is correct instead of a count-based check. Only \
additionally check for empty-state copy if that literal text is given to you via the Test \
data/Expected result above, and even then make it a soft, log-only check that cannot fail the \
test on its own, e.g.:
const emptyMessage = page.getByText('<the given literal text>');
if (await emptyMessage.count() === 0) {{
  console.warn('Empty-state message not found; relying on structural assertion only.');
}}
Never let an absent/mismatched text message fail an otherwise structurally-correct \
empty-state test — the `toHaveCount(0)` check above is what must pass.

Step-ordering rule — perform every listed Test step, in order, BEFORE asserting the Expected \
result. Never assert the Expected result (or any failure/success signal derived from it) \
before the actions that are supposed to produce it have actually been executed — e.g. do not \
check for a login-error indicator before filling in credentials and clicking submit.

Shared-state cleanup rule — if a Scenario's steps mutate state that isn't obviously scoped to \
this one test run alone (e.g. changing a setting, editing a shared/reused record, updating a \
profile field on an account other tests also log in as), add the matching restore step(s) at \
the end of the SAME test, after the Expected result has been asserted — put the value back to \
what it was before this test mutated it. Only skip the restore if the Scenario's own steps \
already end in a state that undoes the change (e.g. the flow itself deletes what it created), \
or if the Scenario's own point IS the mutation's permanence (e.g. "account is deleted").

No-fabricated-assertion rule — never fall back to a tautological check like \
`if (x !== y) {{ expect(x).not.toBe(y) }}` (or its `===`/`.toBe` mirror) when you cannot \
derive a real assertion for this Scenario's Expected result — that pattern can only ever run \
inside the branch where the comparison is already known true, so it never actually verifies \
anything. If none of the rules above give you a genuine, meaningful assertion to write, assert \
on the most concrete observable signal the Test steps/Expected result actually describe instead \
of inventing one.

Existing-data assertion rule — the Test data above is a resolved value for FILLING a form \
field; it is never verified real content that already exists elsewhere in the application \
(e.g. a specific card number, account balance, or transaction amount you have not yourself \
just entered). Never search for, or assert that, a specific Test-data literal is displayed on \
a page UNLESS this same test's own steps entered/submitted that exact value earlier in this \
same test — a value's mere presence in Test data does NOT mean it is real, pre-existing, \
seeded data anywhere in the application. When a Scenario's whole point is reviewing/verifying \
EXISTING data this test did not itself create (e.g. "review the Cards page", "view existing \
transactions"), assert on an observable STRUCTURAL signal instead of a specific fabricated \
value — but only using a locator that corresponds to an actual entry in Known locators above \
(per the Known-locators-only structural rule): that at least one matching row/item is present \
(e.g. `await expect(page.locator(<item selector>).first()).toBeVisible({{ timeout: \
ASSERTION_TIMEOUT_MS }})`, or a `toHaveCount` greater than 0), or that a known label/column \
header from Known pages/locators above is shown — never a specific number, name, or amount \
this test never entered, and never an invented `tr`/`.row`/`table` selector with no Known-\
locators backing. If Known locators gives you nothing to assert a row/item on, fall back to \
confirming the page's known URL/heading is correct instead.

Output ONLY the TypeScript code, no markdown fences, no prose, no explanation."""


def _describe_test_data(
    scenario: Scenario, field_input_types: dict[str, str] | None = None
) -> str:
    field_input_types = field_input_types or {}

    def _line(f: dict) -> str:
        tag = " (number)" if field_input_types.get(f["name"]) == "number" else ""
        return f"- {f['name']}{tag}: {f.get('value')}"

    return "\n".join(_line(f) for f in scenario.test_data) or "(none)"


def _describe_changed_test_data(changed_test_data: list[dict]) -> str:
    return "\n".join(f"- {f['name']}: {f.get('value')}" for f in changed_test_data) or "(none)"


def _describe_known_pages(known_pages: list[dict[str, str]] | None) -> str:
    if not known_pages:
        return "(none)"
    return "\n".join(f"- {p['stage_label']} -> {p['url']}" for p in known_pages)


def _describe_known_locators(known_locators: list[dict[str, str]] | None) -> str:
    if not known_locators:
        return "(none)"

    def _describe_one(loc: dict[str, str]) -> str:
        prefix = f"{loc['stage_label']} / {loc['component_type']}:{loc['component_name']}"
        # "label" strategy's value is real visible label text, not a
        # `page.locator()` selector string — `label=` isn't a real
        # Playwright selector engine, so this must render as a
        # `getByLabel(...)` call, never interpolated into `page.locator(...)`.
        if loc.get("strategy") == "label":
            return f'- {prefix} -> getByLabel("{loc["selector"]}")'
        return f"- {prefix} -> {loc['selector']}"

    return "\n".join(_describe_one(loc) for loc in known_locators)


def _describe_live_locators(locator_candidates: list[dict] | None) -> str:
    """Live-inspection candidates (`locator_capture.extract_page_locator_
    snapshot`'s shape: strategy/value/fragile/element_tag) are structurally
    different from `known_locators` above (Discovery's named Components) —
    no stage_label/component_name, since these came from a bare page probe,
    not a captured, named Component."""
    if not locator_candidates:
        return "(none)"

    def _describe_one(loc: dict) -> str:
        if loc.get("strategy") == "label":
            return f'- <{loc["element_tag"]}> -> getByLabel("{loc["value"]}")'
        return f"- <{loc['element_tag']}> -> {loc['value']}"

    return "\n".join(_describe_one(loc) for loc in locator_candidates)


def _describe_live_action_sequence(steps: list[dict] | None) -> str:
    """`LiveHealActivity`'s ordered replay: each entry is one live MCP
    action (`tool_name` + the same strategy/value/fragile/element_tag shape
    `_describe_live_locators` uses) — order matters here, unlike
    `_describe_live_locators`'s flat candidate list, since an earlier entry
    is often a prerequisite (opening a dropdown/menu/tab) the later target
    only becomes interactable after."""
    if not steps:
        return "(none)"

    def _describe_one(step: dict, index: int) -> str:
        tool = step.get("tool_name", "?")
        tag = step.get("element_tag", "")
        return f"{index}. {tool} on <{tag}> -> {step.get('value', '')}"

    return "\n".join(_describe_one(step, i) for i, step in enumerate(steps, start=1))


# --- NLM prompt classification — is this request a genuine, testable
# description of application behavior, and what does it actually ask for.
# Shared by `LiveExplorationTestWorkflow`, the only NL entry point (see
# `analyze_test_case_prompt`'s own section below for what got removed).

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_PER_CATEGORY_COUNT = re.compile(
    r"\b(?P<count>\d+|one|two|three|four|five)\s+(?P<category>happy|negative|edge)\w*",
    re.IGNORECASE,
)
_TOTAL_TEST_CASE_COUNT = re.compile(
    r"\b(?P<count>\d+|one|two|three|four|five)\s+test\s+cases?\b", re.IGNORECASE
)


def _fallback_requested_scenario_counts(prompt: str) -> dict[str, int]:
    """Deterministic backstop for `analyze_test_case_prompt`'s own LLM-based
    extraction, which — observed live — doesn't reliably populate
    `requested_scenario_counts` on every call even for an unambiguous prompt
    like "create three test cases: happy path, negative path, edge case".
    Only ever used to fill in a category the LLM's own response left out,
    never to override one it did return (see caller)."""
    counts = {
        match.group("category").lower(): (
            _NUMBER_WORDS.get(match.group("count").lower()) or int(match.group("count"))
        )
        for match in _PER_CATEGORY_COUNT.finditer(prompt)
    }
    if counts:
        return counts

    # No per-category number anywhere (e.g. "3 negative scenarios") — the
    # other common idiom is a bare total plus all three category words
    # named with no number of their own, which splits 1 each.
    total_match = _TOTAL_TEST_CASE_COUNT.search(prompt)
    categories_named = {
        category
        for category in ("happy", "negative", "edge")
        if re.search(category, prompt, re.IGNORECASE)
    }
    if total_match and categories_named == {"happy", "negative", "edge"}:
        return {"happy": 1, "negative": 1, "edge": 1}
    return {}

_TEST_CASE_PROMPT_SYSTEM = """A user of a QA automation tool has described, in plain English, a \
test case they want added for a specific web application. Determine whether this is a genuine \
request to test that application's functionality, and if so extract what it's actually asking for.

Reject (is_relevant=false) anything that isn't a request to test this application's own \
functionality — small talk, requests unrelated to this application, or requests to do something \
other than describe a test case (e.g. "write me a poem", "what's the weather", "delete all my \
data"). A short or informally worded request is still relevant if it's clearly describing \
application behavior to test.

Also extract any concrete test-data VALUE the user stated literally in their own words (e.g. \
"using promo code EXPIRED10", "with the email jane@example.com", "search for laptop") into \
"provided_test_data" as {{"<field name>": "<the exact value they gave>"}}. Only include a value \
the user actually wrote — never invent, guess, or fill in a value they didn't state. Most \
requests give none at all; an empty object is the normal case.

Also extract an explicit scenario COUNT if, and only if, the user's own words state one — a \
total ("create three test cases", "give me 5 test cases") and/or a per-category breakdown \
("one happy path, one negative, one edge case", "3 negative scenarios"). Put it in \
"requested_scenario_counts" as {{"happy": <int>, "negative": <int>, "edge": <int>}}, using only \
the categories the user actually implied a count for — a bare total with the three canonical \
categories named (happy/negative/edge, or "successful"/"failure"/"boundary" phrasing) splits \
1 count each; a bare total with no category breakdown at all is not extractable, leave the \
object empty. Never invent a count the user didn't state or imply — most requests give none; \
an empty object is the normal case.

Respond with ONLY a JSON object of this shape, no prose: \
{{"is_relevant": true, "functionality_summary": "one sentence describing the feature/flow under \
test", "actions": ["ordered, plain-language user actions, e.g. \\"open the cart\\", \\"apply a \
promo code\\""], "expected_result": "what should happen if the test passes", \
"provided_test_data": {{}}, "requested_scenario_counts": {{}}, "rejection_reason": null}} — or, \
when not relevant: {{"is_relevant": false, "functionality_summary": "", "actions": [], \
"expected_result": "", "provided_test_data": {{}}, "requested_scenario_counts": {{}}, \
"rejection_reason": "one sentence explaining why this isn't a testable request for this \
application"}}"""

_TEST_CASE_PROMPT_USER = """User's request: "{prompt}\""""

# Story 2.10 AC 3: a short, plain-language (not JSON) opinion — this is
# supporting evidence recorded in diagnostics, never a structured decision
# the caller branches on, so there's nothing here worth a schema for.
_STATE_SIMILARITY_PROMPT = """Two captured application states share the same URL route \
pattern. Based only on their headings and the actions available on each, is state B the \
SAME screen as state A with different data, a VARIANT (same route, materially different \
behaviour — e.g. a different workflow stage with different actions available), or \
genuinely a NEW/unrelated screen?

State A — heading: "{heading_a}", actions: {actions_a}
State B — heading: "{heading_b}", actions: {actions_b}

Respond with one word (SAME, VARIANT, or NEW) followed by a one-sentence reason."""

# Story 2.12 AC 3: called only when the verb-list classifier found no match
# at all — supporting evidence only, recorded in diagnostics; the Safety
# Engine's own posture-driven verdict never changes based on this opinion.
_ACTION_SAFETY_PROMPT = """An automated web crawler found a clickable UI action with no \
verb-based safety classification. Based on its accessible name and the surrounding page \
context, is this action likely SAFE (read-only, no side effects), DESTRUCTIVE (deletes, \
removes, or irreversibly changes data), or AMBIGUOUS (changes state, but not clearly \
destructive)?

Action label: "{label}"
Page context: {page_context}

Respond with one word (SAFE, DESTRUCTIVE, or AMBIGUOUS) followed by a one-sentence reason."""


# Live-exploration agent (NL requirement -> live browser -> Live Flow Model).
# Never given crawler/discovery data — the requirement text and the current
# Playwright MCP `browser_snapshot` are the only grounding, by design. The
# tool catalog is the real, stable Playwright MCP surface; `element`/`ref`
# values in a returned `browser_click`/`browser_type`/`browser_select_option`/
# `browser_hover` call MUST come from a node in the CURRENT snapshot below —
# never invented, never carried over from an earlier turn's snapshot (the
# page may have changed since).
_LIVE_EXPLORATION_PROMPT_SYSTEM = """You are a QA engineer's live-exploration agent. You \
control a real web browser through the Playwright MCP tools listed below, one call at a \
time, to accomplish a natural-language testing requirement against a real, unfamiliar \
web application. You have never seen this application before — you must observe it live \
and decide each next step from what you actually see, never from assumed navigation or \
guessed URLs/selectors.

Available tools (call exactly one per turn):
- browser_navigate({{"url": "..."}})
- browser_snapshot({{}}) — re-observe the current page; use when unsure what changed
- browser_click({{"element": "<human description>", "ref": "<ref from the snapshot below>"}})
- browser_type({{"element": "...", "ref": "...", "text": "...", "submit": false}})
- browser_select_option({{"element": "...", "ref": "...", "values": ["..."]}})
- browser_hover({{"element": "...", "ref": "..."}})
- browser_press_key({{"key": "Enter"}})
- browser_wait_for({{"text": "..."}}) or ({{"time": <seconds>}})
- browser_go_back({{}})

Rules:
- Every "ref" you use must be copied verbatim from a node in the CURRENT snapshot given \
below — never a ref from an earlier turn, never invented.
- Prefer the fewest, most direct steps. Do not explore tangential UI.
- Set "goal_satisfied" to true only once you have observed, in the current snapshot or the \
result of your last action, direct evidence the requirement is fully met (e.g. the created \
item visibly appears in a list) — never assume success from an action alone.
- If a form/dialog appears, fill only the fields necessary to proceed.

Respond with ONLY a JSON object of this shape, no prose: {{"tool_name": "...", "tool_args": \
{{...}}, "rationale": "<one sentence>", "goal_satisfied": false}}"""

_LIVE_EXPLORATION_PROMPT_USER = """Requirement: {requirement}

Turns so far (oldest first):
{history}

Current page snapshot:
{snapshot}

What is the single next tool call?"""

_LIVE_HEAL_PROMPT_SYSTEM = """You are a QA engineer's live-healing agent. A generated \
Playwright test's step failed because the application's UI has changed since the test was \
written. You control the real, current application through the Playwright MCP tools listed \
below. Your only goal is to find the CURRENT correct element for the one failed step \
described below — never consult or trust the test's old locator, it is exactly what is \
wrong.

Available tools (call exactly one per turn):
- browser_navigate({{"url": "..."}})
- browser_snapshot({{}})
- browser_click({{"element": "...", "ref": "..."}})
- browser_type({{"element": "...", "ref": "...", "text": "...", "submit": false}})
- browser_hover({{"element": "...", "ref": "..."}})
- browser_wait_for({{"text": "..."}}) or ({{"time": <seconds>}})

Rules:
- Every "ref" must come from the CURRENT snapshot below, never invented or reused from an \
earlier turn.
- You are looking for one element, not completing the whole scenario. Merely seeing it in a \
snapshot is never enough — identifying it in your own reasoning captures no evidence at all. \
Once you can identify the element from the current snapshot, confirm it with exactly one \
action, chosen by what the failed step actually is:
  - Selecting an option from an already-open dropdown/listbox/menu (the step just chooses a \
value — it is not a submit, save, delete, create, or navigate) — your NEXT turn must be \
"browser_click" on that exact "ref". A hover alone can never confirm this: clicking is the only \
way to tell whether the option genuinely selects when interacted with, and to catch a \
wrong-but-similarly-named element elsewhere on the page (e.g. an unrelated status tag reusing the \
same text) that a hover would have silently accepted. Clicking a dropdown/listbox/menu option is \
not destructive — it only changes which value the field holds, and this heal never goes on to \
submit that form.
  - Anything else (a button, link, or any element that creates, deletes, saves, submits, or \
navigates) — your NEXT turn must be "browser_hover" on that exact "ref" (hover only — never \
"browser_click"/"browser_type", which could trigger the very change under investigation instead \
of just confirming it).
Only in the turn AFTER that confirming click-or-hover has run may you set "goal_satisfied": true, \
naming the element's current role and accessible name in "rationale" (e.g. "button, accessible \
name 'Create connection'", or "generic, accessible name 'GIT' — clicking it set the Server type \
field to GIT"). Never set "goal_satisfied" in the same turn as that confirming action itself, and \
never set it without having performed the correct one (click for a dropdown/listbox/menu option, \
hover for everything else) on the exact element first.
- Do not submit forms, save, delete, or perform any other destructive or navigating action — you \
are investigating, not executing the rest of the step. Selecting a dropdown/listbox/menu option \
(see above) is the one confirming action that is not destructive and is always allowed.

Respond with ONLY a JSON object of this shape, no prose: {{"tool_name": "...", "tool_args": \
{{...}}, "rationale": "<one sentence, or the element identification once goal_satisfied>", \
"goal_satisfied": false}}"""

_LIVE_HEAL_PROMPT_USER = """Failed step: {requirement}

Turns so far (oldest first):
{history}

Current page snapshot:
{snapshot}

What is the single next tool call?"""


async def _chat_completion(
    messages: list[dict[str, Any]],
    *,
    response_format: dict[str, str] | None = None,
    timeout: int = 60,
    max_tokens: int | None = None,
) -> str:
    payload = {
        "model": AI_MODEL,
        "messages": messages,
    }
    if "gpt" in AI_MODEL.lower():
        payload["reasoning_effort"] = "high"
    elif AI_TEMPERATURE is not None:
        payload["temperature"] = AI_TEMPERATURE
    if response_format is not None:
        payload["response_format"] = response_format
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    async with httpx.AsyncClient(base_url=LITELLM_BASE_URL, timeout=timeout) as client:
        response = await client.post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
            json=payload,
        )
        response.raise_for_status()
    choice = response.json()["choices"][0]
    # Without this, a response cut off by the token budget (finish_reason
    # "length") either fails json.loads with a confusing error deep in the
    # caller, or — worse — happens to still be valid-but-incomplete JSON
    # (e.g. truncated right after a complete array element) and silently
    # short-changes the caller (Story: "digital banking" scenario generation
    # stopping at 40 items with no error at all).
    if choice.get("finish_reason") == "length":
        raise RuntimeError(
            f"LLM response truncated by max_tokens (model={AI_MODEL}, "
            f"max_tokens={max_tokens}) — increase max_tokens"
        )
    return choice["message"]["content"]


class HostedAIProvider:
    """`AIProvider` (Protocol) adapter backed by a LiteLLM proxy server."""

    async def infer_journeys(self, pages: list[Page]) -> list[JourneyCandidate]:
        listing = "\n".join(f"{i}: {_describe_page(p)}" for i, p in enumerate(pages))
        content = await _chat_completion(
            [
                {"role": "system", "content": _PROMPT_SYSTEM},
                {"role": "user", "content": _PROMPT_USER.format(page_listing=listing)},
            ],
            response_format={"type": "json_object"},
            timeout=240,
            max_tokens=20000,
        )
        groups = json.loads(content)["journeys"]

        candidates = []
        for group in groups:
            name = group["name"]
            if _ROUTE_SHAPED_NAME.match(name):
                logger.warning(
                    "HostedAIProvider: dropped candidate with route-shaped name %r", name
                )
                continue

            steps = []
            for raw_step in group["steps"]:
                index = raw_step["page_index"]
                # AC7 hallucination guard: the AI referenced a page index
                # outside what it was actually given — drop just this step,
                # not necessarily the whole candidate.
                if not (0 <= index < len(pages)):
                    logger.warning(
                        "HostedAIProvider: dropped hallucinated page_index %r for candidate %r",
                        index,
                        name,
                    )
                    continue
                steps.append(
                    JourneyCandidateStep(
                        page_id=str(pages[index].id), stage_label=raw_step["stage_label"]
                    )
                )

            if not steps:
                logger.warning(
                    "HostedAIProvider: dropped candidate %r — zero valid steps remained", name
                )
                continue

            candidates.append(
                JourneyCandidate(
                    name=name,
                    capability_name=group["capability_name"],
                    steps=steps,
                    description=group.get("description", ""),
                )
            )
        return candidates

    async def generate_scenarios(
        self,
        journey: Journey,
        pages: list[Page],
        limit: int | None = None,
        requested_counts: dict[str, int] | None = None,
    ) -> list[ScenarioCandidate]:
        # `pages` is already in step order, each carrying a transient
        # `.stage_label` (attached by ScenarioGenerationActivity the same way
        # InferenceActivity attaches `.forms`/`.components`/etc) — so the
        # listing below doubles as both the step sequence and the supporting
        # capture detail, no separate steps argument needed.
        listing = "\n".join(f"{i + 1}: {_describe_page(p)}" for i, p in enumerate(pages))
        # A live-exploration Journey's `description` is the user's own,
        # original natural-language request — the only place any explicit
        # instruction (an exact field value, "cover happy/negative/edge",
        # a specific count) can ground scenario generation, since Discovery
        # never captures form-field validation constraints the way a live
        # MCP session's own typed values imply. A crawler-inferred Journey's
        # `description` is just its own short AI-written summary — safe to
        # include the same way, never harmful.
        description_section = (
            f'\nAdditional context — the request this Journey was created for:\n'
            f'"{journey.description}"\n'
            if journey.description
            else ""
        )
        live_session_listing = _describe_captured_flow(getattr(journey, "captured_flow", None))
        live_session_section = (
            f"\nRecorded live browser session (ground truth — the literal, ordered actions "
            f"actually taken against the real application for this Journey):\n{live_session_listing}\n"
            if live_session_listing
            else ""
        )

        candidates = []
        failures: list[str] = []
        for scenario_type, description in _SCENARIO_TYPE_DESCRIPTIONS.items():
            if limit is not None and len(candidates) >= limit:
                break
            exact_count = (requested_counts or {}).get(scenario_type)
            count_guidance = (
                f"Generate EXACTLY {exact_count} Scenario{'s' if exact_count != 1 else ''} of "
                "this type — no more, no fewer, regardless of how many distinct conditions you "
                "could otherwise think of."
                if exact_count
                else _SCENARIO_TYPE_DEFAULT_COUNT_GUIDANCE[scenario_type]
            )
            try:
                content = await _chat_completion(
                    [
                        {
                            "role": "system",
                            "content": _SCENARIO_PROMPT_SYSTEM.format(
                                scenario_type_instructions=f"{description} {count_guidance}"
                            ),
                        },
                        {
                            "role": "user",
                            "content": _SCENARIO_PROMPT_USER.format(
                                journey_name=journey.name,
                                journey_description_section=description_section,
                                step_listing=listing,
                                live_session_section=live_session_section,
                            ),
                        },
                    ],
                    response_format={"type": "json_object"},
                    timeout=240,
                    max_tokens=20000,
                )
                raw_scenarios = json.loads(content)["scenarios"]
            except Exception:
                # Fault isolation, same convention as elsewhere in this codebase
                # (Story 4.2): one bad batch is logged and skipped, not fatal to
                # the whole Journey's Scenarios — a truncated/failed "edge" call
                # should not also throw away an already-good "happy" batch.
                logger.exception(
                    "HostedAIProvider: dropped %r scenarios for journey %r", scenario_type, journey.name
                )
                failures.append(scenario_type)
                continue

            added_for_type = 0
            for raw in raw_scenarios:
                if limit is not None and len(candidates) >= limit:
                    break
                # The model is told to generate exactly `exact_count`, but
                # nothing downstream should ever trust an LLM's own count
                # discipline over an explicit user request — truncate here
                # the same way `limit` already does.
                if exact_count is not None and added_for_type >= exact_count:
                    break
                candidates.append(
                    ScenarioCandidate(
                        name=raw["name"],
                        # Forced from the loop, not trusted from the model —
                        # each call was already scoped to one type.
                        type=scenario_type,
                        steps=list(raw["steps"]),
                        expected_result=raw["expected_result"],
                        test_data=[
                            TestDataFieldCandidate(name=f["name"], mandatory=bool(f["mandatory"]))
                            for f in raw.get("test_data", [])
                        ],
                    )
                )
                added_for_type += 1

        if not candidates and failures:
            # Every scenario-type call errored — nothing was silently "fine",
            # the Journey just got zero Scenarios with no visible failure
            # (observed live: GenerationWorkflow reports Completed either
            # way, so Temporal's own retry_policy on the Activity never had
            # a failure to retry). Raising here only in the all-failed case
            # keeps the partial-success fault isolation above intact while
            # giving Temporal's already-configured retries something to act on.
            raise RuntimeError(
                f"HostedAIProvider: all scenario types failed for journey {journey.name!r}: {failures}"
            )
        return candidates

    # --- NLM prompt classification, shared by LiveExplorationTestWorkflow.
    # `[REMOVED]` match_test_case_scenarios/plan_new_journey/
    # generate_scenario_from_prompt — the "match a prompt against
    # already-crawled Journeys/Scenarios" agents. Per natural_language_flow.png,
    # natural-language test-case creation always goes through live browser
    # exploration, never a match against a prior crawl.

    async def analyze_test_case_prompt(self, prompt: str) -> TestCasePromptCandidate:
        content = await _chat_completion(
            [
                {"role": "system", "content": _TEST_CASE_PROMPT_SYSTEM},
                {"role": "user", "content": _TEST_CASE_PROMPT_USER.format(prompt=prompt)},
            ],
            response_format={"type": "json_object"},
            timeout=60,
        )
        raw = json.loads(content)
        provided_test_data = raw.get("provided_test_data") or {}
        requested_scenario_counts = raw.get("requested_scenario_counts") or {}
        return TestCasePromptCandidate(
            is_relevant=bool(raw["is_relevant"]),
            functionality_summary=raw.get("functionality_summary") or "",
            actions=list(raw.get("actions") or []),
            expected_result=raw.get("expected_result") or "",
            rejection_reason=raw.get("rejection_reason"),
            # Hallucination guard, same spirit as elsewhere in this file — a
            # non-string value (the model returning a number/bool/nested
            # object instead of the literal text it was given) is dropped
            # rather than trusted, since a malformed value here would flow
            # straight into a Scenario's test_data.
            provided_test_data={
                str(k): str(v)
                for k, v in provided_test_data.items()
                if isinstance(v, str) and v.strip()
            }
            if isinstance(provided_test_data, dict)
            else {},
            # Same hallucination guard — only a known category with a
            # positive integer count survives; anything else is dropped
            # rather than trusted, since a malformed value here would force
            # generate_scenarios to produce an unintended exact count.
            # The regex fallback fills in whatever the LLM's own call left
            # out — never overrides a category it did return.
            requested_scenario_counts={
                **_fallback_requested_scenario_counts(prompt),
                **(
                    {
                        str(k): int(v)
                        for k, v in requested_scenario_counts.items()
                        if str(k) in ("happy", "negative", "edge")
                        and isinstance(v, int)
                        and not isinstance(v, bool)
                        and v > 0
                    }
                    if isinstance(requested_scenario_counts, dict)
                    else {}
                ),
            },
        )

    async def infer_state_similarity(
        self, heading_a: str, actions_a: list[str], heading_b: str, actions_b: list[str]
    ) -> str:
        content = await _chat_completion(
            [
                {
                    "role": "user",
                    "content": _STATE_SIMILARITY_PROMPT.format(
                        heading_a=heading_a,
                        actions_a=actions_a,
                        heading_b=heading_b,
                        actions_b=actions_b,
                    ),
                }
            ],
            timeout=30,
        )
        return content.strip()

    async def classify_action_safety(self, label: str, page_context: str) -> str:
        content = await _chat_completion(
            [
                {
                    "role": "user",
                    "content": _ACTION_SAFETY_PROMPT.format(
                        label=label, page_context=page_context
                    ),
                }
            ],
            timeout=30,
        )
        return content.strip()

    async def decide_live_exploration_action(
        self,
        requirement: str,
        history: list[dict],
        snapshot: dict,
        *,
        is_heal: bool = False,
    ) -> LiveExplorationDecision:
        system_prompt = _LIVE_HEAL_PROMPT_SYSTEM if is_heal else _LIVE_EXPLORATION_PROMPT_SYSTEM
        user_template = _LIVE_HEAL_PROMPT_USER if is_heal else _LIVE_EXPLORATION_PROMPT_USER
        history_text = (
            "\n".join(
                f"{i}. called {turn.get('tool_name')}({turn.get('tool_args')}) — "
                f"{turn.get('rationale', '')}"
                for i, turn in enumerate(history)
            )
            or "(none yet)"
        )
        content = await _chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": user_template.format(
                        requirement=requirement,
                        history=history_text,
                        snapshot=json.dumps(snapshot),
                    ),
                },
            ],
            response_format={"type": "json_object"},
            timeout=60,
        )
        parsed = json.loads(content)
        return LiveExplorationDecision(
            tool_name=parsed["tool_name"],
            tool_args=parsed.get("tool_args") or {},
            rationale=parsed.get("rationale", ""),
            goal_satisfied=bool(parsed.get("goal_satisfied", False)),
        )

    async def generate_playwright(
        self,
        scenario: Scenario,
        known_pages: list[dict[str, str]] | None = None,
        known_locators: list[dict[str, str]] | None = None,
        *,
        requires_auth: bool = False,
        field_input_types: dict[str, str] | None = None,
        repair: tuple[str, list[str]] | None = None,
        previous_code: str | None = None,
        # Data-update path (Edit Test Data, Test Suite page) — mutually
        # exclusive with the failure_*/live_inspection_locators params below.
        # Requires previous_code; only used to swap in
        # _PLAYWRIGHT_DATA_UPDATE_CONTEXT instead of _PLAYWRIGHT_FAILURE_CONTEXT.
        changed_test_data: list[dict] | None = None,
        failure_error_message: str | None = None,
        failure_stack_trace: str | None = None,
        failure_console_output: str | None = None,
        target_url: str | None = None,
        failure_screenshot_png: bytes | None = None,
        live_inspection_locators: list[dict] | None = None,
        live_action_sequence: list[dict] | None = None,
    ) -> TestAssetCode:
        step_listing = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(scenario.steps))
        base_url = getattr(scenario, "base_url", None) or ""
        # `[FIXED]` requires_auth used to tell the model to call
        # `fillCredentials(page)` itself as a "precondition" — directly
        # contradicting the exported project's actual architecture
        # (`test_suite_assembler`'s `tests/auth.setup.ts` + `playwright.config.ts`
        # `authenticated` project + `storageState`), where an `@auth`-tagged
        # test already starts authenticated before its body runs. Observed
        # live: every `requires_auth=True` spec generated under the old
        # wording called `fillCredentials(page)` right after this same
        # prompt's own "visit base_url first" rule landed it on the public
        # marketing page — `fillCredentials` then timed out hunting for a
        # login field that only exists on the real login page, not `/`.
        auth_precondition_note = (
            "This Scenario's target page requires that authenticated session — do NOT call "
            "`fillCredentials`, do NOT navigate to any login page, and do not write any "
            "login-related code at all. Proceed straight to the Test steps below as an "
            "already-logged-in user would."
            if requires_auth
            else "This Scenario's target page does not require authentication."
        )
        initial_navigation_rule = (
            "This test already has that authenticated session applied — do NOT visit the "
            "application's base URL or any login page first. Navigate directly to the "
            "Scenario's actual target page as the very first action (via `page.goto(...)` to "
            "its known URL — see Known pages above — or by clicking a discovered link/button), "
            "exactly the way an already-logged-in user's browser would."
            if requires_auth
            else (
                f"Before navigating anywhere else, first visit the application's base URL "
                f"({base_url}) with `{{ timeout: NAVIGATION_TIMEOUT_MS }}` and wait for it to "
                "finish loading with `await page.waitForLoadState('networkidle', "
                "{ timeout: NAVIGATION_TIMEOUT_MS })`. This establishes the session/cookies a "
                "real user's browser would already have. Only after that initial visit should "
                "the test navigate on to whatever page the Scenario's steps actually need (via "
                "`page.goto`, or by clicking a discovered link/button). Never `page.goto()` "
                "straight to a deep URL as the first action of the test."
            )
        )
        if changed_test_data is not None:
            failure_context = _PLAYWRIGHT_DATA_UPDATE_CONTEXT.format(
                previous_code=previous_code,
                changed_data_listing=_describe_changed_test_data(changed_test_data),
            )
        elif previous_code is not None:
            failure_context = _PLAYWRIGHT_FAILURE_CONTEXT.format(
                previous_code=previous_code,
                target_url=target_url or "(unknown)",
                failure_error_message=failure_error_message or "(none)",
                failure_stack_trace=failure_stack_trace or "(none)",
                failure_console_output=failure_console_output or "(none)",
            )
        else:
            failure_context = ""
        live_inspection_context = (
            _PLAYWRIGHT_LIVE_INSPECTION_CONTEXT.format(
                live_locator_listing=_describe_live_locators(live_inspection_locators)
            )
            if live_inspection_locators
            else ""
        )
        live_action_sequence_context = (
            _PLAYWRIGHT_LIVE_ACTION_SEQUENCE_CONTEXT.format(
                action_sequence_listing=_describe_live_action_sequence(live_action_sequence)
            )
            if live_action_sequence
            else ""
        )
        system_message = {
            "role": "system",
            "content": _PLAYWRIGHT_PROMPT_SYSTEM.format(
                base_url=base_url,
                auth_precondition_note=auth_precondition_note,
                initial_navigation_rule=initial_navigation_rule,
            ),
        }
        user_text = _PLAYWRIGHT_PROMPT_USER.format(
            base_url=base_url,
            scenario_name=scenario.name,
            scenario_type=scenario.type,
            step_listing=step_listing,
            expected_result=scenario.expected_result,
            test_data_listing=_describe_test_data(scenario, field_input_types),
            known_pages_listing=_describe_known_pages(known_pages),
            known_locators_listing=_describe_known_locators(known_locators),
            failure_context=failure_context,
            live_inspection_context=live_inspection_context,
            live_action_sequence_context=live_action_sequence_context,
        )
        messages: list[dict[str, Any]] = [
            system_message,
            {"role": "user", "content": user_text},
        ]
        # Self-repair turn: a bare retry re-guesses blind and tends to repeat
        # the exact same tsc error (observed live — same TS2345 string/number
        # mistake across all 3 Temporal attempts). Handing back its own code
        # plus the real compiler output lets it fix the specific line instead.
        if repair is not None:
            repaired_code, typecheck_errors = repair
            messages.append({"role": "assistant", "content": repaired_code})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "That code failed TypeScript compilation:\n\n"
                        + "\n".join(typecheck_errors)
                        + "\n\nFix only what's needed to resolve these compile errors "
                        "(commonly: wrap a string value in `Number(...)` before passing it "
                        "to a numeric Playwright argument). Return the complete corrected "
                        "file, nothing else."
                    ),
                }
            )
        # A real Generate Suite submission fans out one Playwright call per
        # Scenario across every candidate Journey at once (a dozen+ Journeys
        # x dozens of Scenarios isn't unusual) — the default 60s timeout gets
        # exceeded once that concurrency is real, observed live as
        # `httpx.ReadTimeout` for a chunk of Scenarios (silently dropped by
        # SuiteGenerationWorkflow's per-Scenario fault isolation, no way to
        # tell "slow" from "actually broken"). Matches generate_scenarios'
        # own timeout=240 for the same reason.
        if failure_screenshot_png is not None:
            # Best-effort: assumes the configured AI_MODEL (via the LiteLLM
            # proxy) accepts vision input, which this codebase has no
            # capability-detection for — a rejection from the proxy falls
            # back to the plain text-only call rather than failing the
            # whole heal attempt.
            b64_screenshot = base64.b64encode(failure_screenshot_png).decode("ascii")
            vision_messages: list[dict[str, Any]] = [
                system_message,
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_screenshot}"},
                        },
                    ],
                },
            ]
            try:
                content = await _chat_completion(vision_messages, timeout=240)
            except Exception:
                logger.warning(
                    "HostedAIProvider: vision-inclusive heal call failed for scenario %r, "
                    "retrying without the screenshot",
                    scenario.name,
                )
                content = await _chat_completion(messages, timeout=240)
        else:
            content = await _chat_completion(messages, timeout=240)
        # No JSON response_format here (unlike infer_journeys/generate_scenarios)
        # — the model's own code fences are the one common failure mode worth
        # stripping defensively, since raw TypeScript code has no equivalent
        # structured-output guarantee to lean on.
        code = content.strip()
        # The bounded, AI-requested live-inspection fallback (see
        # _PLAYWRIGHT_FAILURE_CONTEXT's own closing instruction) — a literal
        # sentinel first line, since this response is plain TypeScript with
        # no structured-output channel to carry a real boolean flag.
        requests_live_inspection = code.startswith("NEEDS_LIVE_INSPECTION")
        if requests_live_inspection:
            code = code.split("\n", 1)[1].strip() if "\n" in code else ""
        if code.startswith("```"):
            code = code.split("\n", 1)[1] if "\n" in code else code
            if code.endswith("```"):
                code = code.rsplit("```", 1)[0]
            code = code.removeprefix("typescript\n").removeprefix("ts\n").strip()
        return TestAssetCode(code=code, requests_live_inspection=requests_live_inspection)
