"""Story 2.12 Task 6: end-to-end verification against a real crawl — the
Safety Engine wired in as `run_discovery_crawl`'s `safety` specialist. Real
Chromium against `fixtures/target_app.py`, same convention as
test_planner_integration.py.
"""

import json
import uuid

import pytest
from discovery_worker.crawler import CapturedAction, run_discovery_crawl
from discovery_worker.safety_engine import SafetyState
from discovery_worker.session import establish_session
from playwright.async_api import async_playwright


class FakeObjectStore:
    def put(self, data: bytes, discovery_run_id: uuid.UUID) -> str:
        return "fake/0"


async def _crawl_safety_test_page(target_app_url: str, posture: str):
    credential = json.dumps({"username": "qa", "password": "qa-pass"}).encode()
    captured: list = []
    diagnostics: list[tuple[str, dict]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await establish_session(
            browser, auth_method="standard_login", credential=credential, base_url=target_app_url
        )
        await run_discovery_crawl(
            context,
            f"{target_app_url}safety-test",
            FakeObjectStore(),
            uuid.uuid4(),
            auth_method="standard_login",
            credential=credential,
            on_capture=captured.append,
            on_diagnostic=lambda kind, payload: diagnostics.append((kind, payload)),
            safety=SafetyState(posture=posture),
        )
        await context.close()
        await browser.close()
    actions = {a.description for a in captured if isinstance(a, CapturedAction)}
    return actions, diagnostics


@pytest.mark.asyncio
async def test_delete_is_never_clicked_under_either_posture(target_app_url: str) -> None:
    for posture in ("non_production", "production"):
        actions, _ = await _crawl_safety_test_page(target_app_url, posture)
        assert "Delete" not in actions, posture


@pytest.mark.asyncio
async def test_ambiguous_action_executes_under_non_production_and_defers_under_production(
    target_app_url: str,
) -> None:
    non_prod_actions, _ = await _crawl_safety_test_page(target_app_url, "non_production")
    assert "Submit" in non_prod_actions

    prod_actions, _ = await _crawl_safety_test_page(target_app_url, "production")
    assert "Submit" not in prod_actions


@pytest.mark.asyncio
async def test_unmatched_verb_follows_the_same_posture_rule_as_ambiguous(
    target_app_url: str,
) -> None:
    """AC 1: a label in none of the three lists is never Safe by default —
    it's resolved exactly like an explicit Ambiguous match."""
    non_prod_actions, _ = await _crawl_safety_test_page(target_app_url, "non_production")
    assert "Frobnicate" in non_prod_actions

    prod_actions, _ = await _crawl_safety_test_page(target_app_url, "production")
    assert "Frobnicate" not in prod_actions


@pytest.mark.asyncio
async def test_safety_verdict_diagnostic_is_recorded_for_every_verdict(
    target_app_url: str,
) -> None:
    """AC 6: label, matched list (or none), posture, AI-consulted, and the
    final verdict are all recorded — one diagnostic per verdict reached."""
    _, diagnostics = await _crawl_safety_test_page(target_app_url, "production")
    verdicts = {
        payload["label"]: payload for kind, payload in diagnostics if kind == "safety_verdict"
    }
    assert verdicts["Delete"]["verdict"] == "DESTRUCTIVE"
    assert verdicts["Delete"]["matched_list"] == "destructive"
    assert verdicts["Submit"]["verdict"] == "DEFER"
    assert verdicts["Submit"]["matched_list"] == "ambiguous"
    assert verdicts["Frobnicate"]["verdict"] == "DEFER"
    assert verdicts["Frobnicate"]["matched_list"] is None
    assert all(v["posture"] == "production" for v in verdicts.values())
    assert all(v["ai_consulted"] is False for v in verdicts.values())


@pytest.mark.asyncio
async def test_defer_carries_a_normalized_key_for_the_blocked_frontier(
    target_app_url: str,
) -> None:
    """Story 2.15 Task 3: a safety-driven DEFER's `execution_decision`
    diagnostic carries `normalized_key` — what `activities.py`'s
    `_record_diagnostic` uses to attach/create the aggregated `BlockedTask`.
    A SKIP (loop-guard or destructive) carries none — there's no block to
    aggregate for an action that never gets a second chance."""
    from discovery_worker.state_identity import route_template
    from domain import aggregation_key

    _, diagnostics = await _crawl_safety_test_page(target_app_url, "production")
    decisions = {
        payload["label"]: payload
        for kind, payload in diagnostics
        if kind == "execution_decision"
    }
    assert decisions["Submit"]["action"] == "DEFER"
    expected_route = route_template(f"{target_app_url}safety-test")
    assert decisions["Submit"]["normalized_key"] == aggregation_key(
        "Submit", "action_approval", expected_route
    )
    assert "normalized_key" not in decisions["Delete"]
