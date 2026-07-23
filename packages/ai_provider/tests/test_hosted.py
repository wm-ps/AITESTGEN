"""HostedAIProvider (Story 2.6, Task 2).

`infer_journeys`' parsing/mapping logic is tested here with
`httpx.AsyncClient.post` monkeypatched — no real proxy key or network call
needed. A real live call against the configured proxy is a separate,
skip-cleanly integration test (requires `LITELLM_BASE_URL`/`LITELLM_API_KEY`)
since this environment has no provisioned proxy.
"""

import json
import os
import uuid

import httpx
import pytest
from ai_provider.hosted import HostedAIProvider
from domain import Page, Scenario


def _fake_page(url: str, title: str = "") -> Page:
    return Page(application_id=uuid.uuid4(), discovery_run_id=uuid.uuid4(), url=url, title=title)


def _monkeypatch_post(monkeypatch: pytest.MonkeyPatch, fake_response_body: str) -> dict:
    captured: dict = {}

    async def fake_post(self, url, *, headers=None, json=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": fake_response_body}}]},
            request=httpx.Request("POST", "https://fake-proxy.example.com/chat/completions"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return captured


async def test_infer_journeys_maps_ordered_steps_to_page_ids(
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
                    "steps": [
                        {"page_index": 0, "stage_label": "Browse"},
                        {"page_index": 1, "stage_label": "Add Item"},
                    ],
                },
                {
                    "name": "View about page",
                    "capability_name": "Marketing",
                    "steps": [{"page_index": 2, "stage_label": "About"}],
                },
            ]
        }
    )

    captured = _monkeypatch_post(monkeypatch, fake_response_body)

    candidates = await HostedAIProvider().infer_journeys([page0, page1, page2])

    assert len(candidates) == 2
    assert candidates[0].name == "Browse items"
    assert candidates[0].capability_name == "Item Management"
    assert [s.page_id for s in candidates[0].steps] == [str(page0.id), str(page1.id)]
    assert [s.stage_label for s in candidates[0].steps] == ["Browse", "Add Item"]
    assert [s.page_id for s in candidates[1].steps] == [str(page2.id)]

    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert "model" in captured["json"]
    assert captured["headers"]["Authorization"].startswith("Bearer ")


async def test_infer_journeys_rejects_route_shaped_name(monkeypatch: pytest.MonkeyPatch) -> None:
    page0 = _fake_page("https://app.example.com/checkout", title="Checkout")
    fake_response_body = json.dumps(
        {
            "journeys": [
                {
                    "name": "/checkout/step-2",
                    "capability_name": "Order Management",
                    "steps": [{"page_index": 0, "stage_label": "Checkout"}],
                }
            ]
        }
    )
    _monkeypatch_post(monkeypatch, fake_response_body)

    candidates = await HostedAIProvider().infer_journeys([page0])

    assert candidates == []


async def test_infer_journeys_drops_hallucinated_page_index_keeping_valid_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page0 = _fake_page("https://app.example.com/cart", title="Cart")
    fake_response_body = json.dumps(
        {
            "journeys": [
                {
                    "name": "Checkout",
                    "capability_name": "Order Management",
                    "steps": [
                        {"page_index": 0, "stage_label": "Cart"},
                        {"page_index": 99, "stage_label": "Nonexistent"},
                    ],
                }
            ]
        }
    )
    _monkeypatch_post(monkeypatch, fake_response_body)

    candidates = await HostedAIProvider().infer_journeys([page0])

    assert len(candidates) == 1
    assert [s.page_id for s in candidates[0].steps] == [str(page0.id)]


async def test_infer_journeys_drops_whole_candidate_when_zero_valid_steps_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page0 = _fake_page("https://app.example.com/cart", title="Cart")
    fake_response_body = json.dumps(
        {
            "journeys": [
                {
                    "name": "All Hallucinated",
                    "capability_name": "Order Management",
                    "steps": [{"page_index": 99, "stage_label": "Nonexistent"}],
                }
            ]
        }
    )
    _monkeypatch_post(monkeypatch, fake_response_body)

    candidates = await HostedAIProvider().infer_journeys([page0])

    assert candidates == []


@pytest.mark.skipif(
    not (os.environ.get("LITELLM_BASE_URL") and os.environ.get("LITELLM_API_KEY")),
    reason="requires a real LiteLLM proxy (LITELLM_BASE_URL/LITELLM_API_KEY) — "
    "not provisioned here",
)
async def test_infer_journeys_live_call() -> None:
    pages = [
        _fake_page("https://app.example.com/cart", title="Cart"),
        _fake_page("https://app.example.com/checkout", title="Checkout"),
    ]
    candidates = await HostedAIProvider().infer_journeys(pages)
    assert candidates
    assert all(isinstance(c.name, str) and c.name for c in candidates)


def _fake_scenario(**overrides) -> Scenario:
    defaults = dict(
        journey_id=uuid.uuid4(),
        type="happy",
        name="Guest checkout",
        steps=["Add item to cart", "Submit payment"],
        expected_result="Order confirmation is shown",
        test_data=[{"name": "username", "mandatory": True, "value": "qa-user"}],
        generation_run_id=1,
    )
    defaults.update(overrides)
    return Scenario(**defaults)


async def test_generate_playwright_returns_code(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _monkeypatch_post(
        monkeypatch, "def test_guest_checkout():\n    pass\n"
    )
    scenario = _fake_scenario()

    result = await HostedAIProvider().generate_playwright(scenario)

    # Trailing whitespace is stripped by `generate_playwright` itself.
    assert result.code == "def test_guest_checkout():\n    pass"
    assert "Guest checkout" in captured["json"]["messages"][0]["content"]
    assert "qa-user" in captured["json"]["messages"][0]["content"]
    # No response_format here — raw Playwright source, not JSON.
    assert "response_format" not in captured["json"]


async def test_generate_playwright_strips_markdown_code_fences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _monkeypatch_post(
        monkeypatch, "```python\ndef test_guest_checkout():\n    pass\n```"
    )
    scenario = _fake_scenario()

    result = await HostedAIProvider().generate_playwright(scenario)

    assert result.code == "def test_guest_checkout():\n    pass"
    assert "```" not in result.code
