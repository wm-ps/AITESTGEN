"""Shared NLM building blocks — prompt analysis and single-TestAsset
execution, used by `LiveExplorationTestWorkflow` (`live_exploration_workflow.py`).

`[REMOVED]` `AddTestCaseWorkflow` — the "match a prompt against already-
crawled Journeys/Scenarios, reuse or create one" pipeline — used to live
here too. Per `natural_language_flow.png`, natural-language test-case
creation always goes through live browser exploration (LangGraph agent +
Playwright MCP against the real app), never a match against a prior crawl;
`AddTestCaseWorkflow` and its crawled-data-matching Activities
(`IdentifyScenariosActivity`/`CreateJourneyActivity`/`CreateScenarioActivity`)
are gone. `AnalyzePromptActivity` (prompt -> relevance/summary, no DB reads)
and `PrepareSingleTestRunActivity`/`ReadTestResultStatusActivity` (assemble
+ execute one already-generated TestAsset) are generic — no dependency on a
prior crawl — so `LiveExplorationTestWorkflow` still uses them as-is.
"""

from dataclasses import dataclass, field

ANALYZE_PROMPT_ACTIVITY_NAME = "AnalyzePromptActivity"
PREPARE_SINGLE_TEST_RUN_ACTIVITY_NAME = "PrepareSingleTestRunActivity"
READ_TEST_RESULT_STATUS_ACTIVITY_NAME = "ReadTestResultStatusActivity"
DISCARD_TEST_RUN_ACTIVITY_NAME = "DiscardTestRunActivity"


@dataclass
class AnalyzePromptActivityInput:
    prompt: str


@dataclass
class PromptAnalysisResult:
    is_relevant: bool
    functionality_summary: str = ""
    actions: list[str] = field(default_factory=list)
    expected_result: str = ""
    rejection_reason: str | None = None
    # Test Data Priority: mandatory when the user stated it directly in
    # their prompt; never asked for otherwise.
    provided_test_data: dict[str, str] = field(default_factory=dict)
    # Only populated when the user's own prompt states an explicit total or
    # per-category scenario count — threaded into
    # ScenarioGenerationActivityInput so that count overrides the normal
    # free-running per-type generation.
    requested_scenario_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class PrepareSingleTestRunActivityInput:
    application_id: str
    test_asset_id: str


@dataclass
class PrepareSingleTestRunActivityResult:
    test_run_id: str
    test_result_id: str


@dataclass
class ReadTestResultStatusActivityInput:
    test_result_id: str


@dataclass
class ReadTestResultStatusResult:
    status: str
    error_message: str | None = None


@dataclass
class DiscardTestRunActivityInput:
    test_run_id: str


__all__ = [
    "ANALYZE_PROMPT_ACTIVITY_NAME",
    "DISCARD_TEST_RUN_ACTIVITY_NAME",
    "PREPARE_SINGLE_TEST_RUN_ACTIVITY_NAME",
    "READ_TEST_RESULT_STATUS_ACTIVITY_NAME",
    "AnalyzePromptActivityInput",
    "DiscardTestRunActivityInput",
    "PrepareSingleTestRunActivityInput",
    "PrepareSingleTestRunActivityResult",
    "PromptAnalysisResult",
    "ReadTestResultStatusActivityInput",
    "ReadTestResultStatusResult",
]
