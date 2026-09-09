"""AnalyzePromptActivity — shared NLM prompt classification.

`[REMOVED]` `IdentifyScenariosActivity`/`CreateJourneyActivity`/
`CreateScenarioActivity` — the "match a prompt against already-crawled
Journeys/Scenarios, reuse or create one" pipeline — used to live here too.
Per `natural_language_flow.png`, natural-language test-case creation always
goes through live browser exploration, never a match against a prior crawl;
`LiveExplorationTestWorkflow` (`live_exploration_activities.py`) is the only
caller of this feature now, and only needs prompt relevance/summary
extraction — no DB reads, no dependency on a prior crawl.
"""

from ai_provider.hosted import HostedAIProvider
from temporalio import activity
from workflows import AnalyzePromptActivityInput, PromptAnalysisResult


@activity.defn(name="AnalyzePromptActivity")
async def analyze_prompt_activity(input: AnalyzePromptActivityInput) -> PromptAnalysisResult:
    candidate = await HostedAIProvider().analyze_test_case_prompt(input.prompt)
    return PromptAnalysisResult(
        is_relevant=candidate.is_relevant,
        functionality_summary=candidate.functionality_summary,
        actions=candidate.actions,
        expected_result=candidate.expected_result,
        rejection_reason=candidate.rejection_reason,
        provided_test_data=candidate.provided_test_data,
        requested_scenario_counts=candidate.requested_scenario_counts,
    )
