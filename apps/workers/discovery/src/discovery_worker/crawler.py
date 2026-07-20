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

Rework 2026-07-18 (Sprint Change Proposal): emits typed capture records
(`CapturedPage`/`CapturedForm`/`CapturedAction`/`CapturedApiCall`/
`CapturedTransition`) instead of a generic `CapturedEvidence` shape — there is
no `Evidence` table. Also adds three crawl-optimization rules (AC 4-6):
- **Page-fingerprint dedup (AC 4):** `visited_pages` already keys the BFS by
  normalized URL — a page reached via more than one link is only ever
  crawled/interacted-with the first time it's dequeued.
- **Navigation-first (AC 5):** each page's interactions (forms/buttons) are
  exercised exactly once, at first visit — dedup above means a page already
  visited never has its interactions repeated, so newly-discovered
  navigation targets are always what's left to do next; there is no separate
  priority queue to build on top of that.
- **Representative-action sampling (AC 6):** standalone buttons are grouped
  by their visible label; only the first instance of each distinct label is
  clicked and captured (`representative=True`) — the other DOM instances of
  a repeated pattern (e.g. one "Edit" button per grid row) are never clicked
  or written as a separate `Action` row. Widened to up to `_MAX_ACTIONS_PER_PAGE`
  distinct labels per page (page-body content tried before nav/header/footer
  chrome) so a shared site-wide button doesn't crowd out every page-specific
  call-to-action the way a single first-DOM-match previously did.

Bug fix (2026-07-20): `heartbeat()` was only ever called once per page, at
the top of the outer loop, before that page's forms/buttons were processed.
On a real site, one page's form-fill-and-submit or button-click sequence can
itself take close to (or over) the Activity's `heartbeat_timeout` — observed
live: a slow page caused no heartbeat for >120s, Temporal declared the
activity heartbeat-timed-out, and retried `DiscoveryActivity` from scratch —
repeatedly, since retry attempts aren't capped, re-crawling and re-persisting
the entire site every time (a real, user-visible "infinite loop", not the
accepted-risk unbounded-*traversal* case Story 2.3 already documents).
Fixed by heartbeating before each individual form submission and button
click too, not just once per page.
"""

import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urlparse

from playwright.async_api import BrowserContext, Locator, Response

logger = logging.getLogger(__name__)

_GENERIC_VALUES = {
    "email": "test@example.com",
    "tel": "555-0100",
    "number": "1",
    "date": "2026-01-01",
    "text": "Test value",
    "textarea": "Test value",
}

# A field's declared `type` isn't a reliable signal on its own — a quantity
# box is routinely `type="text"` on real sites, and a generic string value
# there (e.g. "Add to Cart" with quantity="Test value") 500s the server
# instead of landing on a real page. Checked by name/id before falling back
# to `_GENERIC_VALUES` below.
_QUANTITY_FIELD_RE = re.compile(r"qty|quantity|count|amount|number", re.IGNORECASE)


def _generic_value(input_type: str, name: str | None, field_id: str | None) -> str:
    if _QUANTITY_FIELD_RE.search(name or field_id or ""):
        return "1"
    return _GENERIC_VALUES.get(input_type, "Test value")

# Representative-action sampling (AC 6) widened from 1 to a few distinct
# labels per page, so a shared nav/header button doesn't crowd out every
# page-specific call-to-action (e.g. "Add to Cart") — body content is tried
# before chrome so a page's own actions win when the budget is tight.
_MAX_ACTIONS_PER_PAGE = 3
_BODY_BUTTONS = (
    "xpath=//button[not(ancestor::form) and not(ancestor::nav) "
    "and not(ancestor::header) and not(ancestor::footer)]"
)
_CHROME_BUTTONS = (
    "xpath=//button[not(ancestor::form) "
    "and (ancestor::nav or ancestor::header or ancestor::footer)]"
)


@dataclass
class CapturedFormField:
    name: str | None
    input_type: str
    required: bool
    default_value: str | None
    captured_selector: str | None


@dataclass
class CapturedPage:
    url: str
    title: str
    object_storage_key: str | None = None


@dataclass
class CapturedForm:
    page_url: str
    action_url: str
    method: str
    fields: list[CapturedFormField] = field(default_factory=list)


@dataclass
class CapturedAction:
    page_url: str
    description: str
    captured_selector: str | None = None
    representative: bool = True


@dataclass
class CapturedApiCall:
    page_url: str
    method: str
    path: str
    status_code: int | None = None
    response_summary: str | None = None


@dataclass
class CapturedTransition:
    from_url: str
    to_url: str
    triggered_by_description: str | None = None


CapturedItem = (
    CapturedPage | CapturedForm | CapturedAction | CapturedApiCall | CapturedTransition
)


@dataclass
class CrawlResult:
    pages: list[CapturedPage] = field(default_factory=list)
    forms: list[CapturedForm] = field(default_factory=list)
    actions: list[CapturedAction] = field(default_factory=list)
    api_calls: list[CapturedApiCall] = field(default_factory=list)
    transitions: list[CapturedTransition] = field(default_factory=list)
    session_expired: bool = False


class _CaptureSink:
    """Fans each captured item out to an optional callback the instant it's
    captured — so a caller (the real Activity) can persist it to Postgres
    immediately, rather than waiting for the whole (possibly very long,
    uncapped per Story 2.3) crawl to finish. Without this, a real site that
    takes longer than an Activity timeout loses every bit already captured
    when the attempt is killed and retried from scratch."""

    def __init__(
        self, result: CrawlResult, on_capture: Callable[[CapturedItem], None] | None
    ) -> None:
        self._result = result
        self._on_capture = on_capture

    def add(self, item: CapturedItem) -> None:
        if isinstance(item, CapturedPage):
            self._result.pages.append(item)
        elif isinstance(item, CapturedForm):
            self._result.forms.append(item)
        elif isinstance(item, CapturedAction):
            self._result.actions.append(item)
        elif isinstance(item, CapturedApiCall):
            self._result.api_calls.append(item)
        elif isinstance(item, CapturedTransition):
            self._result.transitions.append(item)
        if self._on_capture:
            self._on_capture(item)


def _same_origin(url: str, base_url: str) -> bool:
    return urlparse(url).netloc == urlparse(base_url).netloc


def _page_fingerprint(url: str) -> str:
    """Strips the URL fragment for BFS bookkeeping (AC 4). Some pages carry a
    shared header form whose `action="#"` just appends a fragment to
    whatever page you're already on when submitted — without this, that
    produces a "new" URL every time (`.../search?q=x` vs
    `.../search?q=x#`), and the crawler loops forever re-queuing and
    re-visiting what is really the same page.

    Also strips a bare trailing `?` (empty query string) — a GET form with
    no named fields (that same shared header form) genuinely navigates to
    `url?` when submitted, real browser behavior, not a typo. Without this,
    that reads as a distinct destination worth crawling, and every page on
    the site gets a fully duplicated re-visit under its own `?` variant.
    A real, non-empty query string (`.../product?id=6`) is untouched."""
    defragged = urldefrag(url)[0]
    return defragged[:-1] if defragged.endswith("?") else defragged


async def _capture_selector(locator: Locator, fallback_text: str | None = None) -> str:
    """Whatever selector info is reasonably available, in priority order:
    data-testid, id, name, or a text/role fallback — needed by Story 2.5 to
    derive a usable `ComponentLocator` for this element."""
    testid = await locator.get_attribute("data-testid")
    if testid:
        return f'[data-testid="{testid}"]'
    el_id = await locator.get_attribute("id")
    if el_id:
        return f"#{el_id}"
    name = await locator.get_attribute("name")
    if name:
        return f'[name="{name}"]'
    if fallback_text:
        return f'text="{fallback_text}"'
    tag = await locator.evaluate("el => el.tagName.toLowerCase()")
    return f"css={tag}"


async def _submit_button_label(locator: Locator) -> str | None:
    """`<input type=submit>` shows its label via the `value` attribute, not
    innerText — unlike a `<button>`, so this needs its own lookup rather than
    reusing `_capture_selector`'s fallback_text convention."""
    tag = await locator.evaluate("el => el.tagName.toLowerCase()")
    if tag == "input":
        value = await locator.get_attribute("value")
        return value.strip() if value and value.strip() else None
    text = (await locator.inner_text()).strip()
    return text or None


async def _fill_and_submit_form(
    page,
    form_selector: str,
    page_url: str,
    sink: _CaptureSink,
    seen_form_signatures: set[tuple[str, str, tuple[tuple[str | None, str | None], ...]]],
    heartbeat: Callable[[], None] | None = None,
) -> str | None:
    # A form's fill+submit+settle sequence can itself run close to the
    # heartbeat_timeout window on a slow page — heartbeating here, not just
    # once per page in the outer loop, is what actually prevents a single
    # slow form from silently exhausting the whole activity's heartbeat and
    # triggering a from-scratch retry (see Dev Notes below).
    if heartbeat:
        heartbeat()
    form = page.locator(form_selector)
    action = await form.get_attribute("action") or page.url
    method = (await form.get_attribute("method") or "get").upper()

    # Includes hidden inputs (only submit/button are excluded here) — a form
    # whose `action` is a blank template with the real identity carried in a
    # *hidden field's value* (e.g. Shopbit's per-product "Add to Cart":
    # `action="cart?product-id=&quantity="`, `<input name="product-id"
    # value="6" type="hidden">`) would otherwise look byte-identical across
    # every product and only the first one ever get exercised.
    all_inputs = form.locator("input:not([type=submit]):not([type=button])")
    # One round-trip for every field's starting state, not one per attribute
    # per field — a field-heavy form (a checkout/payment page can easily have
    # a dozen+ inputs) would otherwise multiply into dozens of separate
    # browser round-trips just to decide whether this form was seen before.
    input_info = await all_inputs.evaluate_all(
        "els => els.map(el => ({"
        "type: el.type || 'text', name: el.name || null, value: el.value || null, "
        "id: el.id || null, required: el.required"
        "}))"
    )

    # Representative-form sampling: a form's initial state (shape + every
    # input's starting name/value, hidden included) reachable identically
    # from every page — e.g. a shared header search box — is one feature
    # worth capturing once per crawl, not once per page it happens to appear
    # on (mirrors AC 6's button sampling, applied to forms). Any observable
    # difference — including a hidden identifier's value — means these are
    # genuinely different instances, so this stays conservative by design:
    # dedup only fires when nothing at all differs.
    signature = (
        action,
        method,
        tuple((info["name"], info["value"]) for info in input_info),
    )
    if signature in seen_form_signatures:
        return None
    seen_form_signatures.add(signature)
    logger.info("  filling form on %s: %d fields", page_url, len(input_info))

    fields: list[CapturedFormField] = []
    for i, info in enumerate(input_info):
        if info["type"] == "hidden":
            continue
        # A field-heavy form (checkout/payment) fills one field at a time —
        # each fill is its own browser round-trip, and a slow remote site
        # can make a dozen-plus of these add up past the heartbeat window
        # well before the form is ever submitted. Heartbeat per field, not
        # just once at the top of the whole form.
        if heartbeat:
            heartbeat()
        field_el = all_inputs.nth(i)
        input_type = info["type"]
        name = info["name"]
        value = _generic_value(input_type, name, info["id"])
        selector = await _capture_selector(field_el, fallback_text=name)
        try:
            # Explicit short timeout, not Playwright's 30s default — a
            # checkout-sized form can have several CSS-hidden conditional
            # fields (e.g. a "same as billing" toggle) that never become
            # actionable; without this, each one burns its full default
            # wait before falling into the except below (observed live:
            # ~2.7min silent gap on a 46-field form, 2026-07-20).
            await field_el.fill(value, timeout=2000)
            fields.append(
                CapturedFormField(
                    name=name,
                    input_type=input_type,
                    required=info["required"],
                    default_value=value,
                    captured_selector=selector,
                )
            )
        except Exception:
            continue

    before_url = _page_fingerprint(page.url)
    submit = form.locator("button[type=submit], input[type=submit], button:not([type])")
    submit_label: str | None = None
    submit_selector: str | None = None
    # Bracket the submit+settle sequence with heartbeats — this is the
    # single slowest step in form processing (a real submit can redirect
    # through an auth check, hit a slow remote server, or reload a
    # multi-asset page) and was the actual observed cause of a whole-crawl
    # heartbeat-timeout retry loop (2026-07-20, checkout.jsp on a real site).
    if heartbeat:
        heartbeat()
    try:
        if await submit.count() > 0:
            submit_label = await _submit_button_label(submit.first)
            submit_selector = await _capture_selector(submit.first, fallback_text=submit_label)
            await submit.first.click(timeout=2000)
        else:
            await form.evaluate("f => f.submit()")
    except Exception:
        pass
    # A real submit can redirect through an auth check or reload a page with
    # dozens of assets — well past a single short navigation-event window —
    # so settle on load state generically instead of racing one
    # `expect_navigation` call. A submit with no navigation at all (a
    # client-side "Add to Cart" that only updates in-page state) resolves
    # these near-instantly, so this adds no real delay for that case.
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass
    if heartbeat:
        heartbeat()
    try:
        await page.wait_for_load_state("networkidle", timeout=4000)
    except Exception:
        pass
    if heartbeat:
        heartbeat()

    sink.add(CapturedForm(page_url=page_url, action_url=action, method=method, fields=fields))
    after_url = _page_fingerprint(page.url)
    # Recorded whenever there's a real label, whether or not the submit
    # produced a navigation — a submit that only updates in-page state (no
    # URL change, no XHR) is still a real, testable business action; a
    # Transition is the one that needs an actual observed navigation to mean
    # anything.
    if submit_label:
        sink.add(
            CapturedAction(
                page_url=before_url,
                description=submit_label,
                captured_selector=submit_selector,
            )
        )
    if after_url != before_url:
        sink.add(
            CapturedTransition(
                from_url=before_url, to_url=after_url, triggered_by_description=submit_label
            )
        )
    return after_url if after_url != before_url else None


async def _click_standalone_buttons(
    page, sink: _CaptureSink, base_url: str, heartbeat: Callable[[], None] | None = None
) -> list[str]:
    """Clicks up to `_MAX_ACTIONS_PER_PAGE` distinct-labeled standalone
    buttons — page-body content first, nav/header/footer chrome only if
    budget remains, so a site-wide nav item doesn't crowd out every
    page-specific call-to-action the way a single first-DOM-match did.
    Stops as soon as a click navigates away (remaining locator indices would
    then resolve against the new page, not this one) and returns any
    same-origin URL reached this way for the caller to enqueue, same as a
    link or form-submit destination."""
    before_url = _page_fingerprint(page.url)
    seen_labels: set[str] = set()
    discovered: list[str] = []
    budget = _MAX_ACTIONS_PER_PAGE

    for group_selector in (_BODY_BUTTONS, _CHROME_BUTTONS):
        if budget <= 0:
            break
        buttons = page.locator(group_selector)
        button_count = await buttons.count()
        logger.info("  %s: %d candidate buttons (budget=%d)", before_url, button_count, budget)
        for i in range(button_count):
            if budget <= 0:
                break
            button = buttons.nth(i)
            # Same reasoning as `_fill_and_submit_form`: a click can trigger
            # a slow navigation/settle, so heartbeat before each attempt, not
            # just once per page.
            if heartbeat:
                heartbeat()
            try:
                label = (await button.inner_text()).strip()
            except Exception:
                continue
            # Representative-action sampling (AC 6): a repeated identical
            # action pattern (e.g. one "Edit" button per grid row) is
            # exercised once, not once per DOM instance.
            if not label or label in seen_labels:
                continue
            seen_labels.add(label)
            selector = await _capture_selector(button, fallback_text=label)
            try:
                await button.click(timeout=1000)
            except Exception as exc:
                logger.info("standalone button click failed: %r (%s)", label, exc)
                continue
            # Bracket the settle waits too — the click itself is fast, but
            # what it triggers (a redirect, a slow page reload) is the same
            # class of risk `_fill_and_submit_form`'s submit+settle is.
            if heartbeat:
                heartbeat()
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            if heartbeat:
                heartbeat()
            try:
                await page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass
            if heartbeat:
                heartbeat()
            sink.add(
                CapturedAction(
                    page_url=before_url, description=label, captured_selector=selector
                )
            )
            budget -= 1
            after_url = _page_fingerprint(page.url)
            if after_url != before_url:
                sink.add(
                    CapturedTransition(
                        from_url=before_url, to_url=after_url, triggered_by_description=label
                    )
                )
                if _same_origin(after_url, base_url):
                    discovered.append(after_url)
                return discovered
    return discovered


async def run_discovery_crawl(
    context: BrowserContext,
    base_url: str,
    object_store,
    discovery_run_id: uuid.UUID,
    *,
    on_capture: Callable[[CapturedItem], None] | None = None,
    heartbeat: Callable[[], None] | None = None,
) -> CrawlResult:
    result = CrawlResult()
    sink = _CaptureSink(result, on_capture)
    page = await context.new_page()

    async def on_response(response: Response) -> None:
        request = response.request
        if request.resource_type in ("xhr", "fetch"):
            try:
                # Truncated, not parsed — this is signal for a later negative-
                # path Scenario prompt (Story 4.1), not a typed contract.
                body = (await response.text())[:500]
            except Exception:
                body = None
            sink.add(
                CapturedApiCall(
                    page_url=_page_fingerprint(page.url),
                    method=request.method,
                    path=urlparse(request.url).path,
                    status_code=response.status,
                    response_summary=body,
                )
            )

    page.on("response", on_response)

    page_queue: list[tuple[str, str | None]] = [(_page_fingerprint(base_url), None)]
    queued_urls: set[str] = {page_queue[0][0]}
    visited_pages: set[str] = set()
    visited_forms: set[str] = set()
    seen_form_signatures: set[tuple[str, str, tuple[tuple[str | None, str | None], ...]]] = set()

    def _maybe_enqueue(new_url: str | None, from_url: str) -> None:
        if (
            new_url
            and _same_origin(new_url, base_url)
            and new_url not in visited_pages
            and new_url not in queued_urls
        ):
            page_queue.append((new_url, from_url))
            queued_urls.add(new_url)

    while page_queue:
        url, from_url = page_queue.pop(0)
        if url in visited_pages:
            continue
        visited_pages.add(url)
        queued_urls.discard(url)

        # Exhaustive traversal (Story 2.3) has no cap and a real site can
        # take far longer than any fixed timeout — heartbeating each
        # iteration lets Temporal tell "still working" apart from "worker
        # died," instead of a short start-to-close timeout killing (and
        # restarting from scratch) a crawl that's simply large.
        if heartbeat:
            heartbeat()

        try:
            response = await page.goto(url)
        except Exception:
            # A single broken destination (dead link, DNS blip, timeout)
            # shouldn't take down hours of otherwise-healthy traversal —
            # already marked visited above, so it's never retried.
            continue
        if response is not None and response.status >= 400:
            # A 4xx/5xx destination (e.g. a GET against a POST-only route)
            # is not a business page — persisting it as one would hand the
            # Journey/Scenario model a broken page to build an assertion
            # against and land on. Marked visited above so it's never
            # retried; nothing about it (Page, links, forms, buttons) is
            # explored further.
            continue
        screenshot = await page.screenshot()
        key = object_store.put(screenshot, discovery_run_id)
        sink.add(CapturedPage(url=page.url, title=await page.title(), object_storage_key=key))
        # Records how the crawler actually reached this page — without this,
        # plain link-followed BFS navigation (the vast majority of a normal
        # crawl) left `PageTransition` almost empty, since only click/form-
        # triggered navigation emitted one below.
        if from_url and from_url != url:
            sink.add(CapturedTransition(from_url=from_url, to_url=url))

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
        was_redirected = _page_fingerprint(page.url) != url
        if was_redirected and await page.locator('input[type="password"]').count() > 0:
            await page.close()
            return CrawlResult(
                pages=result.pages,
                forms=result.forms,
                actions=result.actions,
                api_calls=result.api_calls,
                transitions=result.transitions,
                session_expired=True,
            )

        current_url = _page_fingerprint(page.url)
        links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        for raw_link in links:
            _maybe_enqueue(_page_fingerprint(raw_link), current_url)

        form_count = await page.locator("form").count()
        logger.info(
            "visiting %s (page %d/?, %d forms, queue=%d remaining)",
            url,
            len(visited_pages),
            form_count,
            len(page_queue),
        )
        for form_index in range(form_count):
            form_key = f"{_page_fingerprint(page.url)}#form-{form_index}"
            if form_key in visited_forms:
                continue
            visited_forms.add(form_key)
            new_url = await _fill_and_submit_form(
                page,
                f"form >> nth={form_index}",
                _page_fingerprint(page.url),
                sink,
                seen_form_signatures,
                heartbeat=heartbeat,
            )
            _maybe_enqueue(new_url, current_url)
            if _page_fingerprint(page.url) != url:
                await page.goto(url)

        # Button-triggered navigation (e.g. an "Add to Cart" button that
        # isn't a plain <a href>) previously dead-ended here — the click was
        # captured as an Action/Transition but its destination was never
        # queued for further crawling, so any flow reachable only via such a
        # button was structurally invisible past the first click.
        for discovered_url in await _click_standalone_buttons(
            page, sink, base_url, heartbeat=heartbeat
        ):
            _maybe_enqueue(discovered_url, current_url)

    await page.close()
    return result
