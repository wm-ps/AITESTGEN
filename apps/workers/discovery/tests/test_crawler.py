"""DiscoveryActivity's crawl loop against a real local target (Story 2.2, AC 1-2, 4-6).

Runs a real headless Chromium against fixtures/target_app.py (a real HTTP
server, not an ASGI transport) through the actual crawler + session +
object-store modules — the closest thing to "verify end-to-end" this
environment supports without a real deployed target application.
"""

import json
import uuid

import pytest
from discovery_worker.crawler import CapturedAction, CapturedPage, run_discovery_crawl
from discovery_worker.session import establish_session
from fixtures.target_app import configure
from playwright.async_api import async_playwright


class FakeObjectStore:
    def __init__(self) -> None:
        self.stored: dict[str, bytes] = {}

    def put(self, data: bytes, discovery_run_id: uuid.UUID) -> str:
        key = f"fake/{len(self.stored)}"
        self.stored[key] = data
        return key

    def get(self, key: str) -> bytes:
        return self.stored[key]


async def _crawl(target_app_url: str):
    credential = json.dumps({"username": "qa", "password": "qa-pass"}).encode()
    object_store = FakeObjectStore()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await establish_session(
            browser,
            auth_method="standard_login",
            credential=credential,
            base_url=target_app_url,
        )
        result = await run_discovery_crawl(context, target_app_url, object_store, uuid.uuid4())
        await context.close()
        await browser.close()
    return result, object_store


@pytest.mark.asyncio
async def test_crawl_captures_every_typed_capture(target_app_url: str) -> None:
    result, object_store = await _crawl(target_app_url)

    assert result.pages
    assert result.forms
    assert result.api_calls

    assert all(page.object_storage_key in object_store.stored for page in result.pages)


@pytest.mark.asyncio
async def test_crawl_detects_session_expiry_mid_crawl(target_app_url: str) -> None:
    # 3 authenticated hits succeed (the post-login redirect, the crawl's own
    # dashboard visit, and the shared header's same-page form resubmit); the
    # dashboard's "Add item" form submission is the 4th and drops the
    # session — a genuine mid-crawl expiry, not an immediate post-login
    # failure.
    configure(expire_after=3)
    result, _ = await _crawl(target_app_url)

    assert result.session_expired is True
    assert result.pages, "expected some pages captured before the session dropped"


@pytest.mark.asyncio
async def test_crawl_does_not_false_positive_on_a_normal_password_field(
    target_app_url: str,
) -> None:
    """A directly-linked page with a password field for a legitimate reason
    (e.g. a change-password section on /settings) must never be mistaken for
    session expiry — only an *unrequested redirect* to a page with a
    password field counts as expiry, not password-field presence alone."""
    result, _ = await _crawl(target_app_url)

    assert result.session_expired is False
    visited_urls = {page.url for page in result.pages}
    assert any(url.endswith("/settings") for url in visited_urls), (
        "expected the crawl to actually reach /settings, or this test proves nothing"
    )


@pytest.mark.asyncio
async def test_crawl_does_not_loop_on_a_shared_hash_action_form(target_app_url: str) -> None:
    """Regression: every page in the test target carries a shared header
    form with action="#" (a stand-in for a real site's search/menu icon).
    Submitting it just appends a "#" fragment to the current page — without
    URL normalization, that reads as a "new" page forever and the crawl
    never terminates. Also proves AC 4 (page-fingerprint dedup): each
    distinct logical page is captured exactly once."""
    result, _ = await _crawl(target_app_url)

    assert result.session_expired is False

    page_urls = [page.url for page in result.pages]
    normalized = [url.split("#")[0] for url in page_urls]
    assert len(normalized) == len(set(normalized)), (
        f"the same page was visited more than once (fragment-duplicate loop): {page_urls}"
    )


@pytest.mark.asyncio
async def test_crawl_samples_one_representative_action_per_repeated_pattern(
    target_app_url: str,
) -> None:
    """AC 6: the /items page renders one "Edit" button per row (2 items) —
    the crawler must capture exactly one representative Action for that
    repeated pattern, not one per DOM instance."""
    result, _ = await _crawl(target_app_url)

    edit_actions = [a for a in result.actions if a.description == "Edit"]
    assert len(edit_actions) == 1
    assert edit_actions[0].representative is True


@pytest.mark.asyncio
async def test_crawl_follows_button_triggered_navigation_to_a_new_page(
    target_app_url: str,
) -> None:
    """Regression: the /items page's "View Cart" button navigates via
    `window.location`, not a plain `<a href>` — before the fix, the click was
    captured as an Action/Transition but its destination was never queued
    for further crawling, so any flow reachable only via a button dead-ended."""
    result, _ = await _crawl(target_app_url)

    visited_urls = {page.url for page in result.pages}
    assert any(url.endswith("/cart") for url in visited_urls), (
        f"expected /cart to be crawled even though nothing links to it via <a href>: {visited_urls}"
    )
    assert any(a.description == "View Cart" for a in result.actions)


@pytest.mark.asyncio
async def test_crawl_prefers_page_content_buttons_over_shared_nav_chrome(
    target_app_url: str,
) -> None:
    """Regression: the dashboard's <nav> button ("Menu") sits first in raw
    DOM order — the old first-DOM-match sampling picked it as the page's
    sole representative action, so a page's own content buttons never got
    captured at all. Body-content buttons must win the (bounded) budget
    before nav/header/footer chrome is ever tried."""
    result, _ = await _crawl(target_app_url)

    dashboard_actions = {a.description for a in result.actions if a.page_url == target_app_url}
    assert {"Wishlist", "Recently viewed"} <= dashboard_actions
    assert "Menu" not in dashboard_actions


@pytest.mark.asyncio
async def test_crawl_records_a_transition_for_plain_link_navigation(target_app_url: str) -> None:
    """Regression: plain `<a href>` BFS navigation never emitted a
    PageTransition — only click/form-triggered navigation did, leaving the
    navigation graph almost empty across a normal crawl."""
    result, _ = await _crawl(target_app_url)

    assert any(
        t.from_url == target_app_url and t.to_url.endswith("/about") for t in result.transitions
    )


@pytest.mark.asyncio
async def test_crawl_captures_a_form_submit_button_as_an_action(target_app_url: str) -> None:
    """Regression: a submit button inside a `<form>` (e.g. "Add item") never
    became an Action row at all — only the form's fields did — so a
    form-based business action like "Add to Cart" had no Component/locator
    for later Playwright generation to use."""
    result, _ = await _crawl(target_app_url)

    assert any(a.description == "Add item" for a in result.actions)


@pytest.mark.asyncio
async def test_crawl_fills_quantity_like_fields_with_a_number(target_app_url: str) -> None:
    """Regression: a field named "quantity" but typed `type="text"` (the
    dashboard's "Add item" form) used to get the generic "Test value" string
    like any other text field — a server that parses it as a number 500s on
    that. Name-based detection should win over the declared `type`."""
    result, _ = await _crawl(target_app_url)

    quantity_fields = [f for form in result.forms for f in form.fields if f.name == "quantity"]
    assert quantity_fields, "expected the dashboard's Add item form to be captured"
    assert all(f.default_value == "1" for f in quantity_fields)


@pytest.mark.asyncio
async def test_crawl_captures_a_shared_form_shape_once_per_crawl(target_app_url: str) -> None:
    """Regression: the shared header form (present on every authenticated
    page: /, /items, /about, /cart) used to be filled and submitted again on
    every single page it appeared on — same action/method/fields each time,
    pure repeated work for zero new signal. Now captured once per crawl, the
    same representative-sampling idea already applied to buttons (AC 6)."""
    result, _ = await _crawl(target_app_url)

    header_forms = [f for f in result.forms if f.action_url == "#"]
    assert len(header_forms) == 1, (
        f"expected the shared header form captured exactly once, got {len(header_forms)}"
    )


@pytest.mark.asyncio
async def test_crawl_captures_a_non_navigating_submit_as_an_action(target_app_url: str) -> None:
    """Regression: a submit whose click only updates in-page state (no
    navigation, no XHR — e.g. a real "Add to Cart" button) used to be
    invisible: the old code only recorded the submit as an Action when the
    URL actually changed. The Action is recorded regardless now; only the
    Transition still requires an observed navigation."""
    result, _ = await _crawl(target_app_url)

    assert any(a.description == "Subscribe" for a in result.actions)
    assert not any(t.triggered_by_description == "Subscribe" for t in result.transitions)


@pytest.mark.asyncio
async def test_crawl_discards_an_error_status_destination(target_app_url: str) -> None:
    """Regression: a 4xx/5xx destination (a dead link, or a GET against a
    POST-only route) used to be persisted as a normal Page, handing the
    Journey/Scenario model a server-error response to build an assertion
    against and land on."""
    result, _ = await _crawl(target_app_url)

    assert not any(page.url.endswith("/broken") for page in result.pages)
    assert not any(t.to_url.endswith("/broken") for t in result.transitions)


def test_captured_dataclasses_carry_selector_info() -> None:
    """Sanity check on the capture shapes themselves — CapturedAction and
    CapturedPage carry the fields DiscoveryActivity/Story 2.5 depend on."""
    page = CapturedPage(url="https://example.com", title="Home", object_storage_key="k")
    assert page.object_storage_key == "k"
    action = CapturedAction(
        page_url="https://example.com", description="Edit", captured_selector="#edit"
    )
    assert action.representative is True
    assert action.captured_selector == "#edit"
