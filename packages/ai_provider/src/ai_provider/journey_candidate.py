"""JourneyCandidate — HostedAIProvider.infer_journeys' output shape (Story 2.6).

Not a `packages/domain` entity — this is the AI's raw grouping of canonical
Pages before `InferenceActivity` persists it as a `Journey` row. `steps` is
an **ordered** list of `(page_id, stage_label)` pairs, in the sequence the AI
infers a user actually moves through the flow — replaces the earlier flat,
unordered `page_ids` list, since a Journey without order/stage is not
distinguishable from an unordered bag of pages. `page_id` holds
`str(Page.id)` (Page has no `external_id` — it's never exposed to the
frontend directly) so `InferenceActivity` can attribute exactly the right
canonical Page (and, through it, Form/ApiEndpoint/Component) rows and
compute `identity_key` from their actual shape (AD-13) — never from `name`
or step order, which the AI may vary run to run.
"""

from dataclasses import dataclass


@dataclass
class JourneyCandidateStep:
    page_id: str
    stage_label: str


@dataclass
class JourneyCandidate:
    name: str
    capability_name: str
    steps: list[JourneyCandidateStep]
