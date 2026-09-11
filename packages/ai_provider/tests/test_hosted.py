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


async def test_generate_scenarios_grounds_prompt_in_journey_description_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A live-exploration Journey's `description` is the user's own original
    request (e.g. an explicit field value, or "cover happy/negative/edge") —
    the only place that instruction can reach scenario generation, since
    Discovery never captures form-field validation constraints the way a
    live MCP session's typed values imply."""
    captured = _monkeypatch_post(monkeypatch, _scenario_body("Happy scenario"))

    await HostedAIProvider().generate_scenarios(
        _fake_journey(description="Fill Server type with GIT and Endpoint URL with the repo URL."),
        [_fake_page("https://a.example.com")],
        limit=1,
    )

    assert "Fill Server type with GIT" in captured["json"]["messages"][1]["content"]


async def test_generate_scenarios_omits_description_section_when_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _monkeypatch_post(monkeypatch, _scenario_body("Happy scenario"))

    await HostedAIProvider().generate_scenarios(
        _fake_journey(), [_fake_page("https://a.example.com")], limit=1
    )

    assert "Additional context" not in captured["json"]["messages"][1]["content"]


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


async def test_generate_scenarios_prompt_excludes_the_account_own_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credential-handling fix: the scenario prompt used to cite "login
    credentials" as an example of legitimate test_data, which is exactly what
    led the model to invent "username"/"password" fields for a plain sign-in
    Scenario — later hardcoded as a literal by the Playwright generator. The
    prompt must no longer offer that example, and must explicitly say the
    account's own existing credential is never test_data."""
    captured_calls: list[dict] = []

    async def fake_post(self, url, *, headers=None, json=None):
        captured_calls.append(json)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": _scenario_body("Sign in")}}]},
            request=httpx.Request("POST", "https://fake-proxy.example.com/chat/completions"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await HostedAIProvider().generate_scenarios(_fake_journey(), [_fake_page("https://a.example.com")])

    content = "".join(m["content"] for m in captured_calls[0]["messages"])
    assert "login credentials" not in content
    assert "never include a field for the account's own existing login" in content


def _scenario_body_multi(names: list[str]) -> str:
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
                for name in names
            ]
        }
    )


async def test_generate_scenarios_truncates_to_an_exact_requested_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A user's explicit "3 test cases: happy/negative/edge" must never come
    back as 9 — even if the model over-generates for one type despite being
    told an exact count, the result is truncated to it, the same way `limit`
    already truncates."""
    bodies = iter(
        [
            _scenario_body("Happy 1"),
            _scenario_body_multi(["Negative 1", "Negative 2", "Negative 3"]),
            _scenario_body("Edge 1"),
        ]
    )

    async def fake_post(self, url, *, headers=None, json=None):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": next(bodies)}}]},
            request=httpx.Request("POST", "https://fake-proxy.example.com/chat/completions"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    candidates = await HostedAIProvider().generate_scenarios(
        _fake_journey(),
        [_fake_page("https://a.example.com")],
        requested_counts={"happy": 1, "negative": 1, "edge": 1},
    )

    assert [c.name for c in candidates] == ["Happy 1", "Negative 1", "Edge 1"]


async def test_generate_scenarios_tells_the_model_an_exact_count_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_calls: list[dict] = []

    async def fake_post(self, url, *, headers=None, json=None):
        captured_calls.append(json)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": _scenario_body("Scenario")}}]},
            request=httpx.Request("POST", "https://fake-proxy.example.com/chat/completions"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await HostedAIProvider().generate_scenarios(
        _fake_journey(),
        [_fake_page("https://a.example.com")],
        requested_counts={"negative": 1},
    )

    # `[FIXED]` A user who asked for a specific type at all is implicitly
    # saying "only that" — a type they never mentioned ("happy", "edge"
    # here) is skipped entirely rather than still running with its
    # free-running default guidance, which used to pad in scenario types
    # nobody asked for on top of the one requested type.
    assert len(captured_calls) == 1
    negative_system_prompt = captured_calls[0]["messages"][0]["content"]
    assert "EXACTLY 1 Scenario" in negative_system_prompt


async def test_generate_scenarios_runs_every_type_with_default_guidance_when_none_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty `requested_counts` (no type named at all, e.g. a plain
    "test the checkout flow" prompt) keeps today's default full-spread
    behavior — every type still runs, none are skipped."""
    captured_calls: list[dict] = []

    async def fake_post(self, url, *, headers=None, json=None):
        captured_calls.append(json)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": _scenario_body("Scenario")}}]},
            request=httpx.Request("POST", "https://fake-proxy.example.com/chat/completions"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await HostedAIProvider().generate_scenarios(
        _fake_journey(),
        [_fake_page("https://a.example.com")],
        requested_counts={},
    )

    assert len(captured_calls) == 3


async def test_generate_scenarios_grounds_prompt_in_the_recorded_live_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Journey.captured_flow` (the literal live-exploration transcript) must
    reach the scenario prompt verbatim, and the model must be told to ground
    steps in it — this is what stops an invented "settings button" locator
    from ever reaching a generated Scenario."""
    captured = _monkeypatch_post(monkeypatch, _scenario_body("Happy scenario"))

    await HostedAIProvider().generate_scenarios(
        _fake_journey(
            captured_flow=[
                {
                    "tool_name": "browser_click",
                    "element_description": "settings icon for the first tenant",
                    "typed_value": None,
                    "page_url": "https://a.example.com/tenants/mcp",
                    "page_heading": "MCP Connections",
                    "rationale": "open the mcp-connections page",
                }
            ]
        ),
        [_fake_page("https://a.example.com")],
        limit=1,
    )

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "Recorded live browser session" in content
    assert "settings icon for the first tenant" in content
    assert "must name only elements/pages/values that appear in it" in content


async def test_generate_scenarios_omits_live_session_section_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _monkeypatch_post(monkeypatch, _scenario_body("Happy scenario"))

    await HostedAIProvider().generate_scenarios(
        _fake_journey(), [_fake_page("https://a.example.com")], limit=1
    )

    assert "Recorded live browser session" not in captured["json"]["messages"][1]["content"]


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


async def test_generate_playwright_data_update_uses_existing_code_not_failure_framing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edit Test Data (Test Suite page) — `changed_test_data` swaps in
    `_PLAYWRIGHT_DATA_UPDATE_CONTEXT` instead of `_PLAYWRIGHT_FAILURE_CONTEXT`:
    the existing code and the changed field(s) reach the prompt, but none of
    the failure/diagnosis framing (which would read nonsensically for a
    plain data edit) does."""
    captured = _monkeypatch_post(
        monkeypatch,
        "import { test, expect } from '@playwright/test'\n\n"
        "test('guest checkout', async ({ page }) => {})\n",
    )
    scenario = _fake_scenario()
    previous_code = (
        "import { test, expect } from '@playwright/test'\n\n"
        "test('guest checkout', { tag: '@public' }, async ({ page }) => {\n"
        "  await page.getByLabel('Username', { exact: true }).fill('qa-user');\n"
        "});\n"
    )

    await HostedAIProvider().generate_playwright(
        scenario,
        previous_code=previous_code,
        changed_test_data=[{"name": "username", "mandatory": True, "value": "new-qa-user"}],
    )

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert previous_code in content
    assert "new-qa-user" in content
    assert "already exists and its logic is correct" in content
    # None of the failure/diagnosis-only framing leaked into a plain data edit.
    assert "target URL at time of failure" not in content
    assert "stack trace" not in content
    assert "NEEDS_LIVE_INSPECTION" not in content


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


async def test_generate_playwright_prompt_uses_a_distinct_navigation_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Navigation-reliability fix: a full page load legitimately takes longer
    than a single locator action, so `page.goto(...)` and the
    `waitForLoadState(...)` call right after it must get their own, longer
    `NAVIGATION_TIMEOUT_MS` budget — never the same `ASSERTION_TIMEOUT_MS`
    used for locator actions/assertions elsewhere."""
    captured = _monkeypatch_post(monkeypatch, "test('x', async ({ page }) => {})")
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(scenario)

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "const NAVIGATION_TIMEOUT_MS = 30000;" in content
    assert "await page.goto(url, { timeout: NAVIGATION_TIMEOUT_MS });" in content


async def test_generate_playwright_prompt_requires_dom_render_wait_after_every_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _monkeypatch_post(monkeypatch, "test('x', async ({ page }) => {})")
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(scenario)

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "not just the first one in the test" in content
    assert "waitForLoadState('domcontentloaded', { timeout: NAVIGATION_TIMEOUT_MS });" in content


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


async def test_generate_playwright_prompt_forbids_literal_fill_on_credential_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credential-handling fix: real generated output was observed calling
    `.fill('Password1$')` on the login page's own password field AND then
    also calling `fillCredentials(page)` right after — a redundant, wrong
    double-fill. The prompt must explicitly forbid a literal `.fill(...)` on
    the username field or the account's own current/existing password field."""
    captured = _monkeypatch_post(monkeypatch, "test('x', async ({ page }) => {})")
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(scenario)

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "Never call `.fill(...)` with a literal string on the username field" in content


async def test_generate_playwright_prompt_forbids_select_option_on_a_non_native_dropdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[FIXED]` regression: real generated output called `.selectOption(...)`
    on a `role="combobox"` element built from a non-native dropdown component
    (Ant Design's `<Select>`, in the observed case) — which always fails with
    "Element is not a <select> element", since `.selectOption(...)` only ever
    works on a genuine native HTML `<select>`. The prompt must steer a
    role="combobox" trigger toward click-open-then-click-option instead."""
    captured = _monkeypatch_post(monkeypatch, "test('x', async ({ page }) => {})")
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(scenario)

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "only ever works on a genuine native HTML `<select>`" in content
    assert "never scope the search to inside the trigger element" in content


async def test_generate_playwright_prompt_requires_visible_filter_for_ambiguous_option_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[FIXED]` regression, then `[FIXED]` again: live-inspected the real DOM
    behind a repeatedly failing "not visible" error against a real Ant Design
    dropdown. First found a `role="option"` hidden accessibility duplicate
    alongside the real, visible popup — the original fix taught the model to
    `.filter({ visible: true })`. Later, live-probed with real Playwright
    directly (not the MCP snapshot) and found the deeper issue: the captured
    `role="generic"` locator itself matches ZERO elements via real
    `getByRole()` — "generic" is name-from-content-prohibited in a real
    accessibility tree, so no amount of `.filter({ visible: true })` can fix
    it. The prompt must steer the model to `getByText(...)` for a
    generic-role element instead, and keep the still-valid
    `.filter({ visible: true })` guidance only for the genuinely-ambiguous
    `role="option"` hidden-duplicate case."""
    captured = _monkeypatch_post(monkeypatch, "test('x', async ({ page }) => {})")
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(scenario)

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "is not guaranteed to be unique" in content
    assert "getByText(name, { exact: true })" in content
    assert "getByRole('generic', { name })" in content
    assert "name-from-content-prohibited" in content


async def test_generate_playwright_prompt_scopes_popup_option_text_with_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[FIXED]` regression: even after switching a popup option to
    `getByText(...)` (see the generic-role rule above), the fix for one
    ambiguity (a hidden ARIA duplicate) didn't cover a second, different one
    — live-diagnosed a real failure and found the real Playwright error was
    a strict-mode violation: the option's text ALSO matched a status tag
    already visible elsewhere on the page (real data created by an earlier
    test run against a real, shared environment), and both matches were
    genuinely visible, so `.filter({ visible: true })` alone couldn't tell
    them apart. A portal-rendered popup is appended to the end of the DOM
    after everything already on the page, so its real option is reliably
    the LAST match, not the first — the prompt must tell the model to scope
    with `.last()` in addition to `.filter({ visible: true })`."""
    captured = _monkeypatch_post(monkeypatch, "test('x', async ({ page }) => {})")
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(scenario)

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "Pre-existing-data ambiguity rule" in content
    assert "resolved to N elements" in content
    assert ".filter({ visible: true }).last()" in content


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


async def test_generate_playwright_includes_ordered_live_action_sequence_in_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LiveHealActivity's fix: the prerequisite action (opening the
    dropdown) must reach the prompt alongside the final target locator, in
    order — not just the final locator on its own."""
    captured = _monkeypatch_post(
        monkeypatch, "test('add connection', async ({ page }) => {})"
    )
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(
        scenario,
        live_action_sequence=[
            {
                "tool_name": "browser_click",
                "strategy": "role",
                "value": 'get_by_role("combobox", name="Server type")',
                "fragile": False,
                "element_tag": "combobox",
            },
            {
                "tool_name": "browser_click",
                "strategy": "role",
                "value": 'get_by_role("option", name="GIT")',
                "fragile": False,
                "element_tag": "option",
            },
        ],
    )

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "Ordered Action Sequence" in content
    assert '1. browser_click on <combobox> -> get_by_role("combobox", name="Server type")' \
        in content
    assert '2. browser_click on <option> -> get_by_role("option", name="GIT")' in content


async def test_generate_playwright_prompt_requires_ensure_visible_for_sequence_steps_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[FIXED]` regression: real generated output resolved the sequence's
    final target with a raw `page.getByRole(...)` and called `.hover()`/
    `.click()` directly on it, skipping `ensureVisible` — the ONE interaction
    in the whole file that wasn't wrapped, which is exactly why it kept
    failing "not visible" even after the wait/poll fix. The prompt must say
    explicitly that a sequence step is not exempt from that rule."""
    captured = _monkeypatch_post(
        monkeypatch, "test('add connection', async ({ page }) => {})"
    )
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(
        scenario,
        live_action_sequence=[
            {
                "tool_name": "browser_click",
                "strategy": "role",
                "value": 'get_by_role("combobox", name="Server type")',
                "fragile": False,
                "element_tag": "combobox",
            },
        ],
    )

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "must still be" in content
    assert "resolved via `page.getByRole(...)`/etc. and routed through `ensureVisible`" in content
    assert "never a raw, unwrapped" in content


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


async def test_generate_playwright_prompt_requires_exact_true_on_getbylabel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Locator-accuracy fix — Playwright's `getByLabel`/`getByText` default to
    substring matching, so a shorter known label that's a substring of a
    longer one (e.g. "New password" vs. "Confirm new password") resolves to
    both and strict-mode-violates unless the prompt tells the LLM to pass
    `{ exact: true }`."""
    captured = _monkeypatch_post(
        monkeypatch, "test('guest checkout', async ({ page }) => {})"
    )
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(scenario)

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "{ exact: true }" in content
    assert "strict-mode violation" in content


async def test_generate_playwright_prompt_forbids_exact_match_on_icon_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real bug this locks in: a button showing a "+" icon and the text "Add
    connection" has a computed accessible name of "plus Add connection" (the
    icon's own alt text merges into the button's ONE accessible name) — a
    real generated test used `getByRole('button', { name: 'Add connection',
    exact: true })`, which matches ZERO elements against that button.
    `isVisible()` on a zero-match locator returns `false` rather than
    raising, so this surfaced as a confusing "element is not visible even
    after scrolling" failure instead of an obvious "not found" — see
    HealTestActivity's live-inspection investigation this fix came from."""
    captured = _monkeypatch_post(monkeypatch, "test('x', async ({ page }) => {})")
    scenario = _fake_scenario()

    await HostedAIProvider().generate_playwright(scenario)

    content = "".join(m["content"] for m in captured["json"]["messages"])
    assert "plus Add connection" in content
    assert "getByRole('button', { name: /Add connection/ })" in content
    # The rule must be phrased broadly (any icon button), not just the one
    # concrete example used to illustrate it.
    assert "icon" in content and "button" in content


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


def _test_case_prompt_body(**overrides) -> str:
    body = {
        "is_relevant": True,
        "functionality_summary": "Add a GIT MCP connection",
        "actions": [],
        "expected_result": "",
        "provided_test_data": {},
        "requested_scenario_counts": {},
        "rejection_reason": None,
    }
    body.update(overrides)
    return json.dumps(body)


async def test_analyze_test_case_prompt_extracts_an_explicit_per_type_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _monkeypatch_post(
        monkeypatch,
        _test_case_prompt_body(
            requested_scenario_counts={"happy": 1, "negative": 1, "edge": 1}
        ),
    )

    candidate = await HostedAIProvider().analyze_test_case_prompt(
        "Create three test cases: happy path, negative path, and edge case."
    )

    assert candidate.requested_scenario_counts == {"happy": 1, "negative": 1, "edge": 1}


async def test_analyze_test_case_prompt_defaults_to_empty_when_no_count_stated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _monkeypatch_post(monkeypatch, _test_case_prompt_body())

    candidate = await HostedAIProvider().analyze_test_case_prompt(
        "Test that adding a GIT MCP connection works."
    )

    assert candidate.requested_scenario_counts == {}


async def test_analyze_test_case_prompt_drops_an_unknown_category_or_bad_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hallucination guard, same spirit as `provided_test_data` below — a
    malformed value here would force `generate_scenarios` into an unintended
    exact count, so an unknown category, a non-int, or a non-positive count
    is dropped rather than trusted."""
    _monkeypatch_post(
        monkeypatch,
        _test_case_prompt_body(
            requested_scenario_counts={
                "happy": 1,
                "smoke": 2,
                "negative": "a lot",
                "edge": 0,
            }
        ),
    )

    candidate = await HostedAIProvider().analyze_test_case_prompt("irrelevant")

    assert candidate.requested_scenario_counts == {"happy": 1}


async def test_analyze_test_case_prompt_falls_back_to_regex_when_the_llm_omits_the_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Observed live: the same unambiguous prompt sometimes comes back from
    the model with an empty `requested_scenario_counts` — the extraction is
    LLM-based and not 100% reliable turn to turn. The deterministic regex
    backstop must still produce the right count from the prompt text itself."""
    _monkeypatch_post(monkeypatch, _test_case_prompt_body(requested_scenario_counts={}))

    candidate = await HostedAIProvider().analyze_test_case_prompt(
        "Create three test cases to cover the happy path, the negative path, and an edge case."
    )

    assert candidate.requested_scenario_counts == {"happy": 1, "negative": 1, "edge": 1}


async def test_analyze_test_case_prompt_regex_fallback_handles_per_category_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _monkeypatch_post(monkeypatch, _test_case_prompt_body(requested_scenario_counts={}))

    candidate = await HostedAIProvider().analyze_test_case_prompt(
        "Give me 3 negative scenarios and one happy path test case."
    )

    assert candidate.requested_scenario_counts == {"negative": 3, "happy": 1}


async def test_analyze_test_case_prompt_llm_count_wins_over_the_regex_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback only fills gaps — when the LLM did return a value for a
    category, that's what's used, never overridden."""
    _monkeypatch_post(
        monkeypatch, _test_case_prompt_body(requested_scenario_counts={"happy": 2})
    )

    candidate = await HostedAIProvider().analyze_test_case_prompt(
        "Create three test cases to cover the happy path, the negative path, and an edge case."
    )

    assert candidate.requested_scenario_counts == {"happy": 2, "negative": 1, "edge": 1}


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


async def test_decide_live_exploration_action_parses_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_response_body = json.dumps(
        {
            "tool_name": "browser_click",
            "tool_args": {"element": "Create connection button", "ref": "e12"},
            "rationale": "The MCP Connections page has a visible 'Create' button.",
            "goal_satisfied": False,
        }
    )
    captured = _monkeypatch_post(monkeypatch, fake_response_body)

    result = await HostedAIProvider().decide_live_exploration_action(
        requirement="Create a new MCP connection for a tenant.",
        history=[{"tool_name": "browser_navigate", "tool_args": {"url": "https://app/tenants"}}],
        snapshot={"role": "main", "children": [{"role": "button", "name": "Create", "ref": "e12"}]},
    )

    assert result.tool_name == "browser_click"
    assert result.tool_args == {"element": "Create connection button", "ref": "e12"}
    assert result.goal_satisfied is False
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert "Create a new MCP connection" in captured["json"]["messages"][1]["content"]


async def test_decide_live_exploration_action_uses_heal_prompt_when_healing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_response_body = json.dumps(
        {
            "tool_name": "browser_snapshot",
            "tool_args": {},
            "rationale": "button, accessible name 'Create connection'",
            "goal_satisfied": True,
        }
    )
    captured = _monkeypatch_post(monkeypatch, fake_response_body)

    result = await HostedAIProvider().decide_live_exploration_action(
        requirement="Step 'click Create' failed: locator not found",
        history=[],
        snapshot={"role": "main"},
        is_heal=True,
    )

    assert result.goal_satisfied is True
    assert "healing agent" in captured["json"]["messages"][0]["content"]


async def test_heal_prompt_requires_a_hover_before_declaring_goal_satisfied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[FIXED]` regression: the heal agent used to be allowed to declare
    `goal_satisfied` after merely "observing" an element in a snapshot and
    reasoning about it in `rationale` — never actually acting on it. Observed
    live: `live_heal_activity` reads `locator_candidate` off the LAST
    recorded step, which is only populated by an actual browser_hover/click/
    type/select_option — a heal that only ever reasoned in prose left that
    None, silently failing to heal despite correctly identifying the fix."""
    captured = _monkeypatch_post(
        monkeypatch,
        json.dumps(
            {
                "tool_name": "browser_hover",
                "tool_args": {"element": "settings link", "ref": "e1"},
                "rationale": "hover the candidate element",
                "goal_satisfied": False,
            }
        ),
    )

    await HostedAIProvider().decide_live_exploration_action(
        requirement="Step 'click Create' failed: locator not found",
        history=[],
        snapshot={"role": "main"},
        is_heal=True,
    )

    system_prompt = captured["json"]["messages"][0]["content"]
    assert "your NEXT turn must be" in system_prompt
    assert "browser_hover" in system_prompt
    assert (
        'Never set "goal_satisfied" in the same turn as that confirming action itself'
        in system_prompt
    )


async def test_heal_prompt_allows_a_click_to_confirm_a_dropdown_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[FIXED]` regression: the heal agent was barred from ever clicking,
    only hovering, to avoid triggering a real side-effect mid-investigation.
    That's right for a submit/save/delete button, but for a dropdown/listbox/
    menu OPTION it left the heal unable to confirm anything beyond "this
    element exists and is hoverable" — never whether clicking it actually
    selects the value, and never able to catch a wrong-but-similarly-named
    element elsewhere on the page (e.g. a status tag reusing the option's
    text) that only a real click would expose. Observed live: a healed test's
    regenerated code mirrored the heal's own hover-only evidence into a
    `.hover()` call on a dropdown option — which can never select anything —
    while the real, unrelated match a plain text locator also picked up went
    undetected because the heal never clicked to find out. Selecting an
    option is not destructive (it only changes a field's value; this heal
    never submits the form), so the prompt must explicitly allow a click for
    this one case while still barring it for anything that saves/submits/
    deletes/navigates."""
    captured = _monkeypatch_post(
        monkeypatch,
        json.dumps(
            {
                "tool_name": "browser_click",
                "tool_args": {"element": "GIT option", "ref": "e7"},
                "rationale": "click the GIT option to confirm it selects",
                "goal_satisfied": False,
            }
        ),
    )

    await HostedAIProvider().decide_live_exploration_action(
        requirement="Step 'select GIT from the Server type dropdown' failed: locator not found",
        history=[],
        snapshot={"role": "main"},
        is_heal=True,
    )

    system_prompt = captured["json"]["messages"][0]["content"]
    assert "your NEXT turn must be \"browser_click\"" in system_prompt
    assert "not destructive" in system_prompt
    assert "never submits" in system_prompt or "never goes on to submit" in system_prompt
