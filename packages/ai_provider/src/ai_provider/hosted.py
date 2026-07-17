"""HostedAIProvider — the first real `AIProvider` adapter (Story 2.5, AD-3).

Backed by `litellm` rather than a direct vendor SDK — no AI vendor is named
in the PRD or Architecture Spine, resolved for this build via `litellm`
(confirmed with the user during story creation). `litellm` is the one unified
client that speaks a single interface across providers, so the model string
is a config value (`AI_MODEL` env var), not a code change — this is what
lets a future hosted/on-prem or vendor swap touch only this file (AD-3).

Requires an API key for whichever provider `AI_MODEL` names — for the
default Anthropic model, `ANTHROPIC_API_KEY` (litellm reads it directly).
`CustomerEndpointAIProvider` (on-prem) has no story to build it in — Epic 7
is removed; not built here or anywhere else without a fresh product decision.
"""

import json
import os

import litellm
from domain import Evidence

from ai_provider.journey_candidate import JourneyCandidate

AI_MODEL = os.environ.get("AI_MODEL", "anthropic/claude-sonnet-5")

_PROMPT = """You are analyzing raw web-application discovery evidence (captured pages, \
form submissions, UI actions, and API calls) to identify the underlying business \
workflows ("Journeys") a QA engineer would care about.

Evidence items (indexed):
{evidence_listing}

Group these evidence items into candidate Journeys. Each Journey needs:
- "name": a short business-language name (e.g. "Add item to list") — never a raw \
route or page identifier
- "capability_name": the broader business capability this Journey belongs to \
(e.g. "Item Management")
- "evidence_indices": the indices (from the list above) of every evidence item that \
supports this Journey

Respond with ONLY a JSON object of this shape, no prose: \
{{"journeys": [{{"name": "...", "capability_name": "...", "evidence_indices": [0, 2]}}, ...]}}"""


class HostedAIProvider:
    """`AIProvider` (Protocol) adapter backed by litellm."""

    def infer_journeys(self, evidence: list[Evidence]) -> list[JourneyCandidate]:
        listing = "\n".join(
            f"{i}: type={item.type} details={json.dumps(item.details)}"
            for i, item in enumerate(evidence)
        )
        response = litellm.completion(
            model=AI_MODEL,
            messages=[{"role": "user", "content": _PROMPT.format(evidence_listing=listing)}],
            response_format={"type": "json_object"},
        )
        # litellm's return type also covers streaming responses; this call
        # never sets stream=True, so it's always the non-streaming shape.
        content = response.choices[0].message.content  # type: ignore[union-attr]
        assert content is not None
        groups = json.loads(content)["journeys"]

        candidates = []
        for group in groups:
            indices = group["evidence_indices"]
            candidates.append(
                JourneyCandidate(
                    name=group["name"],
                    capability_name=group["capability_name"],
                    evidence_external_ids=[str(evidence[i].external_id) for i in indices],
                )
            )
        return candidates
