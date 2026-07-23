"""DiscoveryActivity's crawl loop against a real local target (Story 2.2, AC 1-2, 4-6).

Runs a real headless Chromium against fixtures/target_app.py (a real HTTP
server, not an ASGI transport) through the actual crawler + session +
object-store modules — the closest thing to "verify end-to-end" this
environment supports without a real deployed target application.
"""

import asyncio
import json
import time
import uuid

import pytest
from discovery_worker.crawler import (
    CapturedAction,
    CapturedForm,
    CapturedPage,
    CrawlResult,
    _CaptureSink,
    _is_self_referential_duplicate,
    _page_fingerprint,
    run_discovery_crawl,
)
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
        # Matches real production usage (discovery_worker/activities.py) —
        # lets the crawler replay this same login mid-crawl on a session
        # expiry, same as it would for a real Discovery Run.
        result = await run_discovery_crawl(
            context,
            target_app_url,
            object_store,
            uuid.uuid4(),
            auth_method="standard_login",
            credential=credential,
        )
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
async def test_establish_session_captures_the_login_page_and_form(
    target_app_url: str,
) -> None:
    """`[FIXED 2026-07-23]` The login step happens entirely inside
    `establish_session`, before `run_discovery_crawl` ever starts — so
    without this, no Page/Form ever existed for it and no "Sign in" journey
    could ever be inferred downstream. Also proves the real password is
    never persisted as a captured field's default value."""
    credential = json.dumps({"username": "qa", "password": "qa-pass"}).encode()
    object_store = FakeObjectStore()
    captured: list[object] = []
    run_id = uuid.uuid4()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await establish_session(
            browser,
            auth_method="standard_login",
            credential=credential,
            base_url=target_app_url,
            object_store=object_store,
            discovery_run_id=run_id,
            on_capture=captured.append,
        )
        await context.close()
        await browser.close()

    login_pages = [item for item in captured if isinstance(item, CapturedPage)]
    login_forms = [item for item in captured if isinstance(item, CapturedForm)]
    assert login_pages, "expected the login page itself to be captured"
    assert login_forms, "expected the login form itself to be captured"

    password_fields = [
        field for field in login_forms[0].fields if field.input_type == "password"
    ]
    assert password_fields
    assert password_fields[0].default_value != "qa-pass"


@pytest.mark.asyncio
async def test_heartbeat_fires_more_than_once_per_page(target_app_url: str) -> None:
    """Bug fix (2026-07-20): a page's own form-fill/button-click sequence can
    take close to the Activity's heartbeat_timeout on a slow real site — if
    heartbeat only fired once per page (at dequeue), that page alone could
    silently exceed the timeout and trigger a from-scratch retry loop
    (observed live against a real target). This proves heartbeat now also
    fires per form submission and per button click, not just once per page."""
    credential = json.dumps({"username": "qa", "password": "qa-pass"}).encode()
    object_store = FakeObjectStore()
    heartbeat_calls = 0

    def count_heartbeat() -> None:
        nonlocal heartbeat_calls
        heartbeat_calls += 1

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await establish_session(
            browser, auth_method="standard_login", credential=credential, base_url=target_app_url
        )
        result = await run_discovery_crawl(
            context, target_app_url, object_store, uuid.uuid4(), heartbeat=count_heartbeat
        )
        await context.close()
        await browser.close()

    # The target fixture's dashboard page alone has 2 forms + several
    # standalone buttons — if heartbeat only fired once per page, this count
    # would equal len(result.pages) exactly. It must be strictly greater.
    assert heartbeat_calls > len(result.pages)


@pytest.mark.asyncio
async def test_crawl_detects_session_expiry_mid_crawl(target_app_url: str) -> None:
    # 3 authenticated hits succeed (the post-login redirect, the crawl's own
    # dashboard visit, and the shared header's same-page form resubmit); the
    # dashboard's "Add item" form submission is the 4th and drops the
    # session — a genuine mid-crawl expiry, not an immediate post-login
    # failure. `expire_after` without `recoverable_expiry` is a *permanent*
    # ratchet (every request past the threshold keeps invalidating) — the
    # crawler's own mid-crawl re-login (`[ADDED 2026-07-22]`) will retry a
    # few times against this and still end up here, at the real terminal
    # `session_expired=True` path, once `_MAX_CONSECUTIVE_REAUTH_ATTEMPTS` is
    # exhausted (see `test_crawl_recovers_from_a_recoverable_session_expiry`
    # for the case where re-login actually resolves it).
    configure(expire_after=3)
    result, _ = await _crawl(target_app_url)

    assert result.session_expired is True
    assert result.pages, "expected some pages captured before the session dropped"


@pytest.mark.asyncio
async def test_crawl_recovers_from_a_recoverable_session_expiry(target_app_url: str) -> None:
    """Regression (2026-07-22): a Keycloak-backed real app can issue a very
    short-lived access token that expires well before an exhaustive crawl
    finishes — observed live: a real crawl hit zero actions, zero
    transitions, then landed straight back on the login screen a few
    requests into a normal run. Story 2.4 (AD-11) originally treated any
    mid-crawl expiry as terminal ("re-authenticate to continue"), which
    means such an app could never be fully discovered. The crawler now
    replays the same login in place and resumes traversal — this fixture's
    `recoverable_expiry=True` models the one-time blip (a fresh login stays
    valid for the rest of the crawl), proving the crawl actually continues
    past the expiry rather than just retrying until it gives up."""
    configure(expire_after=3, recoverable_expiry=True)
    result, _ = await _crawl(target_app_url)

    assert result.session_expired is False
    # Pages only reachable well after the expiry point in BFS order — proof
    # traversal genuinely continued, not just that the first few pages
    # (already captured before the expiry) were returned.
    visited_urls = {page.url for page in result.pages}
    assert any(url.endswith("/settings") for url in visited_urls)
    assert any(url.endswith("/order-history") for url in visited_urls)
    assert any(url.endswith("/widgets") for url in visited_urls)


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
    Submitting it just appends a bare, *empty* "#" fragment to the current
    page — without collapsing that specific case, it reads as a "new" page
    forever and the crawl never terminates. Also proves AC 4 (page-
    fingerprint dedup): each distinct logical page is captured exactly once.
    `[UPDATED 2026-07-22]` Normalizes via the crawler's own
    `_page_fingerprint`, not a naive `split("#")[0]` — a *non-empty*
    fragment (e.g. `#Reports`) is now a legitimately distinct page (see
    `test_crawl_discovers_hash_routed_pages_as_distinct_destinations`), so
    the old blanket fragment-stripping this test used for its own
    normalization would wrongly flag those as "duplicates" too."""
    result, _ = await _crawl(target_app_url)

    assert result.session_expired is False

    page_urls = [page.url for page in result.pages]
    normalized = [_page_fingerprint(url) for url in page_urls]
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
async def test_crawl_clicks_a_dead_href_anchor_dropdown_toggle(target_app_url: str) -> None:
    """Regression (2026-07-22): a real dropdown toggle is very often an `<a
    href="#">`, not a `<button>` (Bootstrap-style menus, e.g. an "Account"
    menu revealing Order History/Product Management on a real target). The
    old `_click_standalone_buttons` only ever queried `//button`, so this
    toggle was never clicked and its menu item — injected into the DOM only
    on click, not merely CSS-unhidden — was never discovered."""
    result, _ = await _crawl(target_app_url)

    visited_urls = {page.url for page in result.pages}
    assert any(url.endswith("/order-history") for url in visited_urls), (
        f"expected /order-history to be reached via the Account dropdown <a>: {visited_urls}"
    )
    assert any(a.description == "Account" for a in result.actions)


@pytest.mark.asyncio
async def test_crawl_never_follows_a_logout_link(target_app_url: str) -> None:
    """Regression (2026-07-22): removing the per-page click budget means
    every distinct button/link now genuinely gets tried — including a real
    app's "Log out" (observed live: clicking a user-avatar button revealed a
    profile dropdown with a real "Log out" action, which the crawler
    dutifully clicked, ending its own session mid-crawl). The Account
    dropdown here reveals both "Order History" and a real `<a
    href="/logout">Log out</a>` — the crawler must discover the former and
    categorically refuse the latter, or an exhaustive crawler can never
    finish exhaustively."""
    result, _ = await _crawl(target_app_url)

    assert result.session_expired is False, (
        "the crawler must never end its own session by following /logout"
    )
    assert not any(page.url.endswith("/logout") for page in result.pages)
    assert not any(t.to_url.endswith("/logout") for t in result.transitions)
    assert not any(a.description == "Log out" for a in result.actions)
    # Still discovers the other item genuinely behind the same dropdown.
    visited_urls = {page.url for page in result.pages}
    assert any(url.endswith("/order-history") for url in visited_urls)


@pytest.mark.asyncio
async def test_crawl_exercises_both_body_and_chrome_buttons(
    target_app_url: str,
) -> None:
    """Regression (three times over): the dashboard's <nav> button ("Menu")
    sits first in raw DOM order — the old first-DOM-match sampling picked it
    as the page's sole representative action, so a page's own content
    buttons never got captured at all. Fixed by giving body content its own
    budget, tried first. That fix then over-corrected: body and chrome
    buttons shared one combined budget, so a page with enough distinct body
    buttons to fill it could starve chrome entirely. `[FIXED 2026-07-22]`
    The numeric budgets themselves were then removed altogether — a real
    page can have more than 3 distinct nav destinations (a left-nav sidebar
    is the common case), and a fixed cap silently drops whichever ones don't
    fit, contradicting exhaustive traversal (Story 2.3/AD-10). Both body and
    chrome content must still all get exercised, just with no count limit."""
    result, _ = await _crawl(target_app_url)

    dashboard_actions = {a.description for a in result.actions if a.page_url == target_app_url}
    assert {"Wishlist", "Recently viewed"} <= dashboard_actions
    assert "Menu" in dashboard_actions


@pytest.mark.asyncio
async def test_crawl_keeps_trying_buttons_after_one_navigates_away(
    target_app_url: str,
) -> None:
    """Regression (2026-07-22): a persistent left-nav shown on every route
    (/about, /settings, /cart, /order-history — not the dashboard itself)
    has "Dashboard" (pointing back to an already-visited page) before
    "Widgets" in DOM order. The old `_click_standalone_buttons` stopped
    entirely the instant *any* click navigated away — so visiting any of
    those pages, clicking "Dashboard" navigated back to `/` and the function
    returned immediately, never trying "Widgets" at all. Real observed
    impact: a 13-item left-nav sidebar where only 1-2 items were ever
    reachable. Fixed by restoring the page and continuing instead of
    stopping."""
    result, _ = await _crawl(target_app_url)

    visited_urls = {page.url for page in result.pages}
    assert any(url.endswith("/widgets") for url in visited_urls), (
        f"expected /widgets to be reached after 'Dashboard' navigated away: {visited_urls}"
    )


@pytest.mark.asyncio
async def test_crawl_links_the_pre_captured_login_page_into_the_navigation_graph(
    target_app_url: str,
) -> None:
    """`[FIXED 2026-07-23]` The login page is captured by `establish_session`
    before this crawl ever starts, with no `PageTransition` connecting it to
    anything — `journey_clustering.py` groups pages purely by navigation
    edges, so an unconnected login page could never end up in the same
    cluster as the rest of the app and no "Sign in" journey could ever be
    inferred for it. `login_page_url` seeds the very first page's `from_url`
    with it instead of `None`, giving it exactly one edge in."""
    credential = json.dumps({"username": "qa", "password": "qa-pass"}).encode()
    object_store = FakeObjectStore()
    login_url = "https://fake-login.example/login"

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await establish_session(
            browser, auth_method="standard_login", credential=credential, base_url=target_app_url
        )
        result = await run_discovery_crawl(
            context,
            target_app_url,
            object_store,
            uuid.uuid4(),
            auth_method="standard_login",
            credential=credential,
            login_page_url=login_url,
        )
        await context.close()
        await browser.close()

    assert any(
        t.from_url == login_url and t.to_url == target_app_url for t in result.transitions
    )


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
async def test_crawl_discovers_hash_routed_pages_as_distinct_destinations(
    target_app_url: str,
) -> None:
    """End-to-end proof of the 2026-07-22 fix: the dashboard's "Reports" and
    "Analytics" links are hash-only (`#Reports`/`#Analytics`), swapped by
    client-side JS with no server round-trip — the exact shape of a
    hash-routed SPA page (Angular/React, including WaveMaker-generated
    apps). Before the fix, both collapsed to the same BFS fingerprint as the
    dashboard itself, so only whichever one the browser happened to be on
    was ever "captured," and links that only exist inside one hash view
    (Settings from Reports, Cart from Analytics) were never discovered."""
    result, _ = await _crawl(target_app_url)

    page_urls = {page.url for page in result.pages}
    assert any(url.endswith("#Reports") for url in page_urls), page_urls
    assert any(url.endswith("#Analytics") for url in page_urls), page_urls

    # Both hash views got their own link-scrape pass, not just the bare
    # dashboard's — proves this isn't a single merged "page".
    visited_paths = {url.split("#")[0].split("?")[0] for url in page_urls}
    assert any(p.endswith("/settings") for p in visited_paths)
    assert any(p.endswith("/cart") for p in visited_paths)


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


@pytest.mark.asyncio
async def test_capture_sink_add_does_not_block_the_event_loop() -> None:
    """2026-07-21 fix: `on_capture` (real shape: a synchronous Postgres
    commit, or a synchronous MinIO upload upstream of it) must run off the
    event loop. Before this fix, a slow `on_capture` call froze the whole
    worker process — not just the current crawl — since Temporal's
    heartbeat/poll loop for every concurrent workflow shares this same
    event loop. A concurrently-scheduled ticker task only advances while
    `add` awaits if `on_capture` is truly off-thread."""
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        for _ in range(10):
            await asyncio.sleep(0.01)
            ticks += 1

    def blocking_on_capture(item: CapturedPage) -> None:
        time.sleep(0.15)

    sink = _CaptureSink(CrawlResult(), blocking_on_capture)
    tick_task = asyncio.create_task(ticker())
    await sink.add(CapturedPage(url="https://example.com", title="Home"))
    # Checked immediately, before awaiting `tick_task`: if `on_capture` ran
    # inline on the event loop (the pre-fix behavior), `ticker` never got a
    # turn until `add` returned, so `ticks` would still be 0 right here.
    assert ticks > 0
    await tick_task


def test_page_fingerprint_preserves_hash_routed_pages_as_distinct() -> None:
    """`[FIXED 2026-07-22]` Root cause of a real run covering only 4 of an
    application's ~10 pages: `_page_fingerprint` used to strip *every*
    fragment unconditionally, so every hash-routed page (`#Shop`,
    `#OrderHistory`, `#ProductManagement` — common in Angular/React SPAs,
    including WaveMaker-generated ones) collapsed to the exact same BFS key
    as the bare origin. Once any one of them was visited, every other one
    looked "already visited" and was silently skipped forever."""
    assert _page_fingerprint("https://app.example.com/#Shop") != _page_fingerprint(
        "https://app.example.com/#OrderHistory"
    )
    assert _page_fingerprint("https://app.example.com/#Shop") == _page_fingerprint(
        "https://app.example.com/#Shop"
    )


def test_page_fingerprint_still_collapses_a_bare_empty_fragment() -> None:
    """The one case fragment-stripping was actually fixing (see
    `test_crawl_does_not_loop_on_a_shared_hash_action_form`): a shared header
    form with `action="#"` appends a bare, *empty* fragment to whatever page
    you're already on — that must still collapse to the same page, or the
    crawler loops forever re-queuing what is really the same destination."""
    assert _page_fingerprint("https://app.example.com/search?q=x#") == _page_fingerprint(
        "https://app.example.com/search?q=x"
    )


def test_page_fingerprint_still_strips_a_bare_trailing_query_string() -> None:
    """A GET form with no named fields navigates to `url?` on submit, real
    browser behavior — that must still collapse to the same page as `url`."""
    assert _page_fingerprint("https://app.example.com/search?") == _page_fingerprint(
        "https://app.example.com/search"
    )
    # A real, non-empty query string is a genuinely distinct page.
    assert _page_fingerprint("https://app.example.com/product?id=6") != _page_fingerprint(
        "https://app.example.com/product?id=7"
    )


def test_page_fingerprint_strips_oauth_callback_params() -> None:
    """`[FIXED 2026-07-22]` A Keycloak-backed (or any OIDC) app's silent-SSO
    redirect lands back on the same route with a fresh, single-use
    `code`/`state`/`session_state`/`iss` each time — observed live, this
    caused the same "Home" page to fingerprint as a brand-new destination on
    every visit, so the crawler re-queued and re-captured it repeatedly and
    never got past it."""
    assert _page_fingerprint(
        "https://app.example.com/react-pages/Home?state=aaa&session_state=bbb"
        "&iss=https%3A%2F%2Fidp.example.com%2Frealms%2FDemo&code=ccc"
    ) == _page_fingerprint("https://app.example.com/react-pages/Home")
    # A real, non-OAuth query param is still preserved and still distinct.
    assert _page_fingerprint(
        "https://app.example.com/product?id=6&code=ccc"
    ) != _page_fingerprint("https://app.example.com/product?id=7&code=ccc")


def test_is_self_referential_duplicate_catches_a_router_bug_glued_path() -> None:
    """`[FIXED 2026-07-23]` Observed live: a client-side router bug on a real
    target resolved a relative `navigate()` call against the current route
    instead of the app root, producing a real browser navigation to
    `.../react-pages/Home/bm_catalog_backoffice_ui/react-pages/Home` — the
    app's own base path glued onto itself. A legitimate page can never
    contain its own app-root path segment twice."""
    base_url = "https://app.example.com/bm_catalog_backoffice_ui/"
    assert _is_self_referential_duplicate(
        "https://app.example.com/bm_catalog_backoffice_ui/react-pages/Home"
        "/bm_catalog_backoffice_ui/react-pages/Home",
        base_url,
    )
    assert not _is_self_referential_duplicate(
        "https://app.example.com/bm_catalog_backoffice_ui/react-pages/Home", base_url
    )


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
