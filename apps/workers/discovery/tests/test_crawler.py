"""DiscoveryActivity's crawl loop against a real local target (Story 2.2, AC 1-2).

Runs a real headless Chromium against fixtures/target_app.py (a real HTTP
server, not an ASGI transport) through the actual crawler + session +
object-store modules — the closest thing to "verify end-to-end" this
environment supports without a real deployed target application.
"""

import json
import uuid

import pytest
from discovery_worker.crawler import run_discovery_crawl
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


@pytest.mark.asyncio
async def test_crawl_captures_every_evidence_type(target_app_url: str) -> None:
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

    types_seen = {item.type for item in result.evidence}
    assert "page" in types_seen
    assert "form" in types_seen
    assert "api_call" in types_seen

    page_evidence = [item for item in result.evidence if item.type == "page"]
    assert page_evidence
    assert all(item.object_storage_key in object_store.stored for item in page_evidence)


@pytest.mark.asyncio
async def test_crawl_detects_session_expiry_mid_crawl(target_app_url: str) -> None:
    # 3 authenticated hits succeed (the post-login redirect, the crawl's own
    # dashboard visit, and the shared header's same-page form resubmit); the
    # dashboard's "Add item" form submission is the 4th and drops the
    # session — a genuine mid-crawl expiry, not an immediate post-login
    # failure.
    configure(expire_after=3)
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

    assert result.session_expired is True
    assert result.evidence, "expected some evidence captured before the session dropped"


@pytest.mark.asyncio
async def test_crawl_does_not_false_positive_on_a_normal_password_field(
    target_app_url: str,
) -> None:
    """A directly-linked page with a password field for a legitimate reason
    (e.g. a change-password section on /settings) must never be mistaken for
    session expiry — only an *unrequested redirect* to a page with a
    password field counts as expiry, not password-field presence alone."""
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

    assert result.session_expired is False
    visited_urls = {item.details["url"] for item in result.evidence if item.type == "page"}
    assert any(url.endswith("/settings") for url in visited_urls), (
        "expected the crawl to actually reach /settings, or this test proves nothing"
    )


@pytest.mark.asyncio
async def test_crawl_does_not_loop_on_a_shared_hash_action_form(target_app_url: str) -> None:
    """Regression: every page in the test target carries a shared header
    form with action="#" (a stand-in for a real site's search/menu icon).
    Submitting it just appends a "#" fragment to the current page — without
    URL normalization, that reads as a "new" page forever and the crawl
    never terminates."""
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

    assert result.session_expired is False

    page_urls = [item.details["url"] for item in result.evidence if item.type == "page"]
    normalized = [url.split("#")[0] for url in page_urls]
    assert len(normalized) == len(set(normalized)), (
        f"the same page was visited more than once (fragment-duplicate loop): {page_urls}"
    )
