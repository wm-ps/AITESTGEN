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

import json
import logging
import os
import re

import httpx
from domain import Journey, Page, Scenario

from ai_provider.journey_candidate import JourneyCandidate, JourneyCandidateStep
from ai_provider.scenario_candidate import ScenarioCandidate, TestDataFieldCandidate
from ai_provider.test_asset_code import TestAssetCode

AI_MODEL = os.environ.get("AI_MODEL", "anthropic/claude-sonnet-5")
LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")

logger = logging.getLogger(__name__)

# AC1 backstop: a Journey name must be business language, never a raw route/
# page identifier — this regex only catches the obvious case (starts with a
# path separator, or is bare host/URL-shaped); it's a defensive net behind
# prompting, not the primary enforcement mechanism.
_ROUTE_SHAPED_NAME = re.compile(r"^(/|https?://)")

_PROMPT = """You are analyzing a structured Application Model (canonical pages, their \
forms, automatable components, API calls, and how users actually navigate between \
pages) discovered from a web application, to identify the underlying business \
workflows ("Journeys") a QA engineer would care about.

Pages (indexed):
{page_listing}

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


def _describe_page(page: Page) -> str:
    components = [f"{c.type}:{c.name}" for c in getattr(page, "components", [])]
    forms = [f.action_url for f in getattr(page, "forms", [])]
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


_SCENARIO_PROMPT = """You are writing integration test Scenarios for a specific business \
Journey in a web application, based on its discovered steps and the underlying captured \
pages/forms/API calls.

Journey: "{journey_name}"

Steps (in order — each is a business-language stage of this Journey, with the captured \
page/form/API/component detail behind it):
{step_listing}

Generate integration test Scenarios covering this Journey, including a Happy Path, at \
least one Negative Path (a validation/error condition), and at least one Edge Case. Each \
Scenario needs:
- "name": a short business-language name (e.g. "Guest checkout with an expired card")
- "type": one of "happy", "negative", "edge"
- "steps": an ordered list of plain-language test steps a QA engineer would follow
- "expected_result": what should happen if the Scenario passes
- "test_data": a list of {{"name": "<field name, e.g. \\"username\\">", "mandatory": <bool>}} \
— the input values a human tester must supply to run this Scenario (e.g. login credentials, \
a card number, an expected confirmation value). Do NOT include a value — only the field name \
and whether it's required; a reviewer supplies the actual value later.

Respond with ONLY a JSON object of this shape, no prose: \
{{"scenarios": [{{"name": "...", "type": "happy", "steps": ["...", "..."], \
"expected_result": "...", "test_data": [{{"name": "...", "mandatory": true}}]}}, ...]}}"""

_PLAYWRIGHT_PROMPT = """You are converting one integration test Scenario into a single, \
executable Playwright (TypeScript, @playwright/test) test.

Application base URL: {base_url}

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

Known element locators (real Playwright selector strings discovered on this application, \
listed as "business stage name / component type:component name -> selector"). When a step \
interacts with an element matching one of these, use `page.locator("<selector>")` with this \
exact selector string — only invent your own selector (e.g. `page.getByRole(...)`) for an \
element with no match here:
{known_locators_listing}

Write one complete, runnable test using `import {{ test, expect }} from '@playwright/test'`, \
following the steps in order and asserting the expected result. Use the given test data \
values literally where they'd naturally be used (form fields, query params, etc).

Timeout rules — target applications vary widely in how long they take to load or process \
a submission. Define one constant near the top of the file and use it everywhere a timeout \
applies, rather than relying on Playwright's default:
const TIMEOUT_MS = 180000;
Pass `{{ timeout: TIMEOUT_MS }}` to every `page.goto(...)`, `page.waitForLoadState(...)`, \
`expect(...).toBeVisible(...)`/other `expect` assertions, and every locator action \
(`.click(...)`, `.fill(...)`, etc). In particular, after clicking a form's submit button, \
explicitly wait (with `TIMEOUT_MS`) for the resulting navigation or state change to \
complete before asserting anything about the outcome — do not assume it resolves instantly.

Not every Playwright method accepts a `timeout` option — do not add `{{ timeout: TIMEOUT_MS \
}}` to a call unless that specific method's signature actually has an options parameter. \
Most notably, `page.content()`, `page.url()`, and `response.status()` take NO arguments at \
all — calling e.g. `page.content({{ timeout: TIMEOUT_MS }})` is a compile error, not a slower \
call. When in doubt, only pass `{{ timeout: ... }}` to navigation (`page.goto`), waiting \
(`page.waitForLoadState`, `page.waitForURL`), locator actions (`.click`, `.fill`, `.check`, \
etc), and `expect(...)` assertions — never to a plain getter/accessor method.

Critical: Playwright's own overall per-test timeout defaults to 30000ms regardless of any \
`{{ timeout: TIMEOUT_MS }}` passed to individual calls — a longer per-assertion timeout does \
NOT extend how long the test as a whole is allowed to run, and the test will still be killed \
at 30 seconds even while an individual `expect(...)` is still legitimately waiting within its \
own 180000ms budget. There is no `playwright.config.ts` to raise this globally, so every \
generated test MUST raise its own timeout as the very first line inside the test body:
test('...', async ({{ page }}) => {{
  test.setTimeout(TIMEOUT_MS);
  // ...rest of the test
}});

Session/navigation rules — many target applications are session-dependent and will return \
a server error or broken markup if a deep link is the very first thing opened in a fresh \
browser context with no prior cookies. Follow these rules for every test, not just login \
Scenarios:

1. Before navigating anywhere else, first visit the application's base URL ({base_url}) with \
`{{ timeout: TIMEOUT_MS }}` and wait for it to finish loading with `await \
page.waitForLoadState('networkidle', {{ timeout: TIMEOUT_MS }})`. This establishes the \
session/cookies a real user's browser would already have. Only after that initial visit \
should the test navigate on to whatever page the Scenario's steps actually need (via \
`page.goto`, or by clicking a discovered link/button). Never `page.goto()` straight to a \
deep URL as the first action of the test.

2. After every `page.goto(...)` call, capture the returned response and verify it \
succeeded before doing anything else with the page:
const response = await page.goto(url, {{ timeout: TIMEOUT_MS }});
if (!response || response.status() >= 400) {{
  throw new Error(`Failed to load page. HTTP status: ${{response?.status()}}`);
}}

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

Combine the CSS-attribute options as one comma-separated selector passed to `page.locator(...)` \
and take `.first()`, so any one of them matching resolves the field unambiguously. Assert \
visibility (with `{{ timeout: TIMEOUT_MS }}`) before interacting, so a locator mismatch fails \
clearly instead of a confusing fill/click error. For example, instead of:
await page.getByLabel(/password/i).fill(password);
generate:
const passwordField = page.locator(
  'input[name="password"], input[type="password"], input[id="password"]'
).first();
await expect(passwordField).toBeVisible({{ timeout: TIMEOUT_MS }});
await passwordField.fill(password);

Never treat a button (e.g. `<button aria-label="Show password">`, `<button aria-label="Hide \
password">`, or any other visibility-toggle control) as a candidate for a text/password \
input locator — always constrain field locators to `input` elements only. Only fall back to \
an accessibility-based locator (`getByLabel`/`getByPlaceholder`) for a field when no \
CSS attribute selector for it is available, and even then only if that locator's regex is \
specific enough that it would not plausibly also match a button or other non-field control.

Field-level validation rules — when a step checks that a field shows a validation/error \
state (e.g. "shows required field error", "marks the field invalid"), do NOT search the \
page for arbitrary validation-message text. Assert on the field's own state/attributes \
instead, using whichever of these is applicable: `input[name="..."][aria-invalid="true"]`, \
`input[name="..."][data-validate="..."]` (or any other application-specific validation \
attribute implied by the step), or the native `:invalid` pseudo-class. Only assert on \
visible error text if that exact text is given to you via the Test data or Expected result \
above — never invent your own generic message (e.g. "This field is required") and search \
for it.

Failure-outcome assertion rules — the same "don't invent wording" rule applies to any \
failure/error outcome, not just field validation (e.g. an invalid-login message). Use the \
literal text ONLY if it is explicitly given to you via the Test data or Expected result \
above — copy it verbatim, never paraphrase or invent your own phrasing. If no literal \
expected message text is given, do not assert on any specific fabricated wording at all; \
instead assert on an observable, application-agnostic signal that the action failed. Prefer \
checking that the page did NOT navigate away from where the failing action was attempted \
(e.g. compare `page.url()` before and after, or assert the same form/field is still present) \
as the primary signal — this is always queryable regardless of the application's markup \
conventions. Only additionally assert a generic error/alert container becoming visible \
(e.g. `page.locator('[role="alert"], .error, [aria-live]').first()`) when you have reason to \
believe the application actually renders one — never assert on that locator as your ONLY \
failure signal, since many applications validate via native browser dialogs or custom markup \
this pattern won't match, and a test that only waits on it will time out even though the \
action genuinely failed as expected. Never hardcode a message like "Invalid username or \
password" unless that exact string was given to you as data.

Step-ordering rule — perform every listed Test step, in order, BEFORE asserting the Expected \
result. Never assert the Expected result (or any failure/success signal derived from it) \
before the actions that are supposed to produce it have actually been executed — e.g. do not \
check for a login-error indicator before filling in credentials and clicking submit.

Output ONLY the TypeScript code, no markdown fences, no prose, no explanation."""


def _describe_test_data(scenario: Scenario) -> str:
    return "\n".join(f"- {f['name']}: {f.get('value')}" for f in scenario.test_data) or "(none)"


def _describe_known_pages(known_pages: list[dict[str, str]] | None) -> str:
    if not known_pages:
        return "(none)"
    return "\n".join(f"- {p['stage_label']} -> {p['url']}" for p in known_pages)


def _describe_known_locators(known_locators: list[dict[str, str]] | None) -> str:
    if not known_locators:
        return "(none)"
    return "\n".join(
        f"- {loc['stage_label']} / {loc['component_type']}:{loc['component_name']} -> "
        f"{loc['selector']}"
        for loc in known_locators
    )


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


class HostedAIProvider:
    """`AIProvider` (Protocol) adapter backed by a LiteLLM proxy server."""

    async def infer_journeys(self, pages: list[Page]) -> list[JourneyCandidate]:
        listing = "\n".join(f"{i}: {_describe_page(p)}" for i, p in enumerate(pages))
        payload = {
            "model": AI_MODEL,
            "messages": [{"role": "user", "content": _PROMPT.format(page_listing=listing)}],
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(base_url=LITELLM_BASE_URL, timeout=60) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
                json=payload,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
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
        self, journey: Journey, pages: list[Page]
    ) -> list[ScenarioCandidate]:
        # `pages` is already in step order, each carrying a transient
        # `.stage_label` (attached by ScenarioGenerationActivity the same way
        # InferenceActivity attaches `.forms`/`.components`/etc) — so the
        # listing below doubles as both the step sequence and the supporting
        # capture detail, no separate steps argument needed.
        listing = "\n".join(f"{i + 1}: {_describe_page(p)}" for i, p in enumerate(pages))
        payload = {
            "model": AI_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": _SCENARIO_PROMPT.format(
                        journey_name=journey.name, step_listing=listing
                    ),
                }
            ],
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(base_url=LITELLM_BASE_URL, timeout=60) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
                json=payload,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        raw_scenarios = json.loads(content)["scenarios"]

        candidates = []
        for raw in raw_scenarios:
            candidates.append(
                ScenarioCandidate(
                    name=raw["name"],
                    type=raw["type"],
                    steps=list(raw["steps"]),
                    expected_result=raw["expected_result"],
                    test_data=[
                        TestDataFieldCandidate(name=f["name"], mandatory=bool(f["mandatory"]))
                        for f in raw.get("test_data", [])
                    ],
                )
            )
        return candidates

    async def infer_state_similarity(
        self, heading_a: str, actions_a: list[str], heading_b: str, actions_b: list[str]
    ) -> str:
        payload = {
            "model": AI_MODEL,
            "messages": [
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
        }
        async with httpx.AsyncClient(base_url=LITELLM_BASE_URL, timeout=30) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
                json=payload,
            )
            response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    async def classify_action_safety(self, label: str, page_context: str) -> str:
        payload = {
            "model": AI_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": _ACTION_SAFETY_PROMPT.format(
                        label=label, page_context=page_context
                    ),
                }
            ],
        }
        async with httpx.AsyncClient(base_url=LITELLM_BASE_URL, timeout=30) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
                json=payload,
            )
            response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    async def generate_playwright(
        self,
        scenario: Scenario,
        known_pages: list[dict[str, str]] | None = None,
        known_locators: list[dict[str, str]] | None = None,
    ) -> TestAssetCode:
        step_listing = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(scenario.steps))
        base_url = getattr(scenario, "base_url", None) or ""
        payload = {
            "model": AI_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": _PLAYWRIGHT_PROMPT.format(
                        base_url=base_url,
                        scenario_name=scenario.name,
                        scenario_type=scenario.type,
                        step_listing=step_listing,
                        expected_result=scenario.expected_result,
                        test_data_listing=_describe_test_data(scenario),
                        known_pages_listing=_describe_known_pages(known_pages),
                        known_locators_listing=_describe_known_locators(known_locators),
                    ),
                }
            ],
        }
        async with httpx.AsyncClient(base_url=LITELLM_BASE_URL, timeout=60) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
                json=payload,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        # No JSON response_format here (unlike infer_journeys/generate_scenarios)
        # — the model's own code fences are the one common failure mode worth
        # stripping defensively, since raw TypeScript code has no equivalent
        # structured-output guarantee to lean on.
        code = content.strip()
        if code.startswith("```"):
            code = code.split("\n", 1)[1] if "\n" in code else code
            if code.endswith("```"):
                code = code.rsplit("```", 1)[0]
            code = code.removeprefix("typescript\n").removeprefix("ts\n").strip()
        return TestAssetCode(code=code)
