"""TestAssetCode — HostedAIProvider.generate_playwright's output shape (Story 4.2).

Not a `packages/domain` entity, same reasoning as `ScenarioCandidate`/
`JourneyCandidate` — the AI's raw output before `PlaywrightGenerationActivity`
persists it as a `TestAsset` row.
"""

from dataclasses import dataclass


@dataclass
class TestAssetCode:
    __test__ = False  # pytest: not a test class, despite the name prefix

    code: str
