"""ScenarioCandidate — HostedAIProvider.generate_scenarios' output shape (Story 4.1).

Not a `packages/domain` entity, same reasoning as `JourneyCandidate` — the
AI's raw output before `ScenarioGenerationActivity` persists it as a
`Scenario` row. `test_data` fields never carry a value here — the AI defines
what's needed (name + whether it's mandatory), a reviewer supplies the value
later.
"""

from dataclasses import dataclass


@dataclass
class TestDataFieldCandidate:
    __test__ = False  # pytest: not a test class, despite the name prefix

    name: str
    mandatory: bool


@dataclass
class ScenarioCandidate:
    name: str
    type: str
    steps: list[str]
    expected_result: str
    test_data: list[TestDataFieldCandidate]
