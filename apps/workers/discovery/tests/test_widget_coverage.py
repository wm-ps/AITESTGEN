"""Story 2.14: widget & container coverage — frames, shadow DOM, tabs,
dialogs, popups, file uploads. Same real-Chromium-against-a-real-HTTP-server
convention as test_crawler.py; each test scopes the crawl to one dead-end
fixture route (`base_url=f"{target_app_url}<route>"`) rather than the whole
site, so it stays fast and its assertions aren't diluted by the full
dashboard crawl.
"""

import json
import uuid

import pytest
from discovery_worker.crawler import (
    CapturedAction,
    CapturedForm,
    run_discovery_crawl,
)
from discovery_worker.session import establish_session
from playwright.async_api import async_playwright


class FakeObjectStore:
    def put(self, data: bytes, discovery_run_id: uuid.UUID) -> str:
        return "fake/0"


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
async def test_same_origin_iframe_form_attributed_to_containing_page(
    target_app_url: str,
) -> None:
    captured, _ = await _crawl_route(target_app_url, "frames")
    forms = [item for item in captured if isinstance(item, CapturedForm)]
    frame_page_url = f"{target_app_url}frames"
    assert any(f.page_url == frame_page_url for f in forms), [
        (f.page_url, f.action_url) for f in forms
    ]


@pytest.mark.asyncio
async def test_cross_origin_iframe_logged_as_unreachable_container(
    target_app_url: str,
) -> None:
    _, diagnostics = await _crawl_route(target_app_url, "frames")
    unreachable = [
        payload
        for kind, payload in diagnostics
        if kind == "widget_coverage" and payload.get("container") == "cross_origin_frame"
    ]
    assert unreachable, diagnostics


@pytest.mark.asyncio
async def test_open_shadow_root_button_discovered(target_app_url: str) -> None:
    captured, _ = await _crawl_route(target_app_url, "shadow-dom")
    actions = [item for item in captured if isinstance(item, CapturedAction)]
    assert any(a.description == "Shadow button" for a in actions), actions


@pytest.mark.asyncio
async def test_closed_shadow_root_logged_as_unreachable_container(target_app_url: str) -> None:
    _, diagnostics = await _crawl_route(target_app_url, "shadow-dom")
    closed = [
        payload
        for kind, payload in diagnostics
        if kind == "widget_coverage" and payload.get("container") == "closed_shadow_root"
    ]
    assert closed, diagnostics


@pytest.mark.asyncio
async def test_each_tab_is_explored(target_app_url: str) -> None:
    _, diagnostics = await _crawl_route(target_app_url, "tabs")
    explored_labels = {
        payload["label"]
        for kind, payload in diagnostics
        if kind == "widget_coverage" and payload.get("type") == "tab_explored"
    }
    assert explored_labels == {"First", "Second"}, diagnostics


@pytest.mark.asyncio
async def test_dialog_closed_via_close_button(target_app_url: str) -> None:
    captured, diagnostics = await _crawl_route(target_app_url, "dialog")
    actions = [item for item in captured if isinstance(item, CapturedAction)]
    assert any(a.description == "Open dialog" for a in actions), actions
    closes = [
        payload
        for kind, payload in diagnostics
        if kind == "widget_coverage" and payload.get("type") == "dialog_closed"
    ]
    assert any(c["method"] == "close_button" and c["closed"] for c in closes), closes


@pytest.mark.asyncio
async def test_unclosable_dialog_falls_back_to_forced_navigation(target_app_url: str) -> None:
    """The "stuck" dialog has no Close/Cancel/X control and Escape does
    nothing — proves the crawl doesn't strand inside it (Dev Notes: the
    highest-risk failure mode in this story) but instead recovers via the
    mandatory forced-navigation rung."""
    _, diagnostics = await _crawl_route(target_app_url, "dialog")
    closes = [
        payload
        for kind, payload in diagnostics
        if kind == "widget_coverage" and payload.get("type") == "dialog_closed"
    ]
    assert any(c["method"] == "forced_navigation" for c in closes), closes


@pytest.mark.asyncio
async def test_same_origin_popup_followed_cross_origin_popup_flagged(
    target_app_url: str,
) -> None:
    _, diagnostics = await _crawl_route(target_app_url, "popups")
    followed = [
        payload
        for kind, payload in diagnostics
        if kind == "widget_coverage" and payload.get("type") == "popup_followed"
    ]
    flagged = [
        payload
        for kind, payload in diagnostics
        if kind == "widget_coverage" and payload.get("container") == "cross_origin_popup"
    ]
    assert followed, diagnostics
    assert flagged, diagnostics


@pytest.mark.asyncio
async def test_file_input_receives_placeholder_and_is_logged(target_app_url: str) -> None:
    captured, diagnostics = await _crawl_route(target_app_url, "upload")
    forms = [item for item in captured if isinstance(item, CapturedForm)]
    file_fields = [f for form in forms for f in form.fields if f.input_type == "file"]
    assert file_fields, forms
    assert file_fields[0].default_value in ("placeholder.png", "placeholder.pdf")

    resolutions = [
        payload
        for kind, payload in diagnostics
        if kind == "data_resolution" and payload.get("type") == "file"
    ]
    assert resolutions, diagnostics
