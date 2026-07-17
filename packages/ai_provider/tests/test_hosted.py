"""HostedAIProvider (Story 2.5, Task 2).

`infer_journeys`' parsing/mapping logic is tested here with `litellm.completion`
monkeypatched — no real API key or network call needed. A real live call
against the configured model is a separate, skip-cleanly integration test
(requires `ANTHROPIC_API_KEY` or whatever `AI_MODEL` needs) since this
environment has no provisioned key.
"""

import json
import os
import uuid
from types import SimpleNamespace

import litellm
import pytest
from ai_provider.hosted import HostedAIProvider
from domain import Evidence


def _fake_evidence(evidence_type: str, details: dict) -> Evidence:
    return Evidence(
        discovery_run_id=uuid.uuid4(),
        type=evidence_type,
        details=details,
    )


def test_infer_journeys_maps_evidence_indices_to_external_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ev0 = _fake_evidence("page", {"url": "https://app.example.com/items"})
    ev1 = _fake_evidence("api_call", {"url": "https://app.example.com/api/items", "method": "GET"})
    ev2 = _fake_evidence("page", {"url": "https://app.example.com/about"})

    fake_response_body = json.dumps(
        {
            "journeys": [
                {
                    "name": "Browse items",
                    "capability_name": "Item Management",
                    "evidence_indices": [0, 1],
                },
                {
                    "name": "View about page",
                    "capability_name": "Marketing",
                    "evidence_indices": [2],
                },
            ]
        }
    )

    captured_kwargs = {}

    def fake_completion(**kwargs):
        captured_kwargs.update(kwargs)
        message = SimpleNamespace(content=fake_response_body)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])

    monkeypatch.setattr(litellm, "completion", fake_completion)

    candidates = HostedAIProvider().infer_journeys([ev0, ev1, ev2])

    assert len(candidates) == 2
    assert candidates[0].name == "Browse items"
    assert candidates[0].capability_name == "Item Management"
    assert candidates[0].evidence_external_ids == [str(ev0.external_id), str(ev1.external_id)]
    assert candidates[1].evidence_external_ids == [str(ev2.external_id)]

    assert captured_kwargs["response_format"] == {"type": "json_object"}
    assert "model" in captured_kwargs


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="requires a real ANTHROPIC_API_KEY (or AI_MODEL's provider key) — not provisioned here",
)
def test_infer_journeys_live_call() -> None:
    evidence = [
        _fake_evidence("page", {"url": "https://app.example.com/cart"}),
        _fake_evidence(
            "api_call", {"url": "https://app.example.com/api/checkout", "method": "POST"}
        ),
    ]
    candidates = HostedAIProvider().infer_journeys(evidence)
    assert candidates
    assert all(isinstance(c.name, str) and c.name for c in candidates)
