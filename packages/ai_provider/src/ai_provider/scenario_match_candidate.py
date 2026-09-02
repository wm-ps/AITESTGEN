"""ScenarioMatchCandidate — HostedAIProvider.match_test_case_scenarios' output
shape (NLM "Add Test Case" feature).

A single user request can require ONE test case or SEVERAL — this is always
a list (`match_test_case_scenarios`' return type), one entry per distinct
Scenario the request decomposes into (e.g. "test that login and logout both
work" is two). Each entry independently carries the Journey/Scenario
Decision (reuse an existing Scenario, add a new Scenario under an existing
Journey, or create a new Journey) and its own
`functionality_summary`/`actions`/`expected_result` — specific to just that
one Scenario, not a repeat of the whole original request. Not a
`packages/domain` entity — `CreateJourneyActivity`/`CreateScenarioActivity`
(`add_test_case_activities.py`) turn this into real `Journey`/`Scenario`
rows, applying Duplicate Prevention checks the AI's own judgment isn't
trusted to enforce on its own.
"""

from dataclasses import dataclass, field
from typing import Literal

ScenarioMatchMode = Literal["reuse_scenario", "new_scenario", "new_journey"]


@dataclass
class ScenarioMatchCandidate:
    mode: ScenarioMatchMode
    journey_id: str | None = None
    scenario_id: str | None = None
    proposed_journey_name: str | None = None
    proposed_capability_name: str | None = None
    proposed_scenario_name: str = ""
    functionality_summary: str = ""
    actions: list[str] = field(default_factory=list)
    expected_result: str = ""
    rationale: str = ""
