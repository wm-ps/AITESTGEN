"""JourneyCandidate — HostedAIProvider.infer_journeys' output shape (Story 2.6).

Not a `packages/domain` entity — this is the AI's raw grouping of canonical
Pages before `InferenceActivity` persists it as a `Journey` row. `page_ids`
holds `str(Page.id)` (Page has no `external_id` — it's never exposed to the
frontend directly) so `InferenceActivity` can attribute exactly the right
canonical Page (and, through it, Form/ApiEndpoint/Component) rows and
compute `identity_key` from their actual shape (AD-13) — never from `name`,
which the AI may phrase slightly differently run to run.
"""

from dataclasses import dataclass


@dataclass
class JourneyCandidate:
    name: str
    capability_name: str
    page_ids: list[str]
