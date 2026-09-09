"""analyze_prompt_activity — the bridge between HostedAIProvider's
TestCasePromptCandidate and the workflow's PromptAnalysisResult. Exercises
the real activity function end to end (HTTP call to the AI proxy
monkeypatched) — `test_hosted.py` only tests `HostedAIProvider` directly and
a workflow test's own fake activity only tests the orchestration shape, so
neither catches a field silently dropped in this bridge (exactly what
happened to `requested_scenario_counts`: added to both dataclasses and to
`HostedAIProvider`, but never forwarded here — silent because the field has
a default)."""

import json

import httpx
import pytest
from generation_worker.add_test_case_activities import analyze_prompt_activity
from workflows import AnalyzePromptActivityInput

pytestmark = pytest.mark.asyncio


def _body(**overrides) -> str:
    payload = {
        "is_relevant": True,
        "functionality_summary": "Add a GIT MCP connection",
        "actions": [],
        "expected_result": "",
        "provided_test_data": {},
        "requested_scenario_counts": {"happy": 1, "negative": 1, "edge": 1},
        "rejection_reason": None,
    }
    payload.update(overrides)
    return json.dumps(payload)


async def test_forwards_requested_scenario_counts_through_to_the_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post(self, url, *, headers=None, json=None):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": _body()}}]},
            request=httpx.Request("POST", "https://fake-proxy.example.com/chat/completions"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await analyze_prompt_activity(
        AnalyzePromptActivityInput(prompt="Create three test cases: happy, negative, edge.")
    )

    assert result.requested_scenario_counts == {"happy": 1, "negative": 1, "edge": 1}
