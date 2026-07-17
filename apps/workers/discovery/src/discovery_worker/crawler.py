"""Autonomous exploration loop — DiscoveryActivity's core crawl behavior
(Story 2.2, stop condition replaced by Story 2.3).

Neither the PRD nor the Architecture Spine specifies an exact traversal
algorithm (FR-6: "navigates the Application the way a thorough tester
would"). This is a sound, non-binding default: breadth-first link traversal,
generic placeholder values keyed by input type for form-filling, and
Playwright response interception for API calls — not a spec to match
exactly.

Stop condition (Story 2.3, AD-10, FR-7): the crawl runs until no new page is
found to visit — exhaustive traversal is the *only* stop condition. There is
deliberately no iteration/safety cap here (PRD §12 Risk item 7, accepted
risk: an Application with unbounded pagination could run indefinitely).
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urlparse

from playwright.async_api import BrowserContext, Response

_GENERIC_VALUES = {
    "email": "test@example.com",
    "tel": "555-0100",
    "number": "1",
    "date": "2026-01-01",
    "text": "Test value",
    "textarea": "Test value",
}


@dataclass
class CapturedEvidence:
    type: str
    details: dict
    object_storage_key: str | None = None


@dataclass
class CrawlResult:
    evidence: list[CapturedEvidence] = field(default_factory=list)
    session_expired: bool = False


class _EvidenceSink(list):
    """A plain list that also fans each captured item out to an optional
    callback the instant it's captured — so a caller (the real Activity)
    can persist it to Postgres immediately, rather than waiting for the
    whole (possibly very long, uncapped per Story 2.3) crawl to finish.
    Without this, a real site that takes longer than an Activity timeout
    loses every bit of evidence it already captured when the attempt is
    killed and retried from scratch."""

    def __init__(self, on_evidence: Callable[[CapturedEvidence], None] | None = None) -> None:
        super().__init__()
        self._on_evidence = on_evidence

    def append(self, item: CapturedEvidence) -> None:
        super().append(item)
        if self._on_evidence:
            self._on_evidence(item)


def _same_origin(url: str, base_url: str) -> bool:
    return urlparse(url).netloc == urlparse(base_url).netloc


def _normalize(url: str) -> str:
    """Strips the URL fragment for BFS bookkeeping. Some pages carry a
    shared header form whose `action="#"` just appends a fragment to
    whatever page you're already on when submitted — without this, that
    produces a "new" URL every time (`.../search?q=x` vs
    `.../search?q=x#`), and the crawler loops forever re-queuing and
    re-visiting what is really the same page."""
    return urldefrag(url)[0]


async def _fill_and_submit_form(
    page, form_selector: str, evidence: list[CapturedEvidence]
) -> str | None:
    form = page.locator(form_selector)
    action = await form.get_attribute("action") or page.url
    method = (await form.get_attribute("method") or "get").upper()

    fields: list[dict] = []
    inputs = form.locator("input:not([type=submit]):not([type=hidden]):not([type=button])")
    for i in range(await inputs.count()):
        field_el = inputs.nth(i)
        input_type = (await field_el.get_attribute("type")) or "text"
        name = await field_el.get_attribute("name")
        value = _GENERIC_VALUES.get(input_type, "Test value")
        try:
            await field_el.fill(value)
            fields.append({"name": name, "type": input_type})
        except Exception:
            continue

    before_url = _normalize(page.url)
    submit = form.locator("button[type=submit], input[type=submit], button:not([type])")
    try:
        if await submit.count() > 0:
            async with page.expect_navigation(timeout=3000):
                await submit.first.click()
        else:
            await form.evaluate("f => f.submit()")
    except Exception:
        pass

    evidence.append(
        CapturedEvidence(
            type="form", details={"action": action, "method": method, "fields": fields}
        )
    )
    after_url = _normalize(page.url)
    if after_url != before_url:
        evidence.append(
            CapturedEvidence(type="state_transition", details={"from": before_url, "to": after_url})
        )
    return after_url if after_url != before_url else None


async def _click_standalone_buttons(page, evidence: list[CapturedEvidence]) -> None:
    buttons = page.locator("button:not(form button)")
    before_url = _normalize(page.url)
    for i in range(await buttons.count()):
        button = buttons.nth(i)
        label = (await button.inner_text()).strip()
        try:
            await button.click(timeout=1000)
        except Exception:
            continue
        try:
            await page.wait_for_load_state("networkidle", timeout=2000)
        except Exception:
            pass
        evidence.append(
            CapturedEvidence(type="action", details={"label": label, "page": before_url})
        )
        after_url = _normalize(page.url)
        if after_url != before_url:
            evidence.append(
                CapturedEvidence(
                    type="state_transition", details={"from": before_url, "to": after_url}
                )
            )
            before_url = after_url


async def run_discovery_crawl(
    context: BrowserContext,
    base_url: str,
    object_store,
    discovery_run_id: uuid.UUID,
    *,
    on_evidence: Callable[[CapturedEvidence], None] | None = None,
    heartbeat: Callable[[], None] | None = None,
) -> CrawlResult:
    evidence: list[CapturedEvidence] = _EvidenceSink(on_evidence)
    page = await context.new_page()

    async def on_response(response: Response) -> None:
        request = response.request
        if request.resource_type in ("xhr", "fetch"):
            evidence.append(
                CapturedEvidence(
                    type="api_call",
                    details={
                        "method": request.method,
                        "url": request.url,
                        "status": response.status,
                    },
                )
            )

    page.on("response", on_response)

    page_queue: list[str] = [_normalize(base_url)]
    visited_pages: set[str] = set()
    visited_forms: set[str] = set()

    while page_queue:
        url = page_queue.pop(0)
        if url in visited_pages:
            continue
        visited_pages.add(url)

        # Exhaustive traversal (Story 2.3) has no cap and a real site can
        # take far longer than any fixed timeout — heartbeating each
        # iteration lets Temporal tell "still working" apart from "worker
        # died," instead of a short start-to-close timeout killing (and
        # restarting from scratch) a crawl that's simply large.
        if heartbeat:
            heartbeat()

        await page.goto(url)
        screenshot = await page.screenshot()
        key = object_store.put(screenshot, discovery_run_id)
        evidence.append(
            CapturedEvidence(
                type="page",
                details={"url": page.url, "title": await page.title()},
                object_storage_key=key,
            )
        )

        # Story 2.4 (AD-11), checked before the exhaustive-traversal
        # continuation below: session expiry looks like an *unrequested*
        # redirect landing on a page with a password field — the crawler
        # asked to go to `url` but the server bounced it elsewhere. A page
        # reached normally (by clicking a real link, e.g. a "change
        # password" settings page) never redirects, so it can have a
        # password field without ever tripping this — password-field
        # presence alone is not sufficient, redirect-away-from-requested-url
        # is the actual signal (content-based rather than URL-list matching
        # so it also covers a single-URL app shell where the same route
        # serves both the login form and the authenticated view).
        was_redirected = _normalize(page.url) != url
        if was_redirected and await page.locator('input[type="password"]').count() > 0:
            await page.close()
            return CrawlResult(evidence=evidence, session_expired=True)

        links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        for raw_link in links:
            link = _normalize(raw_link)
            if (
                _same_origin(link, base_url)
                and link not in visited_pages
                and link not in page_queue
            ):
                page_queue.append(link)

        form_count = await page.locator("form").count()
        for form_index in range(form_count):
            form_key = f"{_normalize(page.url)}#form-{form_index}"
            if form_key in visited_forms:
                continue
            visited_forms.add(form_key)
            new_url = await _fill_and_submit_form(page, f"form >> nth={form_index}", evidence)
            if (
                new_url
                and new_url not in page_queue
                and _same_origin(new_url, base_url)
                and new_url not in visited_pages
            ):
                page_queue.append(new_url)
            if _normalize(page.url) != url:
                await page.goto(url)

        await _click_standalone_buttons(page, evidence)

    await page.close()
    return CrawlResult(evidence=evidence)
