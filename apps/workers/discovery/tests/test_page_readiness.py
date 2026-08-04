"""Story 2.9: page readiness (network quiet / DOM stable / content present)
and bounded infinite-scroll/pagination sampling. Real Chromium against real
fixture routes, same convention as test_crawler.py/test_widget_coverage.py.
"""

import json
import time
import uuid

import pytest
from discovery_worker.crawler import (
    CapturedAction,
    NetworkActivityTracker,
    run_discovery_crawl,
    wait_for_page_ready,
)
from discovery_worker.session import establish_session
from playwright.async_api import async_playwright


class FakeObjectStore:
    def put(self, data: bytes, discovery_run_id: uuid.UUID) -> str:
        return "fake/0"


async def _authenticated_page(target_app_url: str):
    """Yields (playwright, browser, context, page) already signed in — for
    tests that drive `wait_for_page_ready` directly rather than through a
    full crawl."""
    credential = json.dumps({"username": "qa", "password": "qa-pass"}).encode()
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch()
    context = await establish_session(
        browser, auth_method="standard_login", credential=credential, base_url=target_app_url
    )
    page = await context.new_page()
    return playwright, browser, context, page


async def _crawl_route(target_app_url: str, route: str):
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
            f"{target_app_url}{route}",
            FakeObjectStore(),
            uuid.uuid4(),
            auth_method="standard_login",
            credential=credential,
            on_capture=captured.append,
            on_diagnostic=lambda kind, payload: diagnostics.append((kind, payload)),
        )
        await context.close()
        await browser.close()
    return captured, diagnostics


@pytest.mark.asyncio
async def test_load_more_sampling_stops_on_confirmed_pattern_not_at_cap_or_first_click(
    target_app_url: str,
) -> None:
    _, diagnostics = await _crawl_route(target_app_url, "load-more")
    sampled = [
        payload
        for kind, payload in diagnostics
        if kind == "page_readiness" and payload.get("type") == "scroll_sampled"
    ]
    assert sampled, diagnostics
    # Growing 3-per-click from 1 to a cap of 12 takes 4 growing clicks, then
    # 3 more flat ones to confirm sampled -> ~7, well short of the 20-item
    # hard budget and more than 1.
    assert sampled[0]["reason"] == "same_run", sampled
    assert 1 < sampled[0]["iterations"] < 20, sampled


@pytest.mark.asyncio
async def test_readiness_settles_quickly_despite_a_polling_endpoint(target_app_url: str) -> None:
    playwright, browser, context, page = await _authenticated_page(target_app_url)
    try:
        await page.goto(f"{target_app_url}polling")
        tracker = NetworkActivityTracker()
        tracker.attach(page)
        start = time.monotonic()
        result = await wait_for_page_ready(page, timeout_seconds=10.0, network_tracker=tracker)
        elapsed = time.monotonic() - start
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()

    assert result.settled, result.unsettled_signals
    # The poll fires every 300ms; readiness should settle in ~1-2s once the
    # cadence is recognized, nowhere near the full 10s ceiling.
    assert elapsed < 5.0, elapsed


@pytest.mark.asyncio
async def test_continuously_mutating_page_times_out_settled_false(target_app_url: str) -> None:
    playwright, browser, context, page = await _authenticated_page(target_app_url)
    try:
        await page.goto(f"{target_app_url}never-settles")
        start = time.monotonic()
        result = await wait_for_page_ready(page, timeout_seconds=1.5)
        elapsed = time.monotonic() - start
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()

    assert result.settled is False
    assert "dom_stable" in result.unsettled_signals, result.unsettled_signals
    # Bounded by the ceiling — proves the run is never blocked by readiness.
    assert elapsed < 3.0, elapsed


@pytest.mark.asyncio
async def test_unsettled_page_logs_a_disc_004_discovery_error(target_app_url: str) -> None:
    """Story 2.18 AC 2/3: a Page Load Timeout is logged as a DISC-004
    `discovery_error` diagnostic — informational, capture still proceeds
    best-effort (Story 2.9's own never-block/fail/retry/abort guarantee is
    unchanged)."""
    playwright, browser, context, page = await _authenticated_page(target_app_url)
    diagnostics: list[tuple[str, dict]] = []
    try:
        await page.goto(f"{target_app_url}never-settles")
        result = await wait_for_page_ready(
            page,
            timeout_seconds=1.5,
            on_diagnostic=lambda kind, payload: diagnostics.append((kind, payload)),
        )
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()

    assert result.settled is False
    disc_004 = [
        payload
        for kind, payload in diagnostics
        if kind == "discovery_error" and payload["error_code"] == "DISC-004"
    ]
    assert disc_004, diagnostics
    assert "never-settles" in disc_004[0]["page_url"]


@pytest.mark.asyncio
async def test_near_zero_timeout_returns_false_not_raises(target_app_url: str) -> None:
    """The concrete proof of AC 3: a near-zero ceiling must return
    `settled=False`, never raise."""
    playwright, browser, context, page = await _authenticated_page(target_app_url)
    try:
        await page.goto(f"{target_app_url}")
        result = await wait_for_page_ready(page, timeout_seconds=0.001)
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()

    assert result.settled is False


@pytest.mark.asyncio
async def test_load_more_control_excluded_from_generic_button_loop(target_app_url: str) -> None:
    """AC: the matched Load-More control isn't also clicked by the generic
    single-click action loop as an ordinary standalone button."""
    captured, _ = await _crawl_route(target_app_url, "load-more")
    actions = [item for item in captured if isinstance(item, CapturedAction)]
    assert not any(a.description == "Load More" for a in actions), actions
