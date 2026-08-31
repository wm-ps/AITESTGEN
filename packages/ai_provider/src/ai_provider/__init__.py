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
reason. `[ADDED 2026-08-05]` `generate_playwright` also takes optional
`known_pages`/`known_locators` — real crawled Pages/ComponentLocators for the
Scenario's Journey, letting the AI ground generated code in discovered URLs/
selectors instead of inventing its own. `[CORRECTED, self-heal]` this
Protocol had drifted out of sync with `HostedAIProvider`'s real
`generate_playwright` implementation, which had already grown `repair`
(compile-time self-repair) and `previous_code`/`failure_error_message`/
`failure_stack_trace`/`failure_console_output`/`target_url`/
`failure_screenshot_png` (runtime self-heal) without this Protocol ever
being updated — corrected here, together with `live_inspection_locators`
(self-heal's targeted live-inspection evidence), so this stays the one
place a caller's type-check actually reflects the real port.
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

    async def generate_playwright(
        self,
        scenario: Scenario,
        known_pages: list[dict[str, str]] | None = None,
        known_locators: list[dict[str, str]] | None = None,
        *,
        requires_auth: bool = False,
        field_input_types: dict[str, str] | None = None,
        repair: tuple[str, list[str]] | None = None,
        previous_code: str | None = None,
        failure_error_message: str | None = None,
        failure_stack_trace: str | None = None,
        failure_console_output: str | None = None,
        target_url: str | None = None,
        failure_screenshot_png: bytes | None = None,
        live_inspection_locators: list[dict] | None = None,
    ) -> TestAssetCode: ...

    # Story 2.10 AC 3: called only when the State Identity Engine's score
    # falls in the ambiguous band. Returns a short plain-language opinion —
    # supporting evidence recorded in run diagnostics, never authoritative;
    # the caller must not let this change the verdict it already computed.
    async def infer_state_similarity(
        self, heading_a: str, actions_a: list[str], heading_b: str, actions_b: list[str]
    ) -> str: ...

    # Story 2.12 AC 3: called only for an action the Safety Engine's own verb
    # lists couldn't classify at all. Same contract as
    # `infer_state_similarity` — a short plain-language opinion, supporting
    # evidence recorded in diagnostics, never authoritative; the caller's
    # posture-driven verdict is already decided before this is even awaited.
    async def classify_action_safety(self, label: str, page_context: str) -> str: ...
