"""AIProvider port (architecture AD-3).

Every inference/generation call in the platform goes through this interface —
no Activity may import an AI vendor SDK directly. Implementations
(HostedAIProvider for SaaS, CustomerEndpointAIProvider for on-prem, deferred)
land in the epics that own them (Epic 2 / Epic 7), not in this story.

`infer_journeys` uses the real `Evidence`/`JourneyCandidate` types now that
Story 2.2/2.5 have built them. `generate_scenarios`/`generate_playwright`
still use `Any` — `Journey`/`Scenario`/`TestAssetCode` for those calls aren't
built by this story (Epic 4's job); `Any` stands in so nothing invented here
can drift from the real type once it lands, same reasoning Story 1.1 used
for this whole file.
"""

from typing import Any, Protocol

from domain import Evidence

from ai_provider.journey_candidate import JourneyCandidate


class AIProvider(Protocol):
    def infer_journeys(self, evidence: list[Evidence]) -> list[JourneyCandidate]: ...

    def generate_scenarios(self, journey: Any, evidence: list[Any]) -> list[Any]:
        """journey: Journey, evidence: list[Evidence] -> list[Scenario]."""
        ...

    def generate_playwright(self, scenario: Any) -> Any:
        """scenario: Scenario -> TestAssetCode."""
        ...
