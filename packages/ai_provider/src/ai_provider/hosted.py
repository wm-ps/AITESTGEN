"""HostedAIProvider — the first real `AIProvider` adapter (Story 2.6, AD-3).

Backed by `litellm` rather than a direct vendor SDK — no AI vendor is named
in the PRD or Architecture Spine, resolved for this build via `litellm`
(confirmed with the user during story creation). `litellm` is the one unified
client that speaks a single interface across providers, so the model string
is a config value (`AI_MODEL` env var), not a code change — this is what
lets a future hosted/on-prem or vendor swap touch only this file (AD-3).

Reads canonical `Page` rows (Story 2.5's Application Model), each optionally
carrying transient `.forms`/`.components`/`.api_endpoints`/
`.outgoing_transitions`/`.assertions` attributes that `InferenceActivity`
attaches before calling this — richer context than a bare page URL, but this
provider tolerates their absence (`getattr(..., [])`) so it stays usable
against a plain `list[Page]` in isolation (e.g. tests).

Requires an API key for whichever provider `AI_MODEL` names — for the
default Anthropic model, `ANTHROPIC_API_KEY` (litellm reads it directly).
`CustomerEndpointAIProvider` (on-prem) has no story to build it in — Epic 7
is removed; not built here or anywhere else without a fresh product decision.
"""

import json
import logging
import os
import re

import litellm
from domain import Page

from ai_provider.journey_candidate import JourneyCandidate, JourneyCandidateStep

AI_MODEL = os.environ.get("AI_MODEL", "anthropic/claude-sonnet-5")

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
- "steps": an ordered list of {{"page_index": <int>, "stage_label": "<short \
business-language stage name, e.g. \\"Login\\" or \\"MFA Verification\\">"}} — one \
entry per page (from the indexed list above) that supports this Journey, in flow order

Respond with ONLY a JSON object of this shape, no prose: \
{{"journeys": [{{"name": "...", "capability_name": "...", "steps": [ \
{{"page_index": 0, "stage_label": "..."}}, {{"page_index": 2, "stage_label": "..."}}]}}, ...]}}"""


def _describe_page(page: Page) -> str:
    components = [f"{c.type}:{c.name}" for c in getattr(page, "components", [])]
    forms = [f.action_url for f in getattr(page, "forms", [])]
    api_calls = [f"{e.method} {e.path}" for e in getattr(page, "api_endpoints", [])]
    outgoing_transitions = [t.url for t in getattr(page, "outgoing_transitions", [])]
    assertions = [
        f"{a.kind}:{a.expected_value}" for a in getattr(page, "assertions", [])
    ]
    return json.dumps(
        {
            "url": page.url,
            "title": page.title,
            "components": components,
            "forms": forms,
            "api_calls": api_calls,
            "outgoing_transitions": outgoing_transitions,
            "assertions": assertions,
        }
    )


class HostedAIProvider:
    """`AIProvider` (Protocol) adapter backed by litellm."""

    def infer_journeys(self, pages: list[Page]) -> list[JourneyCandidate]:
        listing = "\n".join(f"{i}: {_describe_page(p)}" for i, p in enumerate(pages))
        response = litellm.completion(
            model=AI_MODEL,
            messages=[{"role": "user", "content": _PROMPT.format(page_listing=listing)}],
            response_format={"type": "json_object"},
        )
        # litellm's return type also covers streaming responses; this call
        # never sets stream=True, so it's always the non-streaming shape.
        content = response.choices[0].message.content  # type: ignore[union-attr]
        assert content is not None
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
                    name=name, capability_name=group["capability_name"], steps=steps
                )
            )
        return candidates
