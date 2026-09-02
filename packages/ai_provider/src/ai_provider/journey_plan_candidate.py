"""JourneyPlanCandidate — HostedAIProvider.plan_new_journey's output shape
(NLM "Add Test Case" feature).

Only produced when `ScenarioMatchCandidate.mode == "new_journey"` — no
existing Journey covers the user's requested test case, so this picks and
orders the relevant Pages from the Application's already-discovered Page
catalog (never invents application behavior, per "Application Context").
Same `(page_id, stage_label)` shape as `JourneyCandidateStep`
(`journey_candidate.py`) — `CreateScenarioActivity` persists one `JourneyStep`
per entry, exactly as `InferenceActivity` does for a crawl-discovered Journey.
"""

from dataclasses import dataclass, field


@dataclass
class JourneyPlanStep:
    page_id: str
    stage_label: str


@dataclass
class JourneyPlanCandidate:
    steps: list[JourneyPlanStep] = field(default_factory=list)
