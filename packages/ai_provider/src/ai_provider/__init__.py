"""AIProvider port (architecture AD-3).

Every inference/generation call in the platform goes through this interface —
no Activity may import an AI vendor SDK directly. Implementations
(HostedAIProvider for SaaS, CustomerEndpointAIProvider for on-prem, deferred)
land in the epics that own them (Epic 2 / Epic 7), not in this story.

`infer_journeys` reads the structured Application Model (Story 2.5) —
canonical `Page` rows, never raw Evidence (removed in full 2026-07-18) or a
superseded/merged row. `generate_scenarios`/`generate_playwright` still use
`Any` — `Journey`/`Scenario`/`TestAssetCode` for those calls aren't built by
this story (Epic 4's job); `Any` stands in so nothing invented here can
drift from the real type once it lands.
"""

from typing import Any, Protocol

from domain import Page

from ai_provider.journey_candidate import JourneyCandidate


class AIProvider(Protocol):
    def infer_journeys(self, pages: list[Page]) -> list[JourneyCandidate]: ...

    def generate_scenarios(self, journey: Any, pages: list[Any]) -> list[Any]:
        """journey: Journey, pages: list[Page] -> list[Scenario]."""
        ...

    def generate_playwright(self, scenario: Any) -> Any:
        """scenario: Scenario -> TestAssetCode."""
        ...
