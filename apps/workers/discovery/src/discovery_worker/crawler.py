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

import asyncio
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urldefrag, urlencode, urlparse, urlsplit, urlunsplit

from playwright.async_api import BrowserContext, Locator, Response

from discovery_worker.session import attempt_login

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

# Representative-action sampling (AC 6): a repeated identical action pattern
# (e.g. one "Edit" per grid row) is exercised once, not once per DOM
# instance — `seen_labels` in `_click_standalone_buttons` is what actually
# enforces this, by distinct label, not a count.
#
# `[FIXED 2026-07-22]` A per-page numeric click budget (`_MAX_ACTIONS_PER_PAGE`,
# later split into independent body/chrome budgets) used to cap how many
# *distinct*-labeled buttons got clicked per page. That directly contradicts
# Story 2.3/AD-10 ("exhaustive traversal is the only stop condition, no
# safety cap") the moment a real page has more distinct nav destinations than
# the budget — observed live: a left-nav sidebar with 13 distinct sections
# only ever got its first 3 tried, silently dropping the rest. Distinct-label
# dedup (below) already prevents the repeated-DOM-instance case this budget
# was originally added for; the count cap was a redundant second limiter that
# only ever did harm. Removed — every distinct label is now tried.
# `[FIXED 2026-07-22]` A dropdown/menu toggle is very often a Bootstrap-style
# `<a>` (e.g. `<a href="#" class="dropdown-toggle">Account</a>`), not a
# `<button>` — the old `//button`-only selector never clicked it, and its
# dead `href` (`#`, `javascript:void(0)`) also fails the same-origin check
# during link scraping, so it was silently invisible to both discovery paths
# at once. This is exactly the "Account" menu hiding Order History/Product
# Management/etc. behind a click the crawler never made. A real `<a href>`
# to an actual destination is left alone here — it's already found via the
# plain link scrape, no need to also click it.
_DEAD_HREF = (
    "not(@href) or normalize-space(@href)='' or normalize-space(@href)='#' "
    "or starts-with(normalize-space(@href), 'javascript:')"
)
# `[FIXED 2026-07-22]` Removing the click budget above means every distinct
# button now genuinely gets tried, including whatever a dropdown reveals —
# observed live: clicking a real app's user-avatar button ("JD") reveals a
# profile dropdown with a real "Log out" action, which the crawler then
# dutifully clicked, ending its own session mid-crawl ("Session expired
# mid-crawl" — a self-inflicted logout, not a real timeout or rate limit).
# An exhaustive crawler that logs itself out can never finish exhaustively —
# no real QA engineer doing exploratory testing would click this either.
# Checked against both the clicked label (here) and the destination URL
# (`_maybe_enqueue` below, for a plain `<a href="/logout">`-shaped link).
_LOGOUT_RE = re.compile(r"log\s*[-_]?\s*out|sign\s*[-_]?\s*out|log\s*[-_]?\s*off", re.IGNORECASE)
_BODY_BUTTONS = (
    f"xpath=//*[(self::button or (self::a and ({_DEAD_HREF}))) "
    "and not(ancestor::form) and not(ancestor::nav) "
    "and not(ancestor::header) and not(ancestor::footer)]"
)
_CHROME_BUTTONS = (
    f"xpath=//*[(self::button or (self::a and ({_DEAD_HREF}))) "
    "and not(ancestor::form) "
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

    async def add(self, item: CapturedItem) -> None:
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
            # `_on_capture` (the real Activity's `_persist`) does a
            # synchronous Postgres commit — off the event loop so a slow
            # commit stalls only this crawl, not the heartbeat/poll loop
            # this worker process owes Temporal for every other concurrent
            # workflow (observed live: a stalled commit froze the whole
            # worker, not just this activity — 2026-07-21).
            await asyncio.to_thread(self._on_capture, item)


def _same_origin(url: str, base_url: str) -> bool:
    return urlparse(url).netloc == urlparse(base_url).netloc


def _is_self_referential_duplicate(url: str, base_url: str) -> bool:
    """`[FIXED 2026-07-23]` Observed live: a client-side router bug on this
    real target (a relative `navigate()` call resolved against the current
    path instead of the app root) produced a genuine browser navigation to
    `.../react-pages/Home/bm_catalog_backoffice_ui/react-pages/Home` — the
    app's own base path glued onto itself. A legitimate page can never
    contain its own app-root path segment twice, so this is a cheap,
    app-name-agnostic tripwire for that whole bug class rather than a fix
    for this one URL."""
    stem = urlparse(base_url).path.strip("/")
    return bool(stem) and urlparse(url).path.count(stem) > 1


# OIDC Authorization Code flow params (RFC 6749/OIDC core) — see
# `_page_fingerprint`'s docstring for why these get stripped.
_OAUTH_CALLBACK_PARAMS = {"code", "state", "session_state", "iss"}


def _page_fingerprint(url: str) -> str:
    """BFS bookkeeping key (AC 4). `[FIXED 2026-07-22]` Only strips a truly
    *empty* fragment, not any fragment — a shared header form whose
    `action="#"` just appends a bare `#` to whatever page you're already on
    when submitted (`.../search?q=x` -> `.../search?q=x#`), and without
    collapsing that specific case the crawler loops forever re-queuing what
    is really the same page.

    A **non-empty** fragment is very often a real, distinct page in a
    hash-routed SPA (`#/orders`, `#!/products`, `#ProductManagement` —
    common in Angular/React apps, including WaveMaker-generated ones). The
    previous version stripped fragments unconditionally, which silently
    merged every hash-routed page in the app into a single BFS node: once
    any one of them was visited, every other one looked "already visited"
    and was never crawled — the root cause of a real run covering only 4 of
    an application's ~10 pages, all reachable only via `#`-routed nav
    (observed live, shopbit.onwavemaker.com, 2026-07-22). Worth a redundant
    re-visit of a same-page scroll anchor (`/about#team`) over silently
    dropping a real page — never the other way around.

    Also strips a bare trailing `?` (empty query string) — a GET form with
    no named fields (that same shared header form) genuinely navigates to
    `url?` when submitted, real browser behavior, not a typo. A real,
    non-empty query string (`.../product?id=6`) is untouched.

    `[FIXED 2026-07-22, again]` Also strips one-time OAuth/OIDC Authorization
    Code flow callback params (`code`/`state`/`session_state`/`iss`) from the
    query string. Observed live against a real Keycloak-backed app: a
    silent-SSO redirect — retriggered by this crawler's own restore-
    after-navigate `page.goto()` calls in `_click_standalone_buttons` —
    lands back on the exact same route but with a FRESH, single-use
    `code`/`state` each time. Left unstripped, every one of those looks like
    a brand-new page: the crawler re-queued and re-captured the same "Home"
    page 3+ times, one button click at a time, and never got past it. These
    params are inherently single-use and never meaningfully distinguish one
    page from another the way a real `?id=6`-style query does."""
    base, fragment = urldefrag(url)
    if base.endswith("?"):
        base = base[:-1]

    split = urlsplit(base)
    if split.query:
        kept_params = [
            (key, value)
            for key, value in parse_qsl(split.query, keep_blank_values=True)
            if key not in _OAUTH_CALLBACK_PARAMS
        ]
        base = urlunsplit(split._replace(query=urlencode(kept_params)))

    return f"{base}#{fragment}" if fragment else base


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
    rescan: Callable[[str], Awaitable[int]] | None = None,
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
        logger.info("  skip form on %s: identical signature already seen this crawl", page_url)
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
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    if heartbeat:
        heartbeat()
    # `networkidle` can resolve before an SPA's post-navigation data fetch
    # even starts (see the same fix in `run_discovery_crawl`'s main loop) —
    # wait for actual rendered text too, not just quiet network.
    try:
        await page.wait_for_function(
            "document.body && document.body.innerText.trim().length > 0", timeout=15000
        )
    except Exception:
        pass
    if heartbeat:
        heartbeat()

    await sink.add(
        CapturedForm(page_url=page_url, action_url=action, method=method, fields=fields)
    )
    after_url = _page_fingerprint(page.url)
    # Recorded whenever there's a real label, whether or not the submit
    # produced a navigation — a submit that only updates in-page state (no
    # URL change, no XHR) is still a real, testable business action; a
    # Transition is the one that needs an actual observed navigation to mean
    # anything.
    if submit_label:
        await sink.add(
            CapturedAction(
                page_url=before_url,
                description=submit_label,
                captured_selector=submit_selector,
            )
        )
    if after_url != before_url:
        logger.info("  form submit on %s navigated -> %s", page_url, after_url)
        await sink.add(
            CapturedTransition(
                from_url=before_url, to_url=after_url, triggered_by_description=submit_label
            )
        )
    elif rescan:
        # No navigation — but the submit may still have changed the DOM
        # in-place (e.g. an AJAX "Add to Cart" that updates a nav badge, or
        # reveals a confirmation panel with its own links). A one-shot link
        # scrape at page-load time would never see whatever this revealed.
        newly_found = await rescan(before_url)
        if newly_found:
            logger.info(
                "  form submit on %s revealed %d new link(s) without navigating",
                page_url,
                newly_found,
            )
    return after_url if after_url != before_url else None


async def _recover_login_if_needed(
    page,
    expected_url: str,
    credential: bytes | None,
    heartbeat: Callable[[], None] | None = None,
) -> bool:
    """Called after a restore-style `page.goto(expected_url)` (used both
    after a navigating button click and after a form submit, below). Some
    real apps — observed live: a Keycloak-backed one that re-checks auth
    aggressively enough that even a plain restore navigation can land back on
    its login screen — make this restore itself unreliable. Returns True
    once `page` is genuinely back on `expected_url`, attempting a bounded
    number of login replays first if a password field is present and a
    `credential` is available to replay it with. Returns False if recovery
    wasn't possible (no credential, or every retry still didn't land where
    expected) — it's the caller's job to then stop cleanly rather than
    silently keep operating on the wrong page.

    `[FIXED 2026-07-22]` A single attempt here wasn't enough on an app that
    re-checks auth this aggressively — observed live: exploring a left-nav
    sidebar stopped after just 1-2 real items every time, always right after
    the *first* navigating click, because this recovery only ever tried
    once and gave up the moment that one attempt didn't land cleanly (a
    transient Keycloak-redirect timing hiccup, not a truly dead session).
    The outer per-page reauth in `run_discovery_crawl` already tolerates
    this via `_MAX_CONSECUTIVE_REAUTH_ATTEMPTS` retries; this one, called
    far more often (once per click, not once per page), needs the same
    tolerance even more."""
    if _page_fingerprint(page.url) == expected_url:
        return True
    if credential is None:
        return False
    for _attempt in range(_MAX_CONSECUTIVE_REAUTH_ATTEMPTS):
        if await page.locator('input[type="password"]').count() == 0:
            return False
        await attempt_login(page, credential, heartbeat=heartbeat)
        if heartbeat:
            heartbeat()
        try:
            await page.goto(expected_url)
        except Exception:
            return False
        if heartbeat:
            heartbeat()
        if _page_fingerprint(page.url) == expected_url:
            return True
    return False


async def _click_standalone_buttons(
    page,
    sink: _CaptureSink,
    base_url: str,
    rescan: Callable[[str], Awaitable[int]] | None = None,
    heartbeat: Callable[[], None] | None = None,
    credential: bytes | None = None,
    seen_labels: set[str] | None = None,
) -> list[str]:
    """Clicks every distinct-labeled standalone button — page-body content
    tried before nav/header/footer chrome, no numeric cap on either (see the
    comment above `_BODY_BUTTONS`/`_CHROME_BUTTONS`) — and returns any
    same-origin URL reached this way for the caller to enqueue, same as a
    link or form-submit destination.

    `[FIXED 2026-07-22]` A click that navigates away used to stop this
    function entirely, on the theory that remaining locator indices would
    resolve against the new page, not this one — true, but wrong for a
    persistent-shell SPA (e.g. a left-nav sidebar shown on every route):
    once *any* item earlier in DOM order pointed back to a page already
    visited (an extremely common shape — a "Home"/logo link), every visit to
    every *other* page hit that item first, navigated away immediately, and
    never got to try the rest of the sidebar at all (observed live: a 13-item
    left-nav where only 1-2 items were ever reachable). Now restores the
    original page (`page.goto(before_url)`, the same restore-after-navigate
    pattern `_fill_and_submit_form`'s caller already uses for forms below)
    and keeps going — re-querying candidates fresh each pass, so a dropdown
    reveal or a restored page's re-rendered DOM is never read from a stale
    locator. A click that does *not* navigate (a dropdown/drawer/accordion
    toggle) triggers `rescan` the same as before.

    `[ADDED 2026-07-22]` `seen_labels`, if passed in, is mutated in place and
    used as the starting point instead of an empty set — lets the caller
    checkpoint progress across a mid-page session-expiry restart (see
    `seen_button_labels_by_page` in `run_discovery_crawl`), so a retry skips
    straight past already-clicked buttons instead of re-doing them (and
    risking expiring again before ever reaching a new one)."""
    before_url = _page_fingerprint(page.url)
    if seen_labels is None:
        seen_labels = set()
    discovered: list[str] = []

    for group_selector, group_name in (
        (_BODY_BUTTONS, "body"),
        (_CHROME_BUTTONS, "chrome (nav/header/footer)"),
    ):
        while True:
            buttons = page.locator(group_selector)
            button_count = await buttons.count()

            button = None
            label: str | None = None
            for i in range(button_count):
                if heartbeat:
                    heartbeat()
                candidate = buttons.nth(i)
                try:
                    candidate_label = (await candidate.inner_text()).strip()
                except Exception as exc:
                    logger.info(
                        "  %s: %s button #%d inner_text failed, skipping (%s)",
                        before_url,
                        group_name,
                        i,
                        exc,
                    )
                    continue
                # Representative-action sampling (AC 6): a repeated identical
                # action pattern (e.g. one "Edit" button per grid row) is
                # exercised once, not once per DOM instance.
                if not candidate_label or candidate_label in seen_labels:
                    continue
                if candidate_label.strip().lower() == "icon":
                    # `[FIXED 2026-07-22]` A bare, generic "Icon" label (no
                    # other distinguishing text) is exactly the accessible
                    # name a left-nav collapse toggle reports — observed
                    # live: clicking it genuinely collapses the whole
                    # sidebar to zero size for the rest of this page visit,
                    # confirmed with a raw `getBoundingClientRect()` check,
                    # and clicking it again does *not* reliably restore it
                    # (not a simple toggle). Same class of self-defeating
                    # click as "Log out" — skip it rather than lose
                    # navigation for the whole page.
                    seen_labels.add(candidate_label)
                    continue
                if _LOGOUT_RE.search(candidate_label):
                    logger.info(
                        "  %s: refusing to click %s button %r — looks like a logout control",
                        before_url,
                        group_name,
                        candidate_label,
                    )
                    seen_labels.add(candidate_label)
                    continue
                button, label = candidate, candidate_label
                break

            if button is None or label is None:
                # Nothing left unseen in this group — move to the next one.
                break

            seen_labels.add(label)
            selector = await _capture_selector(button, fallback_text=label)
            try:
                await button.click(timeout=1000)
            except Exception as first_exc:
                # `[FIXED 2026-07-22]` Observed live: the *exact* same
                # element, same selector, sometimes fails this click with
                # "element is not visible" and sometimes succeeds instantly
                # on a fresh page that never triggered it. Playwright's own
                # `bounding_box()` isn't a useful independent check here —
                # it shares the same visibility heuristic the click itself
                # uses, so it reports zero-size for the exact same reason
                # the click failed (confirmed live: always empty in exactly
                # this situation). A raw `getBoundingClientRect()` — real
                # layout, no Playwright opinion involved — showed this
                # element fully on-screen with real dimensions the whole
                # time. This is a left-nav panel's CSS transition class
                # ("slide-in"/"collapsed") confusing Playwright's stability
                # check, not a genuinely hidden or covered element, so force
                # through it — a truly zero-size/off-screen element still
                # gets skipped below, since the raw rect check catches that
                # case for real.
                has_real_size = False
                try:
                    has_real_size = await button.evaluate(
                        "el => { const r = el.getBoundingClientRect(); "
                        "return r.width > 0 && r.height > 0; }"
                    )
                except Exception:
                    pass
                if not has_real_size:
                    logger.info(
                        "  %s: %s button click failed, not on-screen: %r (%s)",
                        before_url,
                        group_name,
                        label,
                        first_exc,
                    )
                    continue
                try:
                    await button.click(timeout=1500, force=True)
                except Exception as exc:
                    logger.info(
                        "  %s: %s button click failed even with force=True: %r (%s)",
                        before_url,
                        group_name,
                        label,
                        exc,
                    )
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
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            if heartbeat:
                heartbeat()
            # `networkidle` can resolve before an SPA's post-navigation data
            # fetch even starts (see the same fix in `run_discovery_crawl`'s
            # main loop) — wait for actual rendered text too, not just quiet
            # network.
            try:
                await page.wait_for_function(
                    "document.body && document.body.innerText.trim().length > 0", timeout=15000
                )
            except Exception:
                pass
            if heartbeat:
                heartbeat()
            await sink.add(
                CapturedAction(
                    page_url=before_url, description=label, captured_selector=selector
                )
            )
            after_url = _page_fingerprint(page.url)
            if after_url != before_url:
                logger.info(
                    "  %s button %r navigated: %s -> %s", group_name, label, before_url, after_url
                )
                await sink.add(
                    CapturedTransition(
                        from_url=before_url, to_url=after_url, triggered_by_description=label
                    )
                )
                if _same_origin(after_url, base_url):
                    discovered.append(after_url)
                try:
                    await page.goto(before_url)
                except Exception as exc:
                    logger.warning(
                        "  %s: could not restore page after %s button %r navigated away (%s) — "
                        "stopping %s group early",
                        before_url,
                        group_name,
                        label,
                        exc,
                        group_name,
                    )
                    break
                if not await _recover_login_if_needed(page, before_url, credential, heartbeat):
                    logger.warning(
                        "  %s: session appears lost restoring after %s button %r — "
                        "stopping %s group early",
                        before_url,
                        group_name,
                        label,
                        group_name,
                    )
                    break
                # `[FIXED 2026-07-22]` The restored page can need the exact
                # same real-content settle time the very first page load
                # does (observed live: this app's own left-nav sidebar takes
                # ~4.5s to render after any fresh navigation) — searching
                # for the next candidate immediately, with no wait at all,
                # can catch the restored page mid-render and find nothing,
                # prematurely treating this group as exhausted after just
                # the first navigating click. Same content-readiness check
                # already used for a page's first visit and after a
                # non-navigating click, applied here too.
                try:
                    await page.wait_for_function(
                        "document.body && document.body.innerText.trim().length > 0",
                        timeout=15000,
                    )
                except Exception:
                    pass
                if heartbeat:
                    heartbeat()
                continue
            if rescan:
                # Didn't navigate — likely a toggle/dropdown/drawer/accordion.
                # Whatever it revealed may include new <a href> nav links
                # (React/Angular apps very often conditionally *render* menu
                # items rather than just CSS-hiding a pre-rendered menu, so a
                # one-shot link scrape at page-load time would never see
                # them) — this is exactly the gap that hid an app's
                # authenticated nav menu (Order History, Product Management,
                # etc.) behind an "Account" dropdown, 2026-07-22.
                newly_found = await rescan(before_url)
                if newly_found:
                    logger.info(
                        "  %s button %r revealed %d new link(s) without navigating",
                        group_name,
                        label,
                        newly_found,
                    )
    return discovered


# `[ADDED 2026-07-22]` A genuinely broken login (wrong stored credential,
# a login form the crawler can't drive) must still terminate as
# `session_expired` rather than retry forever — bounds *consecutive*
# re-login attempts with no successful page captured in between (reset to 0
# on every real page, so a long healthy crawl that occasionally needs to
# refresh a short-lived token is never penalized for it).
_MAX_CONSECUTIVE_REAUTH_ATTEMPTS = 3


async def run_discovery_crawl(
    context: BrowserContext,
    base_url: str,
    object_store,
    discovery_run_id: uuid.UUID,
    *,
    on_capture: Callable[[CapturedItem], None] | None = None,
    heartbeat: Callable[[], None] | None = None,
    auth_method: str | None = None,
    credential: bytes | None = None,
    login_page_url: str | None = None,
) -> CrawlResult:
    result = CrawlResult()
    sink = _CaptureSink(result, on_capture)
    page = await context.new_page()
    reauth_attempts_since_last_page = 0

    async def on_response(response: Response) -> None:
        request = response.request
        if request.resource_type in ("xhr", "fetch"):
            try:
                # Truncated, not parsed — this is signal for a later negative-
                # path Scenario prompt (Story 4.1), not a typed contract.
                body = (await response.text())[:500]
            except Exception:
                body = None
            await sink.add(
                CapturedApiCall(
                    page_url=_page_fingerprint(page.url),
                    method=request.method,
                    path=urlparse(request.url).path,
                    status_code=response.status,
                    response_summary=body,
                )
            )

    page.on("response", on_response)

    # `[ADDED 2026-07-23]` Seeding the very first page's `from_url` with the
    # login page (when one was captured pre-crawl by `establish_session`)
    # gives it its only edge into the rest of the navigation graph — without
    # this, `journey_clustering.py`'s connectivity-based grouping sees it as
    # an isolated island with nothing to form a "Sign in" journey's second
    # step from, and no candidate journey ever gets inferred for it.
    page_queue: list[tuple[str, str | None]] = [(_page_fingerprint(base_url), login_page_url)]
    queued_urls: set[str] = {page_queue[0][0]}
    visited_pages: set[str] = set()
    visited_forms: set[str] = set()
    seen_form_signatures: set[tuple[str, str, tuple[tuple[str | None, str | None], ...]]] = set()
    # `[ADDED 2026-07-22]` A mid-page session expiry (see `_recover_login_if_needed`
    # and the reauth block below) re-processes the SAME page from scratch —
    # without this, a real short-lived-token app that expires *during* one
    # page's own button exploration (not just between pages) would restart
    # `_click_standalone_buttons`'s `seen_labels` empty every time, re-trying
    # already-clicked buttons before ever reaching new ones. Observed live: a
    # crawl stuck cycling the same 2 pages for 25+ minutes, never progressing,
    # because each retry re-did the same early candidates and expired again
    # before reaching new ones. Keyed by page fingerprint so unrelated pages
    # don't share state, persists across BFS re-queues of the same page.
    seen_button_labels_by_page: dict[str, set[str]] = {}

    def _maybe_enqueue(new_url: str | None, from_url: str) -> str:
        """Returns why a candidate URL was or wasn't queued — used both to
        actually drive the BFS and to power `_extract_and_enqueue_links`'s
        per-page skip-reason summary below (`[ADDED 2026-07-22]` — this used
        to be silent, which is exactly why a whole class of "page never
        gets crawled" bugs went unnoticed until a live run was manually
        compared against the real site's page list)."""
        if not new_url:
            return "empty"
        if not _same_origin(new_url, base_url):
            return "off-origin"
        if _is_self_referential_duplicate(new_url, base_url):
            return "malformed-duplicate-path"
        if _LOGOUT_RE.search(urlparse(new_url).path):
            # A plain `<a href="/logout">`-shaped link — same self-inflicted
            # session-ending risk as clicking a "Log out" button (see
            # `_LOGOUT_RE`'s definition above), just via ordinary link
            # scraping instead of a click.
            return "logout-link"
        if new_url in visited_pages:
            return "already-visited"
        if new_url in queued_urls:
            return "already-queued"
        page_queue.append((new_url, from_url))
        queued_urls.add(new_url)
        return "enqueued"

    async def _extract_and_enqueue_links(from_url: str) -> int:
        """Scrapes every `<a href>` currently in the DOM and enqueues each
        new same-origin destination. `[ADDED 2026-07-22]` Called not just
        once at page-load (the original behavior) but also after every
        button click / form submit that *doesn't* navigate — a dropdown,
        drawer, or accordion toggle very often renders its `<a>` items into
        the DOM for the first time on click (React/Angular conditional
        rendering) rather than just un-hiding a pre-rendered menu, so a
        single scrape right after `goto()` would never see them. This is
        what actually unlocks a nav menu's authenticated pages (Order
        History, Product Management, etc.) that only existed behind an
        "Account" dropdown.

        `[FIXED 2026-07-22]` A same-URL form submit/click can still trigger a
        real navigation (a self-redirect, or a reload back to the same
        route) even though the fingerprint-based `before_url == after_url`
        check upstream says nothing changed — the settle waits can resolve
        just before a second, in-flight navigation invalidates the page's
        JS execution context, and `eval_on_selector_all` then raises rather
        than returning. Observed live against shopbit.onwavemaker.com: this
        crashed straight out of `run_discovery_crawl` uncaught, failing the
        *entire* Discovery Run over one page's link-scrape timing, instead
        of just skipping that one scrape attempt like every other transient
        per-page failure in this file already does."""
        try:
            links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        except Exception as exc:
            logger.warning("  %s: link scrape failed, skipping (%s)", from_url, exc)
            return 0
        tally: dict[str, int] = {}
        new_links: list[str] = []
        for raw_link in links:
            reason = _maybe_enqueue(_page_fingerprint(raw_link), from_url)
            tally[reason] = tally.get(reason, 0) + 1
            if reason == "enqueued":
                new_links.append(_page_fingerprint(raw_link))
        logger.info(
            "  %s: %d <a href> found — %s",
            from_url,
            len(links),
            ", ".join(f"{count} {reason}" for reason, count in sorted(tally.items())) or "none",
        )
        if new_links:
            logger.info("  %s: newly discovered -> %s", from_url, new_links)
        return len(new_links)

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
        except Exception as exc:
            # A single broken destination (dead link, DNS blip, timeout)
            # shouldn't take down hours of otherwise-healthy traversal —
            # already marked visited above, so it's never retried.
            logger.warning("skip %s: goto() failed (%s)", url, exc)
            continue
        if response is not None and response.status >= 400:
            # A 4xx/5xx destination (e.g. a GET against a POST-only route)
            # is not a business page — persisting it as one would hand the
            # Journey/Scenario model a broken page to build an assertion
            # against and land on. Marked visited above so it's never
            # retried; nothing about it (Page, links, forms, buttons) is
            # explored further.
            logger.warning("skip %s: HTTP %d", url, response.status)
            continue

        # `[ADDED 2026-07-22]` `goto()`'s default `waitUntil="load"` fires as
        # soon as the initial HTML/assets are done — many SPA frameworks
        # (React/Angular, which WaveMaker-generated apps are built on) then
        # make an additional async call (e.g. "fetch my permissions, then
        # render the nav") before the *authenticated* menu actually appears.
        # Scraping links immediately after `goto()`, with no settle wait at
        # all, could miss exactly that menu. Best-effort — a page that never
        # goes idle (a live-updating dashboard) just falls through to
        # whatever rendered within the timeout, same tolerance already used
        # after every form submit/button click below.
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        if heartbeat:
            heartbeat()
        # `[FIXED 2026-07-22, again]` `networkidle` is a *network* signal, not
        # a content one — observed live against a real Next.js app behind
        # Keycloak OAuth (poc-react-app.onwavemaker.com): the post-login route
        # goes quiet (network-idle) around 1-3s, *before* it fires the actual
        # "load my nav" API call, so the wait above kept resolving early
        # regardless of its timeout — real sidebar content only rendered
        # ~4.5s in. Result: a genuinely empty page scraped every time (1 page,
        # 0 actions, 0 links, no error — just nothing there yet). Waiting for
        # actual rendered text is a direct, content-based signal that doesn't
        # depend on guessing the app's network behavior; best-effort/bounded
        # the same way as every other settle-wait here.
        try:
            await page.wait_for_function(
                "document.body && document.body.innerText.trim().length > 0", timeout=15000
            )
        except Exception:
            pass
        if heartbeat:
            heartbeat()

        try:
            screenshot = await page.screenshot()
            title = await page.title()
            # Synchronous MinIO upload — off the event loop for the same
            # reason as the DB commit above (see `_CaptureSink.add`).
            key = await asyncio.to_thread(object_store.put, screenshot, discovery_run_id)
        except Exception as exc:
            # A screenshot/upload hiccup on one page previously failed the
            # *entire* run (any uncaught exception here escapes to
            # `discovery_activity`'s except-block, below) — treat it like
            # any other broken destination instead: skip the page, keep
            # crawling everything else.
            logger.warning("skip %s: screenshot/upload failed (%s)", url, exc)
            continue
        await sink.add(CapturedPage(url=page.url, title=title, object_storage_key=key))
        # Records how the crawler actually reached this page — without this,
        # plain link-followed BFS navigation (the vast majority of a normal
        # crawl) left `PageTransition` almost empty, since only click/form-
        # triggered navigation emitted one below.
        if from_url and from_url != url:
            await sink.add(CapturedTransition(from_url=from_url, to_url=url))

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
            # `[ADDED 2026-07-22]` A short-lived OAuth/OIDC access token
            # (observed live: a Keycloak-backed app) can expire well before
            # an exhaustive crawl finishes — treating this as unconditionally
            # terminal means such an app can *never* be fully discovered.
            # Replay the same login the crawl started with and resume this
            # exact page, bounded by `_MAX_CONSECUTIVE_REAUTH_ATTEMPTS` so a
            # genuinely broken login (wrong credential, an unhandled login
            # form) still terminates rather than retrying forever.
            if (
                auth_method == "standard_login"
                and credential is not None
                and reauth_attempts_since_last_page < _MAX_CONSECUTIVE_REAUTH_ATTEMPTS
            ):
                reauth_attempts_since_last_page += 1
                logger.warning(
                    "session expired mid-crawl: requested %s, redirected to %s — "
                    "attempting silent re-login (%d/%d)",
                    url,
                    page.url,
                    reauth_attempts_since_last_page,
                    _MAX_CONSECUTIVE_REAUTH_ATTEMPTS,
                )
                await attempt_login(page, credential, heartbeat=heartbeat)
                if heartbeat:
                    heartbeat()
                visited_pages.discard(url)
                queued_urls.add(url)
                page_queue.insert(0, (url, from_url))
                continue

            logger.warning(
                "session expired: requested %s, redirected to %s (password field present)",
                url,
                page.url,
            )
            await page.close()
            return CrawlResult(
                pages=result.pages,
                forms=result.forms,
                actions=result.actions,
                api_calls=result.api_calls,
                transitions=result.transitions,
                session_expired=True,
            )
        reauth_attempts_since_last_page = 0

        current_url = _page_fingerprint(page.url)
        await _extract_and_enqueue_links(current_url)

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
                rescan=_extract_and_enqueue_links,
                heartbeat=heartbeat,
            )
            _maybe_enqueue(new_url, current_url)
            if _page_fingerprint(page.url) != url:
                await page.goto(url)
                if not await _recover_login_if_needed(page, url, credential, heartbeat):
                    logger.warning(
                        "  %s: session appears lost restoring after a form submit — "
                        "stopping form loop early",
                        url,
                    )
                    break

        # Button-triggered navigation (e.g. an "Add to Cart" button that
        # isn't a plain <a href>) previously dead-ended here — the click was
        # captured as an Action/Transition but its destination was never
        # queued for further crawling, so any flow reachable only via such a
        # button was structurally invisible past the first click.
        for discovered_url in await _click_standalone_buttons(
            page,
            sink,
            base_url,
            rescan=_extract_and_enqueue_links,
            heartbeat=heartbeat,
            credential=credential,
            seen_labels=seen_button_labels_by_page.setdefault(current_url, set()),
        ):
            _maybe_enqueue(discovered_url, current_url)

    logger.info(
        "crawl finished: %d pages, %d forms, %d actions, %d api calls, %d transitions",
        len(result.pages),
        len(result.forms),
        len(result.actions),
        len(result.api_calls),
        len(result.transitions),
    )
    await page.close()
    return result
