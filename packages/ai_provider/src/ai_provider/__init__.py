"""AIProvider port (architecture AD-3).

Every inference/generation call in the platform goes through this interface —
no Activity may import an AI vendor SDK directly. Implementations
(HostedAIProvider for SaaS, CustomerEndpointAIProvider for on-prem, deferred)
land in the epics that own them (Epic 2 / Epic 7), not in this story.

The real domain types this Protocol references (Evidence, JourneyCandidate,
Journey, Scenario, TestAssetCode) are built by their owning epics, not this
scaffold story — `Any` stands in for them here rather than a placeholder
class, so nothing invented here can drift from the real type once it lands.
"""

from typing import Any, Protocol


class AIProvider(Protocol):
    def infer_journeys(self, evidence: list[Any]) -> list[Any]:
        """evidence: list[Evidence] -> list[JourneyCandidate]."""
        ...

    def generate_scenarios(self, journey: Any, evidence: list[Any]) -> list[Any]:
        """journey: Journey, evidence: list[Evidence] -> list[Scenario]."""
        ...

    def generate_playwright(self, scenario: Any) -> Any:
        """scenario: Scenario -> TestAssetCode."""
        ...
