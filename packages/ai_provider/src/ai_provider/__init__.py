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
`[CORRECTED 2026-07-21]` `generate_scenarios` is `async` — it was previously
declared sync in this Protocol, which never matched `infer_journeys`'s real
(network I/O) shape. `[ADDED 2026-07-23]` `generate_playwright` (Story 4.2)
now has its real `Scenario -> TestAssetCode` signature, `async` for the same
reason.
"""

from typing import Protocol

from domain import Journey, Page, Scenario

from ai_provider.journey_candidate import JourneyCandidate
from ai_provider.scenario_candidate import ScenarioCandidate
from ai_provider.test_asset_code import TestAssetCode


class AIProvider(Protocol):
    async def infer_journeys(self, pages: list[Page]) -> list[JourneyCandidate]: ...

    async def generate_scenarios(
        self, journey: Journey, pages: list[Page]
    ) -> list[ScenarioCandidate]: ...

    async def generate_playwright(self, scenario: Scenario) -> TestAssetCode: ...
