"""TestCasePromptCandidate — HostedAIProvider.analyze_test_case_prompt's output
shape (NLM "Add Test Case" feature).

Not a `packages/domain` entity, same reasoning as `JourneyCandidate`/
`ScenarioCandidate` — the AI's raw read of a user's plain-English request,
before any Journey/Scenario matching or creation happens. `is_relevant=False`
is the Out-of-Scope Validation gate: a prompt unrelated to this Application's
functionality/test behavior is rejected here, before any DB write beyond the
request itself.

`provided_test_data` is the entire "Test data" input surface for this
feature — everything is prompt-based (no separate data-entry form): any
concrete value the user states directly in their prompt (e.g. "using promo
code EXPIRED10") is extracted here and used mandatorily; anything not
mentioned is resolved from the existing Test Data Pool or left for
`PlaywrightGenerationActivity`'s own existing default-value synthesis to
fill in, exactly like a normal-flow Scenario. Extracted, never invented — a
value not literally present in the prompt is never guessed at here.
"""

from dataclasses import dataclass, field


@dataclass
class TestCasePromptCandidate:
    is_relevant: bool
    functionality_summary: str = ""
    actions: list[str] = field(default_factory=list)
    expected_result: str = ""
    rejection_reason: str | None = None
    provided_test_data: dict[str, str] = field(default_factory=dict)
