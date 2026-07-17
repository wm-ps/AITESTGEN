"""JourneyCandidate — HostedAIProvider.infer_journeys' output shape (Story 2.5).

Not a `packages/domain` entity — this is the AI's raw grouping of Evidence
before `InferenceActivity` persists it as a `Journey` row. `evidence_external_ids`
lets `InferenceActivity` attribute exactly the right `Evidence` rows
(`journey_id`) and compute `identity_key` from their actual shape (AD-13) —
never from `name`, which the AI may phrase slightly differently run to run.
"""

from dataclasses import dataclass


@dataclass
class JourneyCandidate:
    name: str
    capability_name: str
    evidence_external_ids: list[str]
