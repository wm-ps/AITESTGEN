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
from ai_provider.hosted import HostedAIProvider, _describe_form
from domain import Form, Journey, Page, Scenario


def _fake_page(url: str, title: str = "") -> Page:
    return Page(application_id=uuid.uuid4(), discovery_run_id=uuid.uuid4(), url=url, title=title)


def _fake_form(action_url: str, fields: list[dict]) -> Form:
    form = Form(
        application_id=uuid.uuid4(),
        discovery_run_id=uuid.uuid4(),
        page_id=uuid.uuid4(),
        action_url=action_url,
        method="POST",
    )
    # Transient, same technique `scenario_generation_activity` uses to attach
    # each field's captured `ValidationRule`s (generation_worker/activities.py).
    object.__setattr__(form, "fields", fields)
    return form


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


_LOGIN_URL = "https://digitalbankingportal.onwavemaker.com/Account/Login"
# Real Chrome's own native `validationMessage` text for an empty
# `required` input — what `crawler.py`'s `checkValidity()` call actually
# captures, not a made-up string.
_REQUIRED_MESSAGE = "Please fill out this field."


def test_describe_form_reports_html5_message_when_username_is_missing() -> None:
    # Username left empty, password filled in — mirrors what the crawler
    # captures on https://digitalbankingportal.onwavemaker.com/Account/Login
    # when only the username field fails constraint validation.
    form = _fake_form(
        _LOGIN_URL,
        fields=[
            {
                "name": "username",
                "rules": [
                    {"rule_type": "required", "value": None},
                    {"rule_type": "html5_message", "value": _REQUIRED_MESSAGE},
                ],
            },
            {"name": "password", "rules": [{"rule_type": "required", "value": None}]},
        ],
    )

    described = _describe_form(form)

    assert described["action_url"] == _LOGIN_URL
    rules_by_field = {f["name"]: f["validation_rules"] for f in described["fields"]}
    assert {"rule_type": "html5_message", "value": _REQUIRED_MESSAGE} in rules_by_field["username"]
    # Password was filled in — still "required", but no validation message.
    assert rules_by_field["password"] == [{"rule_type": "required", "value": None}]


def test_describe_form_reports_html5_message_when_password_is_missing() -> None:
    # Password left empty, username filled in — the mirror case.
    form = _fake_form(
        _LOGIN_URL,
        fields=[
            {"name": "username", "rules": [{"rule_type": "required", "value": None}]},
            {
                "name": "password",
                "rules": [
                    {"rule_type": "required", "value": None},
                    {"rule_type": "html5_message", "value": _REQUIRED_MESSAGE},
                ],
            },
        ],
    )

    described = _describe_form(form)

    assert described["action_url"] == _LOGIN_URL
    rules_by_field = {f["name"]: f["validation_rules"] for f in described["fields"]}
    assert {"rule_type": "html5_message", "value": _REQUIRED_MESSAGE} in rules_by_field["password"]
    assert rules_by_field["username"] == [{"rule_type": "required", "value": None}]


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


def _fake_journey(**overrides) -> Journey:
    defaults = dict(
        application_id=uuid.uuid4(),
        discovery_run_id=uuid.uuid4(),
        name="Guest checkout",
        identity_key=f"identity-{uuid.uuid4()}",
    )
    defaults.update(overrides)
    return Journey(**defaults)


def _scenario_body(name: str) -> str:
    return json.dumps(
        {
            "scenarios": [
                {
                    "name": name,
                    "type": "SOMETHING-THE-MODEL-MADE-UP",
                    "steps": ["step 1"],
                    "expected_result": "it works",
                    "test_data": [],
                }
            ]
        }
    )


async def test_generate_scenarios_batches_by_type_and_forces_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bodies = iter(
        [_scenario_body("Happy scenario"), _scenario_body("Negative scenario"), _scenario_body("Edge scenario")]
    )
    captured_calls: list[dict] = []

    async def fake_post(self, url, *, headers=None, json=None):
        captured_calls.append(json)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": next(bodies)}}]},
            request=httpx.Request("POST", "https://fake-proxy.example.com/chat/completions"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    candidates = await HostedAIProvider().generate_scenarios(_fake_journey(), [_fake_page("https://a.example.com")])

    # One call per type, not one call for everything — bounds each call's
    # output separately so a large Journey can't get silently capped.
    assert len(captured_calls) == 3
    assert [c.name for c in candidates] == ["Happy scenario", "Negative scenario", "Edge scenario"]
    # Forced from which call produced it, never trusted from the model's own
    # (possibly wrong) "type" field.
    assert [c.type for c in candidates] == ["happy", "negative", "edge"]


async def test_generate_scenarios_isolates_a_failed_type_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]},
                request=httpx.Request("POST", "https://fake-proxy.example.com/chat/completions"),
            ),
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": _scenario_body("Negative scenario")}}]},
                request=httpx.Request("POST", "https://fake-proxy.example.com/chat/completions"),
            ),
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": _scenario_body("Edge scenario")}}]},
                request=httpx.Request("POST", "https://fake-proxy.example.com/chat/completions"),
            ),
        ]
    )

    async def fake_post(self, url, *, headers=None, json=None):
        return next(responses)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    candidates = await HostedAIProvider().generate_scenarios(_fake_journey(), [_fake_page("https://a.example.com")])

    # The truncated "happy" batch is dropped, but "negative"/"edge" still
    # make it through — one bad batch doesn't lose the whole Journey.
    assert [c.name for c in candidates] == ["Negative scenario", "Edge scenario"]


async def test_generate_scenarios_raises_when_every_type_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post(self, url, *, headers=None, json=None):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    # All 3 types erroring must raise, not return [] — a Journey with zero
    # Scenarios and no error is indistinguishable from "the model legitimately
    # found nothing", and it means GenerationWorkflow's retry_policy (which
    # only retries a *failed* Activity) never gets a chance to retry a
    # transient failure like this one.
    with pytest.raises(RuntimeError, match="all scenario types failed"):
        await HostedAIProvider().generate_scenarios(
            _fake_journey(), [_fake_page("https://a.example.com")]
        )


async def test_generate_playwright_returns_code(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _monkeypatch_post(
        monkeypatch,
        "import { test, expect } from '@playwright/test'\n\n"
        "test('guest checkout', async ({ page }) => {})\n",
    )
    scenario = _fake_scenario()

    result = await HostedAIProvider().generate_playwright(scenario)

    # Trailing whitespace is stripped by `generate_playwright` itself.
    assert result.code == (
        "import { test, expect } from '@playwright/test'\n\n"
        "test('guest checkout', async ({ page }) => {})"
    )
    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "Guest checkout" in content
    assert "qa-user" in content
    # No response_format here — raw Playwright source, not JSON.
    assert "response_format" not in captured["json"]


async def test_generate_playwright_strips_markdown_code_fences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _monkeypatch_post(
        monkeypatch,
        "```typescript\ntest('guest checkout', async ({ page }) => {})\n```",
    )
    scenario = _fake_scenario()

    result = await HostedAIProvider().generate_playwright(scenario)

    assert result.code == "test('guest checkout', async ({ page }) => {})"
    assert "```" not in result.code


async def test_generate_playwright_forbids_fillcredentials_when_requires_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[FIXED]` requires_auth=True used to instruct the model to call
    `fillCredentials(page)` itself as a login "precondition" — directly
    contradicting the exported project's real architecture, where an
    `@auth`-tagged spec already starts authenticated via `storageState`
    (set up once by `tests/auth.setup.ts`). Combined with this same prompt's
    own "visit the base URL first" rule, every such spec called
    `fillCredentials` on the public marketing page instead of the real login
    page, timing out hunting for a login field that was never there."""
    captured = _monkeypatch_post(monkeypatch, "test('x', async ({ page }) => {})")
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(scenario, requires_auth=True)

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "do NOT call `fillCredentials`" in content
    assert "do NOT visit the application's base URL" in content


async def test_generate_playwright_allows_base_url_visit_when_no_auth_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _monkeypatch_post(monkeypatch, "test('x', async ({ page }) => {})")
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(scenario, requires_auth=False)

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "first visit the application's base URL" in content
    assert "do NOT visit the application's base URL" not in content


async def test_generate_playwright_includes_known_pages_in_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _monkeypatch_post(
        monkeypatch, "test('guest checkout', async ({ page }) => {})"
    )
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(
        scenario,
        known_pages=[{"stage_label": "Checkout", "url": "https://app.example.com/checkout"}],
    )

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "Known pages" in content
    assert "Checkout -> https://app.example.com/checkout" in content


async def test_generate_playwright_degrades_gracefully_with_no_known_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _monkeypatch_post(
        monkeypatch, "test('guest checkout', async ({ page }) => {})"
    )
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(scenario)

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "Known pages" in content
    assert "(none)" in content


async def test_generate_playwright_includes_known_locators_in_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _monkeypatch_post(
        monkeypatch, "test('guest checkout', async ({ page }) => {})"
    )
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(
        scenario,
        known_locators=[
            {
                "stage_label": "Checkout",
                "component_type": "button",
                "component_name": "Save button",
                "selector": '[data-testid="save"]',
            }
        ],
    )

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "Known element locators" in content
    assert 'Checkout / button:Save button -> [data-testid="save"]' in content


async def test_generate_playwright_renders_label_strategy_as_getbylabel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`label=` isn't a real Playwright selector engine — a "label" strategy \
    locator must render as a ready-to-call `getByLabel(...)`, never interpolated \
    into a `page.locator("label=\\"...\\"")` string."""
    captured = _monkeypatch_post(
        monkeypatch, "test('guest checkout', async ({ page }) => {})"
    )
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(
        scenario,
        known_locators=[
            {
                "stage_label": "Login",
                "component_type": "input",
                "component_name": "Username field",
                "selector": "Username",
                "strategy": "label",
            }
        ],
    )

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert 'Login / input:Username field -> getByLabel("Username")' in content
    assert 'label="Username"' not in content


async def test_generate_playwright_degrades_gracefully_with_no_known_locators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _monkeypatch_post(
        monkeypatch, "test('guest checkout', async ({ page }) => {})"
    )
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(scenario)

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "Known element locators" in content
    assert "(none)" in content


async def test_infer_state_similarity_returns_the_raw_opinion_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 2.10 AC 3 — a short plain-language opinion, not JSON; the
    caller records it as supporting evidence and never parses/branches on
    it as a structured decision."""
    captured = _monkeypatch_post(
        monkeypatch, "VARIANT: state B shows Approve/Reject actions state A doesn't have."
    )

    result = await HostedAIProvider().infer_state_similarity(
        heading_a="Claim Details",
        actions_a=["Edit", "Submit"],
        heading_b="Claim Details",
        actions_b=["Approve", "Reject"],
    )

    assert result == "VARIANT: state B shows Approve/Reject actions state A doesn't have."
    assert "Claim Details" in captured["json"]["messages"][0]["content"]
    assert "Approve" in captured["json"]["messages"][0]["content"]
    # Plain text opinion — no JSON response_format, matching generate_playwright.
    assert "response_format" not in captured["json"]


async def test_classify_action_safety_returns_the_raw_opinion_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 2.12 AC 3 — supporting evidence only, recorded in diagnostics;
    the Safety Engine's posture-driven verdict never depends on this."""
    captured = _monkeypatch_post(
        monkeypatch, "AMBIGUOUS: archiving may trigger a downstream workflow."
    )

    result = await HostedAIProvider().classify_action_safety(
        label="Archive", page_context="Claim Details page, status: Open"
    )

    assert result == "AMBIGUOUS: archiving may trigger a downstream workflow."
    assert "Archive" in captured["json"]["messages"][0]["content"]
    assert "Claim Details" in captured["json"]["messages"][0]["content"]
    assert "response_format" not in captured["json"]
