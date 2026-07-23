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
executable Playwright (Python, sync API) test function.

Scenario: "{scenario_name}" ({scenario_type})

Test steps:
{step_listing}

Expected result: {expected_result}

Test data (use these exact values in the generated code, they are already resolved — \
either reviewer-provided or a sensible default):
{test_data_listing}

Write one complete, runnable `test_...` function using `playwright.sync_api`, following \
the steps in order and asserting the expected result. Use the given test data values \
literally where they'd naturally be used (form fields, query params, etc). Output ONLY \
the Python code, no markdown fences, no prose, no explanation."""


def _describe_test_data(scenario: Scenario) -> str:
    return "\n".join(f"- {f['name']}: {f.get('value')}" for f in scenario.test_data) or "(none)"


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

    async def generate_playwright(self, scenario: Scenario) -> TestAssetCode:
        step_listing = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(scenario.steps))
        payload = {
            "model": AI_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": _PLAYWRIGHT_PROMPT.format(
                        scenario_name=scenario.name,
                        scenario_type=scenario.type,
                        step_listing=step_listing,
                        expected_result=scenario.expected_result,
                        test_data_listing=_describe_test_data(scenario),
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
        # stripping defensively, since raw Python code has no equivalent
        # structured-output guarantee to lean on.
        code = content.strip()
        if code.startswith("```"):
            code = code.split("\n", 1)[1] if "\n" in code else code
            if code.endswith("```"):
                code = code.rsplit("```", 1)[0]
            code = code.removeprefix("python\n").strip()
        return TestAssetCode(code=code)
