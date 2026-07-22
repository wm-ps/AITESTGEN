"""AIProvider port (architecture AD-3).

Every inference/generation call in the platform goes through this interface —
no Activity may import an AI vendor SDK directly. Implementations
(HostedAIProvider for SaaS, CustomerEndpointAIProvider for on-prem, deferred)
land in the epics that own them (Epic 2 / Epic 7), not in this story.

`infer_journeys` reads the structured Application Model (Story 2.5) —
canonical `Page` rows, never raw Evidence (removed in full 2026-07-18) or a
superseded/merged row. `generate_scenarios` returns `ScenarioCandidate`s
(Story 4.1), mirroring `infer_journeys`'s `JourneyCandidate` shape — the
Activity, not this port, converts candidates into real `Scenario` rows.
`generate_playwright` still uses `Any` — `TestAssetCode` isn't built by this
story (Story 4.2's job); `Any` stands in so nothing invented here can drift
from the real type once it lands. `[CORRECTED 2026-07-21]` `generate_scenarios`
is `async` — it was previously declared sync in this Protocol, which never
matched `infer_journeys`'s real (network I/O) shape.
"""

from typing import Any, Protocol

from domain import Journey, Page

from ai_provider.journey_candidate import JourneyCandidate
from ai_provider.scenario_candidate import ScenarioCandidate


class AIProvider(Protocol):
    async def infer_journeys(self, pages: list[Page]) -> list[JourneyCandidate]: ...

    async def generate_scenarios(
        self, journey: Journey, pages: list[Page]
    ) -> list[ScenarioCandidate]: ...

    def generate_playwright(self, scenario: Any) -> Any:
        """scenario: Scenario -> TestAssetCode."""
        ...
