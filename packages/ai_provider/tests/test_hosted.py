"""HostedAIProvider (Story 2.6, Task 2).

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
from domain import Page


def _fake_page(url: str, title: str = "") -> Page:
    return Page(application_id=uuid.uuid4(), discovery_run_id=uuid.uuid4(), url=url, title=title)


def test_infer_journeys_maps_page_indices_to_page_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page0 = _fake_page("https://app.example.com/items", title="Items")
    page1 = _fake_page("https://app.example.com/items/new", title="Add item")
    page2 = _fake_page("https://app.example.com/about", title="About")

    fake_response_body = json.dumps(
        {
            "journeys": [
                {
                    "name": "Browse items",
                    "capability_name": "Item Management",
                    "page_indices": [0, 1],
                },
                {
                    "name": "View about page",
                    "capability_name": "Marketing",
                    "page_indices": [2],
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

    candidates = HostedAIProvider().infer_journeys([page0, page1, page2])

    assert len(candidates) == 2
    assert candidates[0].name == "Browse items"
    assert candidates[0].capability_name == "Item Management"
    assert candidates[0].page_ids == [str(page0.id), str(page1.id)]
    assert candidates[1].page_ids == [str(page2.id)]

    assert captured_kwargs["response_format"] == {"type": "json_object"}
    assert "model" in captured_kwargs


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="requires a real ANTHROPIC_API_KEY (or AI_MODEL's provider key) — not provisioned here",
)
def test_infer_journeys_live_call() -> None:
    pages = [
        _fake_page("https://app.example.com/cart", title="Cart"),
        _fake_page("https://app.example.com/checkout", title="Checkout"),
    ]
    candidates = HostedAIProvider().infer_journeys(pages)
    assert candidates
    assert all(isinstance(c.name, str) and c.name for c in candidates)
